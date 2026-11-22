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
from apps.entidades.models import Proveedor
from apps.obras.models import Obra
from .models import (
    DetalleDocumento, DetalleSesionInventario, DetalleSolicitud, Despacho, DocumentoEntrada,
    MovimientoInventario as M, SesionInventario, SolicitudDespacho,
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
                         sesion=None, actualizar_costos=False):
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
        # Único lugar donde cambian el último costo y el PMP: siempre con un documento de respaldo.
        if tipo != M.TIPO_ENTRADA or costo is None or documento is None:
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
    )


# ---------------------------------------------------------------------------
# INGRESO DE DOCUMENTOS TRIBUTARIOS (HU-01)
# ---------------------------------------------------------------------------
def _aplicar_detalle_en_inventario(documento, detalle, articulo, usuario):
    cantidad = detalle.cantidad
    precio_final = detalle.precio_unitario_final
    stock_anterior = articulo.stock_actual
    es_nota_credito = documento.tipo_documento == DocumentoEntrada.TIPO_NOTA_CREDITO

    if es_nota_credito:
        if stock_anterior < cantidad:
            raise ValidationError(
                f"Stock insuficiente para aplicar Nota de Crédito en '{articulo.nombre}'. "
                f"Stock actual: {stock_anterior}, requerido: {cantidad}"
            )
        nuevo_stock = stock_anterior - cantidad
        tipo_movimiento = MovimientoInventario.TIPO_SALIDA
        referencia = (
            f"Nota de Crédito N° {documento.numero_documento} - "
            f"{documento.proveedor.razon_social}"
        )
    else:
        nuevo_stock = stock_anterior + cantidad
        tipo_movimiento = MovimientoInventario.TIPO_ENTRADA
        referencia = (
            f"{documento.get_tipo_documento_display()} N° "
            f"{documento.numero_documento} - {documento.proveedor.razon_social}"
        )
        articulo.ultimo_costo_compra = precio_final
        if nuevo_stock > 0:
            costo_anterior_total = (
                Decimal(str(stock_anterior))
                * Decimal(str(articulo.pmp_costo_actual))
            )
            costo_nuevo_total = cantidad * Decimal(str(precio_final))
            pmp_calculado = (
                costo_anterior_total + costo_nuevo_total
            ) / Decimal(str(nuevo_stock))
            articulo.pmp_costo_actual = int(
                pmp_calculado.quantize(Decimal('1'), rounding=ROUND_HALF_UP)
            )
        else:
            articulo.pmp_costo_actual = precio_final

    articulo.stock_actual = nuevo_stock
    articulo.save()
    MovimientoInventario.objects.create(
        articulo=articulo,
        documento=documento,
        tipo_movimiento=tipo_movimiento,
        cantidad=cantidad,
        stock_anterior=stock_anterior,
        stock_posterior=nuevo_stock,
        costo_unitario=precio_final,
        usuario=usuario,
        referencia=referencia,
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
    tipo_documento = datos_documento['tipo_documento']
    numero_documento = str(datos_documento['numero_documento']).strip()
    tipos_validos = {tipo for tipo, _ in DocumentoEntrada.TIPOS_DOCUMENTO}
    if tipo_documento not in tipos_validos:
        raise ValidationError("El tipo de documento seleccionado no es válido.")
    if not numero_documento:
        raise ValidationError("El número del documento es obligatorio.")
    if not proveedor.activo or proveedor.tipo != proveedor.Tipo.PROVEEDOR:
        raise ValidationError("Debe seleccionar un proveedor activo.")
    if DocumentoEntrada.objects.filter(
        proveedor=proveedor,
        tipo_documento=tipo_documento,
        numero_documento=numero_documento,
    ).exists():
        raise ValidationError("Ya existe un documento con ese tipo y número para este proveedor.")

    # 1. Crear encabezado del documento
    tipo_doc = datos_documento['tipo_documento']
    if tipo_doc == 'GUIA':
        tipo_doc = DocumentoEntrada.TIPO_GUIA

    documento = DocumentoEntrada.objects.create(
<<<<<<< HEAD
        proveedor=datos_documento['proveedor'],
        tipo_documento=tipo_doc,
        numero_documento=datos_documento['numero_documento'].strip(),
=======
        proveedor=proveedor,
        tipo_documento=tipo_documento,
        numero_documento=numero_documento,
>>>>>>> origin/ramaBenja
        fecha_emision=datos_documento['fecha_emision'],
        observaciones=datos_documento.get('observaciones', ''),
        registrado_por=usuario,
        monto_neto=0)
    proveedor = datos_documento['proveedor']
    if proveedor.tipo != Proveedor.Tipo.PROVEEDOR or not proveedor.activo:
        raise ValidationError("Debe seleccionar un proveedor activo (los mandantes no emiten documentos de compra).")

    tipo_doc = datos_documento['tipo_documento']
    if tipo_doc not in dict(DocumentoEntrada.TIPOS_DOCUMENTO):
        raise ValidationError("Tipo de documento no válido.")
    numero = (datos_documento['numero_documento'] or '').strip()
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

    es_nc = documento.es_nota_credito
    glosa = f"{documento.get_tipo_documento_display()} N° {numero} - {proveedor.razon_social}"
    total = 0
    total_neto_acumulado = 0

    for linea in lineas_detalle:
<<<<<<< HEAD
        articulo_id = linea['articulo_id']
        cantidad = Decimal(str(linea['cantidad']))
        precio_raw = linea.get('precio_unitario_base', linea.get('precio_unitario', 0))
        precio_base = int(Decimal(str(precio_raw or 0)))
        d1 = Decimal(str(linea.get('descuento_1_porcentaje', linea.get('descuento_1', 0)) or 0))
        d2 = Decimal(str(linea.get('descuento_2_porcentaje', linea.get('descuento_2', 0)) or 0))
        d3 = Decimal(str(linea.get('descuento_3_porcentaje', linea.get('descuento_3', 0)) or 0))
        cantidad = _a_decimal(linea.get('cantidad'), "La cantidad")
        if cantidad <= 0:
            raise ValidationError("La cantidad debe ser mayor a cero en todos los artículos.")
        try:
            precio_base = int(linea['precio_unitario_base'])
        except (KeyError, TypeError, ValueError):
            raise ValidationError("El precio base de cada artículo debe ser un número entero.")
        if precio_base < 0:
            raise ValidationError("El precio base no puede ser negativo.")
=======
        try:
            articulo_id = int(linea['articulo_id'])
            cantidad = Decimal(str(linea['cantidad']))
            precio_base = int(linea['precio_unitario_base'])
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise ValidationError("Cada línea debe incluir artículo, cantidad y precio base válidos.")
        if not cantidad.is_finite():
            raise ValidationError("La cantidad debe ser un número válido.")
>>>>>>> origin/ramaBenja
        d1 = Decimal(str(linea.get('descuento_1_porcentaje', 0) or 0))
        d2 = Decimal(str(linea.get('descuento_2_porcentaje', 0) or 0))
        d3 = Decimal(str(linea.get('descuento_3_porcentaje', 0) or 0))

        precio_final = calcular_descuentos_sucesivos(precio_base, d1, d2, d3)
        subtotal = calcular_subtotal_linea(precio_final, cantidad)
        total += subtotal

        articulo_id = linea.get('articulo_id')
        if not Articulo.objects.filter(pk=articulo_id, activo=True).exists():
            raise ValidationError("Uno de los artículos no existe o está desactivado.")

        DetalleDocumento.objects.create(
            documento=documento, articulo_id=articulo_id, cantidad=cantidad,
            precio_unitario_base=precio_base,
            descuento_1_porcentaje=d1,
            descuento_2_porcentaje=d2, 
            descuento_3_porcentaje=d3,
            precio_unitario_final=precio_final, 
            subtotal_linea=subtotal,
        )

<<<<<<< HEAD
        if es_nc:
            # La nota de crédito resta existencias y mantiene el PMP vigente.
            registrar_movimiento(articulo_id, M.TIPO_SALIDA, cantidad, usuario, glosa,
                                 costo=precio_final, documento=documento)
=======
        # 3. Bloquear y actualizar el artículo (con select_for_update para prevenir race conditions)
        try:
            articulo = Articulo.objects.select_for_update().get(pk=articulo_id)
        except Articulo.DoesNotExist:
            raise ValidationError("Uno de los artículos seleccionados ya no existe.")
        stock_anterior = articulo.stock_actual

        if es_nota_credito:
            # Nota de crédito descuenta stock
            if stock_anterior < cantidad:
                raise ValidationError(
                    f"Stock insuficiente para aplicar Nota de Crédito en '{articulo.nombre}'. "
                    f"Stock actual: {stock_anterior}, requerido: {cantidad}"
                )
            nuevo_stock = stock_anterior - cantidad
            tipo_mov = MovimientoInventario.TIPO_SALIDA
            glosa = f"Nota de Crédito N° {documento.numero_documento} - {documento.proveedor.razon_social}"
>>>>>>> origin/ramaBenja
        else:
            # Factura, boleta y guía suman existencias y recalculan el PMP.
            registrar_movimiento(articulo_id, M.TIPO_ENTRADA, cantidad, usuario, glosa,
                                 costo=precio_final, documento=documento, actualizar_costos=True)

            # Actualizar precios de compra y PMP (Precio Medio Ponderado)
            articulo.ultimo_costo_compra = precio_final
            if nuevo_stock > 0:
                costo_anterior_total = Decimal(str(stock_anterior)) * Decimal(str(articulo.pmp_costo_actual))
                costo_nuevo_total = cantidad * Decimal(str(precio_final))
                pmp_calculado = (costo_anterior_total + costo_nuevo_total) / Decimal(str(nuevo_stock))
                articulo.pmp_costo_actual = int(pmp_calculado.quantize(Decimal('1'), rounding=ROUND_HALF_UP))
            else:
                articulo.pmp_costo_actual = precio_final

        articulo.stock_actual = nuevo_stock
        articulo.save()

        # 4. Registrar en MovimientoInventario (log de auditoría)
        MovimientoInventario.objects.create(
            articulo=articulo,
            documento=documento,
            tipo_movimiento=tipo_mov,
            cantidad=cantidad,
            stock_anterior=stock_anterior,
            stock_posterior=nuevo_stock,
            costo_unitario=precio_final,
            usuario=usuario,
            referencia=glosa)
# 3. Bloquear y actualizar el artículo vía punto único de escritura al Kardex
        articulo = Articulo.objects.select_for_update().get(pk=articulo_id)
        if es_nc:
            registrar_movimiento(
                articulo_id,
                M.TIPO_SALIDA,
                cantidad,
                usuario,
                glosa,
                costo=precio_final,
                documento=documento,
                proveedor=documento.proveedor,
                actualizar_costos=False,
            )
        else:
            registrar_movimiento(
                articulo_id,
                M.TIPO_ENTRADA,
                cantidad,
                usuario,
                glosa,
                costo=precio_final,
                documento=documento,
                proveedor=documento.proveedor,
                actualizar_costos=True,
            )

    # Actualizar monto total en el documento
    documento.monto_neto = total_neto_acumulado
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
    """Usuarios activos del grupo 'tecnico' (receptores de materiales)."""
    return get_user_model().objects.filter(is_active=True, groups__name='tecnico').distinct().order_by('first_name', 'username')


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
                                obra=obra if tipo == M.TIPO_DEVOLUCION_OBRA else None,
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
        articulo = Articulo.objects.select_for_update().get(pk=detalle.articulo_id)
        _aplicar_detalle_en_inventario(documento, detalle, articulo, usuario)

    documento.estado = DocumentoEntrada.ESTADO_CONFIRMADO
    documento.save(update_fields=['estado'])
    return documento

