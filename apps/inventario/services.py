import base64
import binascii
import datetime
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.catalogo.models import Articulo
from apps.usuarios.roles import ALIAS_ROLES
from apps.entidades.models import Proveedor
from apps.obras.models import Obra
from .models import (
    DetalleDocumento, DetalleSesionInventario, Despacho, DocumentoEntrada,
    MovimientoInventario as M, OrdenRestock, SesionInventario, SolicitudDespacho,
)

TIPOS_SUMAN = {M.TIPO_ENTRADA, M.TIPO_DEVOLUCION_OBRA, M.TIPO_AJUSTE_POS}
TIPOS_RESTAN = {M.TIPO_SALIDA, M.TIPO_EGRESO_OBRA, M.TIPO_MERMA, M.TIPO_DEVOLUCION_PROVEEDOR,
                M.TIPO_USO_INTERNO, M.TIPO_AJUSTE_NEG}
# Movimientos que exigen justificación obligatoria (toda merma, entre ellos).
TIPOS_CON_JUSTIFICACION = {M.TIPO_MERMA, M.TIPO_DEVOLUCION_OBRA, M.TIPO_DEVOLUCION_PROVEEDOR,
                           M.TIPO_USO_INTERNO, M.TIPO_AJUSTE_POS, M.TIPO_AJUSTE_NEG}
MIN_JUSTIFICACION = 10
SALIDAS_TIPIFICADAS = (M.TIPO_MERMA, M.TIPO_DEVOLUCION_OBRA, M.TIPO_DEVOLUCION_PROVEEDOR, M.TIPO_USO_INTERNO)


def _a_decimal(valor, nombre):
    """Convierte a Decimal validando que sea finito y con a lo más 2 decimales."""
    try:
        d = Decimal(str(valor).strip().replace(',', '.'))
    except (InvalidOperation, ValueError, AttributeError):
        raise ValidationError(f"{nombre} no es un número válido.")
    if not d.is_finite():
        raise ValidationError(f"{nombre} no es un número válido.")
    if d != d.quantize(Decimal('0.01')):
        raise ValidationError(f"{nombre} admite como máximo 2 decimales.")
    if abs(d) >= Decimal('100000000'):
        raise ValidationError(f"{nombre} es demasiado grande.")
    return d


def calcular_descuentos_sucesivos(precio_base, desc1=0, desc2=0, desc3=0):
    """
    Calcula el precio unitario final aplicando hasta tres descuentos sucesivos independientes.
    Retorna el precio unitario final redondeado al entero más cercano (CLP).
    """
    p = Decimal(str(precio_base))
    d1 = Decimal(str(desc1 or 0))
    d2 = Decimal(str(desc2 or 0))
    d3 = Decimal(str(desc3 or 0))

    for d in (d1, d2, d3):
        if d < 0 or d > 100:
            raise ValidationError(f"El porcentaje de descuento debe estar entre 0% y 100%. Valor recibido: {d}%")
        p = p * (Decimal('1') - (d / Decimal('100')))

    # Redondeo bancario/comercial estándar para CLP
    precio_final = int(p.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    return max(0, precio_final)


def calcular_subtotal_linea(precio_unitario_final, cantidad):
    """
    Calcula el subtotal de una línea multiplicando precio final por cantidad.
    """
    cant = Decimal(str(cantidad))
    if cant <= 0:
        raise ValidationError("La cantidad del ítem debe ser mayor a 0.")
    subtotal = (Decimal(precio_unitario_final) * cant).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    return int(subtotal)


# ---------------------------------------------------------------------------
# PUNTO ÚNICO DE ESCRITURA AL CARDEX
# Todo cambio de stock pasa por aquí: bloquea el artículo, valida, actualiza el
# saldo y deja un asiento inalterable con fecha, hora y usuario (HU-01/02/04/05).
# ---------------------------------------------------------------------------
@transaction.atomic
def registrar_movimiento(articulo_id, tipo, cantidad, usuario, referencia, costo=None, documento=None,
                         obra=None, justificacion='', proveedor=None, tecnico=None, despacho=None,
                         sesion=None, actualizar_costos=False, orden_restock=None):
    if tipo not in TIPOS_SUMAN | TIPOS_RESTAN:
        raise ValidationError(f"Tipo de movimiento no soportado: {tipo}.")
    if usuario is None or not getattr(usuario, 'pk', None):
        raise ValidationError("Todo movimiento requiere un usuario responsable.")

    cantidad = _a_decimal(cantidad, "La cantidad")
    if cantidad <= 0:
        raise ValidationError("La cantidad debe ser mayor a cero.")

    justificacion = (justificacion or '').strip()
    if tipo in TIPOS_CON_JUSTIFICACION and len(justificacion) < MIN_JUSTIFICACION:
        raise ValidationError(f"Este movimiento exige una justificación de al menos {MIN_JUSTIFICACION} caracteres.")

    if tipo == M.TIPO_EGRESO_OBRA:
        if obra is None or tecnico is None or despacho is None:
            raise ValidationError("El egreso exige obra, técnico receptor y vale de salida.")
        if obra.estado != Obra.Estado.ACTIVA:
            raise ValidationError("Solo se puede egresar material a una obra activa.")
    if tipo == M.TIPO_DEVOLUCION_OBRA and obra is None:
        raise ValidationError("La devolución desde obra exige indicar la obra.")
    if tipo == M.TIPO_DEVOLUCION_PROVEEDOR:
        if proveedor is None or proveedor.tipo != Proveedor.Tipo.PROVEEDOR:
            raise ValidationError("La devolución a proveedor exige seleccionar un proveedor.")

    try:
        articulo = Articulo.objects.select_for_update().get(pk=articulo_id)
    except Articulo.DoesNotExist:
        raise ValidationError("El artículo seleccionado no existe.")
    if not articulo.activo:
        raise ValidationError(f"El artículo '{articulo.nombre}' está desactivado.")

    anterior = articulo.stock_actual
    if tipo in TIPOS_SUMAN:
        posterior = anterior + cantidad
    else:
        if anterior < cantidad:
            raise ValidationError(
                f"Stock insuficiente de '{articulo.nombre}'. Disponible: {anterior}, requerido: {cantidad}."
            )
        posterior = anterior - cantidad

    campos = ['stock_actual']
    if actualizar_costos:
        # Único lugar donde cambian el último costo y el PMP: siempre con un respaldo
        # (documento tributario u orden de restock aprobada por Finanzas).
        if tipo != M.TIPO_ENTRADA or costo is None or (documento is None and orden_restock is None):
            raise ValidationError("El costo solo se actualiza con una entrada respaldada por un documento.")
        costo_previo = Decimal(anterior) * Decimal(articulo.pmp_costo_actual)
        pmp = (costo_previo + cantidad * Decimal(int(costo))) / posterior
        articulo.ultimo_costo_compra = int(costo)
        articulo.pmp_costo_actual = int(pmp.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        campos += ['ultimo_costo_compra', 'pmp_costo_actual']

    articulo.stock_actual = posterior
    articulo.save(update_fields=campos)

    return M.objects.create(
        articulo=articulo, documento=documento, tipo_movimiento=tipo, cantidad=cantidad,
        stock_anterior=anterior, stock_posterior=posterior,
        costo_unitario=articulo.pmp_costo_actual if costo is None else int(costo),
        usuario=usuario, referencia=referencia[:255], obra=obra, proveedor=proveedor,
        tecnico=tecnico, despacho=despacho, sesion_inventario=sesion, justificacion=justificacion,
        orden_restock=orden_restock,
    )


# ---------------------------------------------------------------------------
# INGRESO DE DOCUMENTOS TRIBUTARIOS (HU-01)
# ---------------------------------------------------------------------------
def _glosa_documento(documento):
    return (f"{documento.get_tipo_documento_display()} N° {documento.numero_documento} - "
            f"{documento.proveedor.razon_social}")


def _movimiento_por_documento(documento, articulo_id, cantidad, precio_final, usuario):
    """Asienta una línea del documento en el Cardex: la NC resta sin tocar el PMP,
    factura/boleta/guía suman y recalculan último costo y PMP."""
    if documento.es_nota_credito:
        tipo, actualizar_costos = M.TIPO_SALIDA, False
    else:
        tipo, actualizar_costos = M.TIPO_ENTRADA, True
    return registrar_movimiento(
        articulo_id, tipo, cantidad, usuario, _glosa_documento(documento),
        costo=precio_final, documento=documento, proveedor=documento.proveedor,
        actualizar_costos=actualizar_costos,
    )


@transaction.atomic
def registrar_documento_entrada(datos_documento, lineas_detalle, usuario=None):
    """
    Registra un documento de entrada (Factura, Boleta, Guía, Nota de Crédito) con sus líneas,
    actualiza stock, último costo y PMP, y deja los asientos en el Cardex.
    Todo en una transacción: si cualquier línea falla, no se guarda nada.
    """
    if usuario is None:
        raise ValidationError("Todo ingreso requiere un usuario responsable.")
    if not lineas_detalle:
        raise ValidationError("El documento debe contener al menos una línea de detalle.")

    proveedor = datos_documento['proveedor']
    if proveedor.tipo != Proveedor.Tipo.PROVEEDOR or not proveedor.activo:
        raise ValidationError("Debe seleccionar un proveedor activo (los mandantes no emiten documentos de compra).")

    tipo_doc = datos_documento['tipo_documento']
    if tipo_doc not in dict(DocumentoEntrada.TIPOS_DOCUMENTO):
        raise ValidationError("Tipo de documento no válido.")
    numero = str(datos_documento.get('numero_documento') or '').strip()
    if not numero:
        raise ValidationError("Debe ingresar el número del documento.")

    fecha = datos_documento['fecha_emision']
    if isinstance(fecha, str):
        try:
            fecha = datetime.date.fromisoformat(fecha)
        except ValueError:
            raise ValidationError("La fecha de emisión no es válida.")

    if DocumentoEntrada.objects.filter(
        proveedor=proveedor, tipo_documento=tipo_doc, numero_documento__iexact=numero
    ).exclude(estado=DocumentoEntrada.ESTADO_ANULADO).exists():
        raise ValidationError(
            f"Ya existe un documento {dict(DocumentoEntrada.TIPOS_DOCUMENTO)[tipo_doc]} N° {numero} de este proveedor."
        )

    documento = DocumentoEntrada.objects.create(
        proveedor=proveedor, tipo_documento=tipo_doc, numero_documento=numero, fecha_emision=fecha,
        observaciones=datos_documento.get('observaciones', ''), registrado_por=usuario, monto_neto=0,
    )

    total_neto = 0
    for linea in lineas_detalle:
        try:
            articulo_id = int(linea['articulo_id'])
        except (KeyError, TypeError, ValueError):
            raise ValidationError("Cada línea debe indicar un artículo válido.")
        if not Articulo.objects.filter(pk=articulo_id, activo=True).exists():
            raise ValidationError("Uno de los artículos no existe o está desactivado.")

        cantidad = _a_decimal(linea.get('cantidad'), "La cantidad")
        if cantidad <= 0:
            raise ValidationError("La cantidad debe ser mayor a cero en todos los artículos.")

        try:
            precio_base = int(linea['precio_unitario_base'])
        except (KeyError, TypeError, ValueError):
            raise ValidationError("El precio base de cada artículo debe ser un número entero.")
        if precio_base < 0:
            raise ValidationError("El precio base no puede ser negativo.")

        d1 = _a_decimal(linea.get('descuento_1_porcentaje') or 0, "El descuento 1")
        d2 = _a_decimal(linea.get('descuento_2_porcentaje') or 0, "El descuento 2")
        d3 = _a_decimal(linea.get('descuento_3_porcentaje') or 0, "El descuento 3")

        precio_final = calcular_descuentos_sucesivos(precio_base, d1, d2, d3)
        subtotal = calcular_subtotal_linea(precio_final, cantidad)
        total_neto += subtotal

        DetalleDocumento.objects.create(
            documento=documento, articulo_id=articulo_id, cantidad=cantidad,
            precio_unitario_base=precio_base,
            descuento_1_porcentaje=d1, descuento_2_porcentaje=d2, descuento_3_porcentaje=d3,
            precio_unitario_final=precio_final, subtotal_linea=subtotal,
        )
        _movimiento_por_documento(documento, articulo_id, cantidad, precio_final, usuario)

    documento.monto_neto = total_neto
    documento.save(update_fields=['monto_neto'])
    return documento


# ---------------------------------------------------------------------------
# EGRESO / DESPACHO A OBRA (HU-02)
# ---------------------------------------------------------------------------
PREFIJO_FIRMA = 'data:image/png;base64,'


def _validar_firma(firma):
    firma = (firma or '').strip()
    if not firma.startswith(PREFIJO_FIRMA) or len(firma) > 700_000:
        raise ValidationError("Falta la firma de recepción del técnico (o no es válida).")
    try:
        binario = base64.b64decode(firma[len(PREFIJO_FIRMA):], validate=True)
    except (binascii.Error, ValueError):
        raise ValidationError("La firma de recepción no es válida.")
    if not binario.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValidationError("La firma de recepción no es una imagen PNG válida.")
    return firma


def tecnicos_disponibles():
    """Usuarios activos con rol técnico (receptores de materiales), con cualquiera de
    los nombres de grupo registrados: 'tecnico', 'Técnico' o 'Tecnico'."""
    return (get_user_model().objects.filter(is_active=True, groups__name__in=ALIAS_ROLES['tecnico'])
            .distinct().order_by('first_name', 'username'))


def _obtener_tecnico(tecnico_id):
    try:
        tecnico = tecnicos_disponibles().filter(pk=int(tecnico_id)).first()
    except (TypeError, ValueError):
        tecnico = None
    if tecnico is None:
        raise ValidationError("Debe seleccionar un técnico receptor válido.")
    return tecnico


@transaction.atomic
def despachar(solicitud_id, usuario, tecnico_id, firma):
    """Despacha una solicitud pendiente: valida stock, rebaja existencias al PMP vigente,
    emite el vale de salida y registra la firma del técnico. Todo o nada."""
    try:
        solicitud = (SolicitudDespacho.objects.select_for_update()
                     .select_related('obra__mandante').get(pk=solicitud_id))
    except SolicitudDespacho.DoesNotExist:
        raise ValidationError("La solicitud no existe.")

    if solicitud.estado != SolicitudDespacho.Estado.PENDIENTE:
        raise ValidationError("Solo se pueden despachar solicitudes pendientes.")
    if solicitud.obra.estado != Obra.Estado.ACTIVA:
        raise ValidationError("La obra de la solicitud no está activa.")
    tecnico = _obtener_tecnico(tecnico_id)
    firma = _validar_firma(firma)

    detalles = list(solicitud.detalles.select_related('articulo'))
    if not detalles:
        raise ValidationError("La solicitud no tiene artículos.")

    # Se valida el stock de TODAS las líneas antes de tocar nada, para informar todos los faltantes juntos.
    requerido = defaultdict(Decimal)
    for det in detalles:
        requerido[det.articulo_id] += det.cantidad
    faltantes = []
    for art in Articulo.objects.select_for_update().filter(pk__in=requerido.keys()).order_by('pk'):
        if not art.activo:
            faltantes.append(f"'{art.nombre}' está desactivado")
        elif art.stock_actual < requerido[art.pk]:
            faltantes.append(f"'{art.nombre}' (disponible {art.stock_actual}, solicitado {requerido[art.pk]})")
    if faltantes:
        raise ValidationError("Stock insuficiente: " + "; ".join(faltantes) + ".")

    despacho = Despacho.objects.create(solicitud=solicitud, despachado_por=usuario,
                                       tecnico=tecnico, firma_recepcion=firma)
    glosa = f"Vale de salida #{despacho.pk} - Solicitud #{solicitud.pk} - {solicitud.obra} ({solicitud.obra.mandante.razon_social})"
    for det in detalles:
        registrar_movimiento(det.articulo_id, M.TIPO_EGRESO_OBRA, det.cantidad, usuario, glosa,
                             obra=solicitud.obra, tecnico=tecnico, despacho=despacho)

    solicitud.estado = SolicitudDespacho.Estado.DESPACHADA
    solicitud.save(update_fields=['estado'])
    return despacho


@transaction.atomic
def rechazar_solicitud(solicitud_id, usuario, motivo):
    """Bodega rechaza una solicitud (ej. stock insuficiente) y deja el motivo para el supervisor."""
    motivo = (motivo or '').strip()
    if len(motivo) < MIN_JUSTIFICACION:
        raise ValidationError(f"Indique el motivo del rechazo (mínimo {MIN_JUSTIFICACION} caracteres).")
    try:
        solicitud = SolicitudDespacho.objects.select_for_update().get(pk=solicitud_id)
    except SolicitudDespacho.DoesNotExist:
        raise ValidationError("La solicitud no existe.")
    if solicitud.estado != SolicitudDespacho.Estado.PENDIENTE:
        raise ValidationError("Solo se pueden rechazar solicitudes pendientes.")
    solicitud.estado = SolicitudDespacho.Estado.RECHAZADA
    solicitud.motivo_rechazo = f"{motivo} (rechazada por {usuario.get_username()})"
    solicitud.save(update_fields=['estado', 'motivo_rechazo'])
    return solicitud


# ---------------------------------------------------------------------------
# SALIDAS TIPIFICADAS: MERMA, DEVOLUCIONES Y USO INTERNO (HU-04)
# ---------------------------------------------------------------------------
def _saldo_en_obra(obra, articulo_id):
    """Cantidad neta despachada a la obra (egresos - devoluciones) y su costo promedio de egreso."""
    egresos = M.objects.filter(obra=obra, articulo_id=articulo_id, tipo_movimiento=M.TIPO_EGRESO_OBRA)
    devueltas = M.objects.filter(obra=obra, articulo_id=articulo_id, tipo_movimiento=M.TIPO_DEVOLUCION_OBRA)
    total_egresado = sum((m.cantidad for m in egresos), Decimal('0'))
    total_devuelto = sum((m.cantidad for m in devueltas), Decimal('0'))
    valor = sum((m.cantidad * m.costo_unitario for m in egresos), Decimal('0'))
    costo = int((valor / total_egresado).quantize(Decimal('1'), rounding=ROUND_HALF_UP)) if total_egresado else 0
    return total_egresado - total_devuelto, costo


@transaction.atomic
def registrar_salida_tipificada(tipo, articulo_id, cantidad, usuario, justificacion, obra=None, proveedor=None):
    if tipo not in SALIDAS_TIPIFICADAS:
        raise ValidationError("Tipo de movimiento no válido.")
    cantidad_dec = _a_decimal(cantidad, "La cantidad")
    costo = None
    if tipo == M.TIPO_MERMA:
        referencia = "Merma"
    elif tipo == M.TIPO_USO_INTERNO:
        referencia = "Uso interno de bodega"
    elif tipo == M.TIPO_DEVOLUCION_PROVEEDOR:
        referencia = f"Devolución a proveedor {proveedor.razon_social if proveedor else ''}".strip()
    else:
        if obra is None:
            raise ValidationError("La devolución desde obra exige indicar la obra.")
        Articulo.objects.select_for_update().filter(pk=articulo_id).first()  # serializa devoluciones concurrentes
        pendiente, costo = _saldo_en_obra(obra, articulo_id)
        if cantidad_dec > pendiente:
            raise ValidationError(
                f"La obra '{obra}' solo tiene {max(pendiente, Decimal('0'))} unidad(es) de este artículo pendientes de devolver."
            )
        referencia = f"Devolución desde obra {obra}"
    return registrar_movimiento(articulo_id, tipo, cantidad_dec, usuario, referencia, costo=costo,
                                obra=obra if tipo in (M.TIPO_DEVOLUCION_OBRA, M.TIPO_MERMA) else None,
                                proveedor=proveedor if tipo == M.TIPO_DEVOLUCION_PROVEEDOR else None,
                                justificacion=justificacion)


# ---------------------------------------------------------------------------
# INVENTARIO FÍSICO POR SECTOR (HU-05)
# ---------------------------------------------------------------------------
def sectores_disponibles():
    return sorted(set(Articulo.objects.filter(activo=True).values_list('ubicacion_bodega', flat=True)))


@transaction.atomic
def abrir_sesion_inventario(sector, usuario):
    sector = (sector or '').strip()
    articulos = list(Articulo.objects.select_for_update().filter(activo=True, ubicacion_bodega=sector).order_by('nombre'))
    if not articulos:
        raise ValidationError("El sector seleccionado no tiene artículos activos.")
    if SesionInventario.objects.filter(sector=sector, estado=SesionInventario.Estado.ABIERTA).exists():
        raise ValidationError("Ya existe una sesión de inventario abierta para este sector.")
    try:
        with transaction.atomic():
            sesion = SesionInventario.objects.create(sector=sector, abierta_por=usuario)
    except IntegrityError:
        raise ValidationError("Ya existe una sesión de inventario abierta para este sector.")
    DetalleSesionInventario.objects.bulk_create([
        DetalleSesionInventario(sesion=sesion, articulo=a, stock_sistema=a.stock_actual) for a in articulos
    ])
    return sesion


@transaction.atomic
def guardar_conteo(sesion_id, conteos):
    """conteos = {detalle_id: texto}. Texto vacío = aún sin contar. La sesión sigue abierta."""
    sesion = SesionInventario.objects.select_for_update().get(pk=sesion_id)
    if sesion.estado != SesionInventario.Estado.ABIERTA:
        raise ValidationError("La sesión está cerrada: el conteo no se puede modificar.")
    for det in sesion.detalles.select_related('articulo'):
        if det.pk not in conteos:
            continue
        texto = str(conteos[det.pk]).strip()
        if texto == '':
            det.stock_contado = None
        else:
            valor = _a_decimal(texto, f"El conteo de '{det.articulo.nombre}'")
            if valor < 0:
                raise ValidationError(f"El conteo de '{det.articulo.nombre}' no puede ser negativo.")
            det.stock_contado = valor
        det.save()
    return sesion


@transaction.atomic
def cerrar_sesion_inventario(sesion_id, usuario, observaciones=''):
    """Cierra la sesión (irreversible): calcula diferencias, las valoriza y genera los ajustes en el Cardex."""
    sesion = SesionInventario.objects.select_for_update().get(pk=sesion_id)
    if sesion.estado != SesionInventario.Estado.ABIERTA:
        raise ValidationError("La sesión ya está cerrada.")
    observaciones = (observaciones or '').strip()

    detalles = list(sesion.detalles.select_related('articulo').order_by('articulo_id'))
    sin_contar = [d.articulo.nombre for d in detalles if d.stock_contado is None]
    if sin_contar:
        raise ValidationError(f"Faltan {len(sin_contar)} artículo(s) por contar: " + ", ".join(sin_contar[:5])
                              + ("..." if len(sin_contar) > 5 else ""))

    articulos = {a.pk: a for a in Articulo.objects.select_for_update().filter(pk__in=[d.articulo_id for d in detalles])}
    total_valor = 0
    pendientes = []
    for det in detalles:
        art = articulos[det.articulo_id]
        diferencia = det.stock_contado - art.stock_actual
        det.stock_sistema = art.stock_actual
        det.diferencia = diferencia
        det.valor_diferencia = int((diferencia * art.pmp_costo_actual).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        det.save()
        total_valor += det.valor_diferencia
        if diferencia != 0:
            pendientes.append(det)

    if pendientes and len(observaciones) < MIN_JUSTIFICACION:
        raise ValidationError(f"Hay diferencias de stock: ingrese una observación de al menos {MIN_JUSTIFICACION} caracteres que las justifique.")

    for det in pendientes:
        tipo = M.TIPO_AJUSTE_POS if det.diferencia > 0 else M.TIPO_AJUSTE_NEG
        registrar_movimiento(
            det.articulo_id, tipo, abs(det.diferencia), usuario,
            referencia=f"Inventario físico #{sesion.pk} - sector {sesion.sector}",
            justificacion=f"Sistema {det.stock_sistema}, contado {det.stock_contado}. {observaciones}",
            sesion=sesion,
        )

    sesion.estado = SesionInventario.Estado.CERRADA
    sesion.cerrada_por = usuario
    sesion.fecha_cierre = timezone.now()
    sesion.observaciones = observaciones
    sesion.valor_diferencia_total = total_valor
    sesion.save()
    return sesion


SECTOR_CHECKLIST_GENERAL = 'CHECKLIST GENERAL BODEGA'


@transaction.atomic
def registrar_checklist_general(conteos, usuario, observaciones=''):
    """Checklist de toda la bodega. conteos = {articulo_id: texto contado} solo de los
    artículos marcados como revisados. Deja una sesión cerrada con su detalle y, si hay
    diferencias, los ajustes (+/-) en el Cardex a través de cerrar_sesion_inventario()."""
    if not conteos:
        raise ValidationError("Marque como revisado al menos un artículo del checklist.")
    articulos = list(Articulo.objects.select_for_update()
                     .filter(pk__in=conteos.keys(), activo=True).order_by('pk'))
    if len(articulos) != len(conteos):
        raise ValidationError("El checklist incluye artículos que no existen o están desactivados.")
    if SesionInventario.objects.filter(sector=SECTOR_CHECKLIST_GENERAL,
                                       estado=SesionInventario.Estado.ABIERTA).exists():
        raise ValidationError("Ya hay un checklist general en curso. Intente nuevamente en unos segundos.")
    try:
        with transaction.atomic():
            sesion = SesionInventario.objects.create(sector=SECTOR_CHECKLIST_GENERAL, abierta_por=usuario)
    except IntegrityError:
        raise ValidationError("Ya hay un checklist general en curso. Intente nuevamente en unos segundos.")

    detalles = DetalleSesionInventario.objects.bulk_create([
        DetalleSesionInventario(sesion=sesion, articulo=a, stock_sistema=a.stock_actual) for a in articulos
    ])
    guardar_conteo(sesion.pk, {d.pk: conteos[d.articulo_id] for d in detalles})
    return cerrar_sesion_inventario(sesion.pk, usuario, observaciones)


# ---------------------------------------------------------------------------
# RESTOCK: Bodega solicita -> Finanzas aprueba -> Técnico/Bodega recibe e ingresa
# ---------------------------------------------------------------------------
@transaction.atomic
def crear_orden_restock(articulo_id, cantidad, costo_unitario, usuario, proveedor=None, observaciones=''):
    cantidad = _a_decimal(cantidad, "La cantidad")
    if cantidad <= 0:
        raise ValidationError("La cantidad a reponer debe ser mayor a cero.")
    try:
        costo = int(costo_unitario)
    except (TypeError, ValueError):
        raise ValidationError("El costo unitario estimado debe ser un número entero (CLP).")
    if costo < 0:
        raise ValidationError("El costo unitario no puede ser negativo.")
    articulo = Articulo.objects.filter(pk=articulo_id, activo=True).first()
    if articulo is None:
        raise ValidationError("El artículo seleccionado no existe o está desactivado.")
    if proveedor is not None and (proveedor.tipo != Proveedor.Tipo.PROVEEDOR or not proveedor.activo):
        raise ValidationError("El proveedor debe ser una ficha de proveedor activa.")
    return OrdenRestock.objects.create(
        articulo=articulo, proveedor=proveedor, cantidad=cantidad, costo_unitario=costo,
        solicitado_por=usuario, observaciones=(observaciones or '').strip(),
    )


@transaction.atomic
def resolver_orden_restock(orden_id, usuario, aprobar, observacion=''):
    """Finanzas aprueba o rechaza el presupuesto de la orden (rechazar exige motivo)."""
    orden = OrdenRestock.objects.select_for_update().filter(pk=orden_id).first()
    if orden is None:
        raise ValidationError("La orden de restock no existe.")
    if orden.estado != OrdenRestock.ESTADO_PENDIENTE_FINANZAS:
        raise ValidationError("Solo se pueden resolver órdenes pendientes de aprobación de Finanzas.")
    if orden.solicitado_por_id and orden.solicitado_por_id == getattr(usuario, 'pk', None):
        raise ValidationError("Por segregación de funciones, quien solicita el restock no puede aprobar su propio presupuesto.")
    observacion = (observacion or '').strip()
    if not aprobar and len(observacion) < MIN_JUSTIFICACION:
        raise ValidationError(f"Indique el motivo del rechazo (mínimo {MIN_JUSTIFICACION} caracteres).")

    orden.estado = OrdenRestock.ESTADO_APROBADA_FINANZAS if aprobar else OrdenRestock.ESTADO_RECHAZADA
    orden.aprobado_por = usuario
    orden.fecha_aprobacion = timezone.now()
    if observacion:
        etiqueta = 'Finanzas' if aprobar else 'Rechazo Finanzas'
        orden.observaciones = f"{orden.observaciones}\n[{etiqueta}] {observacion}".strip()
    orden.save(update_fields=['estado', 'aprobado_por', 'fecha_aprobacion', 'observaciones'])
    return orden


@transaction.atomic
def recibir_orden_restock(orden_id, usuario, observacion=''):
    """Revisión técnica conforme: ingresa el material al stock por el punto único del Cardex."""
    orden = OrdenRestock.objects.select_for_update().select_related('proveedor').filter(pk=orden_id).first()
    if orden is None:
        raise ValidationError("La orden de restock no existe.")
    if orden.estado != OrdenRestock.ESTADO_APROBADA_FINANZAS:
        raise ValidationError("Solo se puede ingresar al stock una orden con presupuesto aprobado por Finanzas.")
    if orden.aprobado_por_id and orden.aprobado_por_id == getattr(usuario, 'pk', None):
        raise ValidationError("Por segregación de funciones, quien aprobó el presupuesto en Finanzas no puede confirmar la recepción física.")

    movimiento = registrar_movimiento(
        orden.articulo_id, M.TIPO_ENTRADA, orden.cantidad, usuario,
        referencia=f"Restock #{orden.pk} aprobado por Finanzas",
        costo=orden.costo_unitario, proveedor=orden.proveedor,
        actualizar_costos=True, orden_restock=orden,
    )
    orden.estado = OrdenRestock.ESTADO_INSERTADA
    orden.revisado_por = usuario
    orden.fecha_recepcion = timezone.now()
    observacion = (observacion or '').strip()
    if observacion:
        orden.observaciones = f"{orden.observaciones}\n[Revisión técnica] {observacion}".strip()
    orden.save(update_fields=['estado', 'revisado_por', 'fecha_recepcion', 'observaciones'])
    return movimiento


@transaction.atomic
def confirmar_documento_borrador(documento_id, usuario):
    documento = DocumentoEntrada.objects.select_for_update().get(pk=documento_id)
    if documento.estado != DocumentoEntrada.ESTADO_BORRADOR:
        raise ValidationError('Solo se pueden confirmar documentos en borrador.')

    detalles = list(documento.detalles.all())
    if not detalles:
        raise ValidationError('El borrador debe tener al menos una línea.')
    if documento.movimientos_generados.exists():
        raise ValidationError('El borrador ya tiene movimientos de inventario asociados.')

    for detalle in detalles:
        _movimiento_por_documento(documento, detalle.articulo_id, detalle.cantidad,
                                  detalle.precio_unitario_final, usuario)

    documento.estado = DocumentoEntrada.ESTADO_CONFIRMADO
    documento.save(update_fields=['estado'])
    return documento


# ---------------------------------------------------------------------------
# ANULACIÓN CONTROLADA (CONTRA-ASIENTO, HU-12)
# El Kardex (MovimientoInventario) es el único registro: el Cardex de Auditoría es otra
# vista de la misma tabla. El contra-asiento apunta a su original con movimiento_anulado.
# ---------------------------------------------------------------------------
PREFIJO_ANULACION = "ANULADO ID#"


class AnulacionError(ValidationError):
    """Error de negocio al anular. 'codigo' permite a cada vista conservar su mensaje."""

    def __init__(self, mensaje, codigo, **datos):
        super().__init__(mensaje, code=codigo)
        self.codigo = codigo
        self.datos = datos


def movimiento_ya_anulado(mov):
    """True si el movimiento ya tiene su contra-asiento."""
    return M.objects.filter(movimiento_anulado=mov).exists()


@transaction.atomic
def anular_movimiento_inventario(mov_id, usuario, motivo):
    """Genera el contra-asiento de un movimiento: revierte el stock, deja la ANULACION en el
    Kardex enlazada al original (movimiento_anulado) y registra la bitácora."""
    from apps.auditoria.middleware import get_current_ip
    from apps.auditoria.models import BitacoraAuditoria

    motivo = (motivo or '').strip()
    if len(motivo) < MIN_JUSTIFICACION:
        raise AnulacionError(f"Indique el motivo de la anulación (mínimo {MIN_JUSTIFICACION} caracteres).", 'motivo')

    mov = M.objects.select_for_update().select_related('articulo', 'documento').filter(pk=mov_id).first()
    if mov is None:
        raise AnulacionError("El movimiento no existe.", 'no_existe')
    if mov.articulo_id is None:
        raise AnulacionError("Los registros de ingreso/salida de personal no mueven stock.", 'sin_articulo')
    if mov.tipo_movimiento == M.TIPO_ANULACION:
        raise AnulacionError("Este registro ya corresponde a un contra-asiento de anulación.", 'es_anulacion')
    if movimiento_ya_anulado(mov):
        raise AnulacionError(f"El movimiento #{mov.pk} ya fue anulado anteriormente.", 'ya_anulado')

    articulo = Articulo.objects.select_for_update().get(pk=mov.articulo_id)
    stock_anterior = articulo.stock_actual
    if mov.suma_stock:
        # El original sumó stock: la reversa resta y no puede dejar saldo negativo
        nuevo_stock = stock_anterior - mov.cantidad
        direccion = 'REVERSA ENTRADA'
    else:
        nuevo_stock = stock_anterior + mov.cantidad
        direccion = 'REVERSA SALIDA'
    if nuevo_stock < 0:
        raise AnulacionError(
            f"No se puede anular el movimiento #{mov.pk}: el stock de \"{articulo.nombre}\" quedaría negativo "
            f"({nuevo_stock}).", 'stock_negativo', nuevo_stock=nuevo_stock, articulo=articulo.nombre)

    articulo.stock_actual = nuevo_stock
    articulo.save(update_fields=['stock_actual'])

    ahora_str = timezone.localtime(timezone.now()).strftime('%d/%m/%Y %H:%M')
    detalle = (f"{PREFIJO_ANULACION}{mov.pk} ({direccion}) | Por: {usuario.username} | "
               f"Fecha: {ahora_str} | Motivo: {motivo}")
    contra = M.objects.create(
        articulo=articulo, documento=mov.documento, tipo_movimiento=M.TIPO_ANULACION,
        cantidad=mov.cantidad, stock_anterior=stock_anterior, stock_posterior=nuevo_stock,
        costo_unitario=mov.costo_unitario or articulo.pmp_costo_actual or 0,
        usuario=usuario, referencia=detalle[:255], obra=mov.obra, justificacion=motivo,
        movimiento_anulado=mov,
    )
    BitacoraAuditoria.objects.create(
        usuario=usuario, ip_origen=get_current_ip(), modulo='Inventario', accion='ANULAR',
        modelo_afectado='MovimientoInventario', objeto_id=str(mov.pk),
        descripcion=(f"Contra-asiento #{contra.pk} generado sobre el movimiento #{mov.pk} ({articulo.nombre}): "
                     f"stock {stock_anterior} -> {nuevo_stock}. Motivo: {motivo}"),
    )
    return contra
