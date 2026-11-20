"""Operaciones de bodega: despachos a obra, salidas tipificadas e inventario físico.
Todas exigen el rol 'bodega'. Las reglas de negocio viven en services.py."""
import csv
import logging

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from .forms import AbrirSesionForm, DespachoForm, SalidaTipificadaForm
from .models import Despacho, SesionInventario, SolicitudDespacho
from .permisos import bodega_requerida, lectura_cardex
from .services import (
    abrir_sesion_inventario, cerrar_sesion_inventario, despachar, guardar_conteo,
    rechazar_solicitud, registrar_salida_tipificada,
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
