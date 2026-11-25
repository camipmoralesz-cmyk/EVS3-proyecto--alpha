"""Operaciones de bodega: despachos a obra, salidas tipificadas, inventario físico y restock.
Lo que mueve stock exige el rol 'bodega' (el restock lo recibe también el técnico).
Las reglas de negocio viven en services.py."""
import csv
import logging

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from apps.catalogo.models import Articulo, Categoria
from apps.entidades.models import Proveedor
from apps.usuarios.roles import rol_requerido, tiene_rol
from .forms import AbrirSesionForm, DespachoForm, SalidaTipificadaForm
from .models import Despacho, OrdenRestock, SesionInventario, SolicitudDespacho
from .permisos import bodega_requerida, lectura_cardex
from .services import (
    SECTOR_CHECKLIST_GENERAL, abrir_sesion_inventario, cerrar_sesion_inventario, crear_orden_restock,
    despachar, guardar_conteo, rechazar_solicitud, recibir_orden_restock, registrar_checklist_general,
    registrar_salida_tipificada, resolver_orden_restock,
)

logger = logging.getLogger(__name__)


def _mensaje(e):
    return ' '.join(e.messages)


# ---------------------------------------------------------------- Despachos (HU-02)
@bodega_requerida
def lista_solicitudes(request):
    solicitudes = (SolicitudDespacho.objects.filter(estado=SolicitudDespacho.Estado.PENDIENTE)
                   .select_related('obra__mandante', 'solicitante').prefetch_related('detalles__articulo'))
    despachos = Despacho.objects.select_related('solicitud__obra', 'tecnico')[:10]
    return render(request, 'inventario/lista_solicitudes.html', {'solicitudes': solicitudes, 'despachos': despachos})


@bodega_requerida
@require_http_methods(['GET', 'POST'])
def despachar_solicitud(request, pk):
    solicitud = get_object_or_404(
        SolicitudDespacho.objects.select_related('obra__mandante', 'solicitante').prefetch_related('detalles__articulo'),
        pk=pk)
    if solicitud.estado != SolicitudDespacho.Estado.PENDIENTE:
        messages.warning(request, f"La solicitud #{solicitud.pk} ya fue {solicitud.get_estado_display().lower()}.")
        return redirect('lista_solicitudes')

    form = DespachoForm(request.POST or None)
    if request.method == 'POST':
        if form.is_valid():
            try:
                despacho = despachar(solicitud.pk, request.user, form.cleaned_data['tecnico'].pk,
                                     form.cleaned_data['firma'])
            except ValidationError as e:
                messages.error(request, _mensaje(e))
            except Exception:
                logger.exception("Error inesperado al despachar la solicitud %s", pk)
                messages.error(request, "Ocurrió un error inesperado. No se realizó ningún cambio.")
            else:
                messages.success(request, f"Vale de salida #{despacho.pk} emitido. Stock actualizado.")
                return redirect('comprobante_despacho', pk=despacho.pk)
        else:
            messages.error(request, "Seleccione al técnico receptor y registre su firma antes de confirmar.")

    lineas = [(d, d.articulo.stock_actual >= d.cantidad) for d in solicitud.detalles.all()]
    return render(request, 'inventario/despachar.html', {
        'solicitud': solicitud, 'form': form, 'lineas': lineas,
        'hay_faltantes': any(not ok for _, ok in lineas),
    })


@bodega_requerida
@require_POST
def rechazar_solicitud_view(request, pk):
    try:
        rechazar_solicitud(pk, request.user, request.POST.get('motivo', ''))
    except ValidationError as e:
        messages.error(request, _mensaje(e))
        return redirect('despachar_solicitud', pk=pk)
    messages.success(request, f"Solicitud #{pk} rechazada. El supervisor verá el motivo.")
    return redirect('lista_solicitudes')


@lectura_cardex
def comprobante_despacho(request, pk):
    despacho = get_object_or_404(
        Despacho.objects.select_related('solicitud__obra__mandante', 'despachado_por', 'tecnico'), pk=pk)
    movimientos = despacho.movimientos.select_related('articulo')
    total = sum(m.valor_total for m in movimientos)
    return render(request, 'inventario/comprobante_despacho.html', {
        'despacho': despacho, 'movimientos': movimientos, 'total': total,
    })


# ---------------------------------------------------- Merma / devolución / uso interno (HU-04)
@bodega_requerida
@require_http_methods(['GET', 'POST'])
def salida_tipificada(request):
    form = SalidaTipificadaForm(request.POST or None, initial={'tipo': request.GET.get('tipo')})
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        try:
            mov = registrar_salida_tipificada(
                d['tipo'], d['articulo'].pk, d['cantidad'], request.user, d['justificacion'],
                obra=d.get('obra'), proveedor=d.get('proveedor'))
        except ValidationError as e:
            form.add_error(None, _mensaje(e))
        except Exception:
            logger.exception("Error inesperado al registrar salida tipificada")
            form.add_error(None, "Ocurrió un error inesperado. No se realizó ningún cambio.")
        else:
            messages.success(request, f"{mov.get_tipo_movimiento_display()} registrada: "
                                      f"{mov.cantidad} x {mov.articulo.nombre}. Stock actualizado a {mov.stock_posterior}.")
            return redirect('salida_tipificada')
    return render(request, 'inventario/salida_tipificada.html', {'form': form})


# ----------------------------------------------------------- Inventario físico (HU-05)
@bodega_requerida
@require_http_methods(['GET', 'POST'])
def lista_sesiones_inventario(request):
    form = AbrirSesionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            sesion = abrir_sesion_inventario(form.cleaned_data['sector'], request.user)
        except ValidationError as e:
            messages.error(request, _mensaje(e))
        else:
            messages.success(request, f"Sesión de inventario #{sesion.pk} abierta para el sector '{sesion.sector}'.")
            return redirect('detalle_sesion_inventario', pk=sesion.pk)
    sesiones = SesionInventario.objects.select_related('abierta_por', 'cerrada_por')[:30]
    return render(request, 'inventario/inventario_fisico_lista.html', {'form': form, 'sesiones': sesiones})


@bodega_requerida
@require_http_methods(['GET', 'POST'])
def detalle_sesion_inventario(request, pk):
    sesion = get_object_or_404(SesionInventario.objects.select_related('abierta_por', 'cerrada_por'), pk=pk)

    if request.method == 'POST' and sesion.estado == SesionInventario.Estado.ABIERTA:
        conteos = {}
        for clave, valor in request.POST.items():
            if clave.startswith('conteo_') and clave[7:].isdigit():
                conteos[int(clave[7:])] = valor
        try:
            guardar_conteo(sesion.pk, conteos)
            if 'cerrar' in request.POST:
                cerrar_sesion_inventario(sesion.pk, request.user, request.POST.get('observaciones', ''))
                messages.success(request, f"Sesión #{sesion.pk} cerrada. Se generaron los movimientos de regularización en el Cardex.")
            else:
                messages.success(request, "Conteo guardado. La sesión sigue abierta.")
        except ValidationError as e:
            messages.error(request, _mensaje(e))
        return redirect('detalle_sesion_inventario', pk=pk)

    detalles = sesion.detalles.select_related('articulo')
    return render(request, 'inventario/inventario_fisico_detalle.html', {
        'sesion': sesion, 'detalles': detalles,
        'contados': sum(1 for d in detalles if d.stock_contado is not None),
    })


@rol_requerido('bodega', 'tecnico', 'gerencia')
@require_http_methods(['GET', 'POST'])
def checklist_inventario_bodega(request):
    """Checklist de todos los artículos activos. Técnico y Gerencia lo consultan;
    solo Bodega lo envía, porque cerrar el checklist ajusta stock en el Cardex."""
    puede_registrar = tiene_rol(request.user, 'bodega')
    if request.method == 'POST':
        if not puede_registrar:
            raise PermissionDenied
        conteos = {}
        for clave in request.POST.getlist('revisado'):
            if clave.isdigit():
                conteos[int(clave)] = request.POST.get(f'contado_{clave}', '')
        try:
            sesion = registrar_checklist_general(conteos, request.user, request.POST.get('observaciones', ''))
        except ValidationError as e:
            messages.error(request, _mensaje(e))
        else:
            ajustes = sesion.movimientos.count()
            messages.success(request, f"Checklist #{sesion.pk} registrado: {sesion.detalles.count()} artículo(s) revisados, "
                                      f"{ajustes} ajuste(s) en el Cardex (valorización ${sesion.valor_diferencia_total}).")
            return redirect('checklist_inventario_bodega')

    articulos = Articulo.objects.filter(activo=True).select_related('categoria').order_by('nombre')
    checklists = (SesionInventario.objects.filter(sector=SECTOR_CHECKLIST_GENERAL)
                  .select_related('cerrada_por')[:5])
    return render(request, 'inventario/inventario_checklist.html', {
        'articulos': articulos,
        'categorias': Categoria.objects.filter(articulos__activo=True).distinct().order_by('nombre'),
        'checklists': checklists,
        'puede_registrar': puede_registrar,
    })


# --------------------------------------------- Restock (Bodega -> Finanzas -> Técnico)
@rol_requerido('bodega', 'finanzas', 'tecnico', 'gerencia')
@require_http_methods(['GET', 'POST'])
def lista_restock(request):
    puede_solicitar = tiene_rol(request.user, 'bodega')
    if request.method == 'POST':
        if not puede_solicitar:
            raise PermissionDenied
        proveedor = None
        if request.POST.get('proveedor', '').isdigit():
            proveedor = Proveedor.objects.filter(pk=int(request.POST['proveedor'])).first()
        try:
            orden = crear_orden_restock(
                request.POST.get('articulo'), request.POST.get('cantidad'), request.POST.get('costo_unitario'),
                request.user, proveedor=proveedor, observaciones=request.POST.get('observaciones', ''))
        except ValidationError as e:
            messages.error(request, _mensaje(e))
        else:
            messages.success(request, f"Restock #{orden.pk} enviado a Finanzas para aprobar el presupuesto "
                                      f"(${orden.monto_total}).")
        return redirect('lista_restock')

    ordenes = OrdenRestock.objects.select_related(
        'articulo', 'proveedor', 'solicitado_por', 'aprobado_por', 'revisado_por')
    etapas = [(valor, etiqueta, [o for o in ordenes if o.estado == valor]) for valor, etiqueta in OrdenRestock.ESTADOS]
    return render(request, 'inventario/restock_lista.html', {
        'etapas': etapas,
        'articulos': Articulo.objects.filter(activo=True).order_by('nombre'),
        'proveedores': Proveedor.objects.filter(tipo=Proveedor.Tipo.PROVEEDOR, activo=True).order_by('razon_social'),
        'puede_solicitar': puede_solicitar,
        # Los flags solo ocultan botones; los endpoints validan el rol por su cuenta
        'puede_aprobar': tiene_rol(request.user, 'finanzas'),
        'puede_recibir': tiene_rol(request.user, 'tecnico', 'bodega'),
    })


@rol_requerido('finanzas')
@require_POST
def aprobar_restock_finanzas(request, pk):
    aprobar = request.POST.get('decision') != 'rechazar'
    try:
        orden = resolver_orden_restock(pk, request.user, aprobar, request.POST.get('observacion', ''))
    except ValidationError as e:
        messages.error(request, _mensaje(e))
    else:
        if aprobar:
            messages.success(request, f"Presupuesto del restock #{orden.pk} aprobado (${orden.monto_total}). "
                                      f"Queda pendiente la revisión técnica.")
        else:
            messages.warning(request, f"Restock #{orden.pk} rechazado por Finanzas.")
    return redirect('lista_restock')


# Ítems que el técnico debe confirmar antes de ingresar el material al stock
CHECKLIST_RECEPCION = ('check_cantidad', 'check_estado', 'check_especificacion')


@rol_requerido('tecnico', 'bodega')
@require_POST
def confirmar_recepcion_restock(request, pk):
    if not all(request.POST.get(c) for c in CHECKLIST_RECEPCION):
        messages.error(request, "Complete el checklist de conformidad técnica (cantidad, estado y especificación) "
                                "antes de ingresar el material.")
        return redirect('lista_restock')
    try:
        mov = recibir_orden_restock(pk, request.user, request.POST.get('observacion', ''))
    except ValidationError as e:
        messages.error(request, _mensaje(e))
    else:
        messages.success(request, f"Restock #{pk} ingresado: {mov.cantidad} x {mov.articulo.nombre}. "
                                  f"Stock actualizado a {mov.stock_posterior}.")
    return redirect('lista_restock')


@lectura_cardex
def exportar_sesion_inventario(request, pk):
    """Exporta la sesión a un archivo que abre Excel (CSV con separador ';' y UTF-8)."""
    sesion = get_object_or_404(SesionInventario, pk=pk)
    respuesta = HttpResponse(content_type='text/csv; charset=utf-8')
    respuesta['Content-Disposition'] = f'attachment; filename="inventario_fisico_{sesion.pk}.csv"'
    respuesta.write('\ufeff')  # BOM para que Excel respete los acentos
    w = csv.writer(respuesta, delimiter=';')
    w.writerow([f"Inventario físico #{sesion.pk}", f"Sector: {sesion.sector}", sesion.get_estado_display()])
    w.writerow(['Código', 'Artículo', 'Stock sistema', 'Stock contado', 'Diferencia', 'Valorización (CLP)'])
    for d in sesion.detalles.select_related('articulo'):
        w.writerow([_celda(d.articulo.codigo_interno), _celda(d.articulo.nombre), d.stock_sistema,
                    '' if d.stock_contado is None else d.stock_contado, d.diferencia, d.valor_diferencia])
    w.writerow(['', '', '', '', 'Total', sesion.valor_diferencia_total])
    return respuesta


def _celda(valor):
    """Evita inyección de fórmulas al abrir el CSV en Excel."""
    valor = str(valor)
    return "'" + valor if valor[:1] in ('=', '+', '-', '@') else valor
