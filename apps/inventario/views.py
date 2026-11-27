import json
import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.catalogo.models import Articulo
from apps.entidades.models import Proveedor
from apps.finanzas.utils import bloquear_escrituras_finanzas
from apps.usuarios.roles import rol_requerido
from .forms import DocumentoEntradaForm
from .models import DocumentoEntrada, MovimientoInventario
from .permisos import bodega_requerida, lectura_cardex, lectura_inventario
from .services import confirmar_documento_borrador, registrar_documento_entrada

logger = logging.getLogger(__name__)


@login_required
@bodega_requerida
@bloquear_escrituras_finanzas
def registro_documento(request):
    """
    Registro de un documento de entrada (factura, boleta, guía, nota de crédito) con múltiples
    líneas y hasta 3 descuentos sucesivos por línea. Solo Bodega / Logística.
    """
    if request.method == 'POST':
        # Detectar si viene por JSON (AJAX) o multipart/form-data
        is_ajax = request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json'

        try:
            if request.content_type == 'application/json':
                payload = json.loads(request.body.decode('utf-8'))
                proveedor_id = payload.get('proveedor')
                tipo_documento = payload.get('tipo_documento')
                numero_documento = payload.get('numero_documento')
                fecha_emision = payload.get('fecha_emision')
                observaciones = payload.get('observaciones', '')
                lineas_raw = payload.get('lineas', [])
            else:
                proveedor_id = request.POST.get('proveedor')
                tipo_documento = request.POST.get('tipo_documento')
                numero_documento = request.POST.get('numero_documento')
                fecha_emision = request.POST.get('fecha_emision')
                observaciones = request.POST.get('observaciones', '')
                lineas_raw = json.loads(request.POST.get('lineas_json', '[]'))

            if not proveedor_id:
                raise ValidationError("Debe seleccionar un proveedor.")
            if not tipo_documento:
                raise ValidationError("Debe indicar el tipo de documento.")
            if not numero_documento:
                raise ValidationError("Debe ingresar el número del documento.")
            if not fecha_emision:
                raise ValidationError("Debe ingresar la fecha de emisión.")
            if not lineas_raw or not isinstance(lineas_raw, list):
                raise ValidationError("Debe ingresar al menos una línea de artículo.")

            # Bodega solo selecciona proveedores existentes, activos y de tipo proveedor.
            proveedor = Proveedor.objects.filter(
                pk=proveedor_id, activo=True, tipo=Proveedor.Tipo.PROVEEDOR).first()
            if proveedor is None:
                raise ValidationError("El proveedor seleccionado no existe o no está activo.")

            documento = registrar_documento_entrada({
                'proveedor': proveedor,
                'tipo_documento': tipo_documento,
                'numero_documento': numero_documento,
                'fecha_emision': fecha_emision,
                'observaciones': observaciones,
            }, lineas_raw, usuario=request.user)

            msg_exito = (f"{documento.get_tipo_documento_display()} N° {documento.numero_documento} "
                         f"registrado exitosamente. Stock actualizado en tiempo real.")
            if is_ajax:
                return JsonResponse({
                    'status': 'ok',
                    'message': msg_exito,
                    'documento_id': documento.id,
                    'redirect_url': f"/inventario/documentos/{documento.id}/"
                })
            messages.success(request, msg_exito)
            return redirect('detalle_documento', pk=documento.pk)

        except ValidationError as e:
            error_msg = ' '.join(e.messages)
        except (ValueError, TypeError, KeyError):
            error_msg = "Los datos enviados no son válidos. Revise el formulario."
        except Exception:
            # Los detalles técnicos quedan solo en el log interno (estándar de programación segura).
            logger.exception("Error inesperado al registrar documento de entrada")
            error_msg = "Ocurrió un error inesperado al registrar el documento. No se guardó ningún cambio."

        if is_ajax:
            return JsonResponse({'status': 'error', 'message': error_msg}, status=400)
        messages.error(request, f"Error al registrar documento: {error_msg}")

    form = DocumentoEntradaForm()
    return render(request, 'inventario/registro_documento.html', {
        'form': form,
        'proveedores': form.fields['proveedor'].queryset,
        'articulos': Articulo.objects.filter(activo=True).order_by('nombre'),
    })


@lectura_cardex
def lista_documentos(request):
    """Listado histórico de documentos de entrada registrados (con valorización)."""
    documentos = DocumentoEntrada.objects.select_related('proveedor', 'registrado_por').prefetch_related('detalles')
    return render(request, 'inventario/lista_documentos.html', {'documentos': documentos})


@lectura_cardex
def detalle_documento(request, pk):
    """Detalle de un documento y sus líneas con desglose de descuentos."""
    documento = get_object_or_404(DocumentoEntrada.objects.select_related('proveedor', 'registrado_por'), pk=pk)
    return render(request, 'inventario/detalle_documento.html', {
        'documento': documento,
        'detalles': documento.detalles.select_related('articulo'),
        'movimientos': documento.movimientos_generados.select_related('articulo'),
    })


@rol_requerido('bodega')
@require_POST
def confirmar_borrador(request, pk):
    try:
        documento = confirmar_documento_borrador(pk, request.user)
    except DocumentoEntrada.DoesNotExist as error:
        raise Http404 from error
    except ValidationError as error:
        messages.error(request, 'No se pudo confirmar el borrador: ' + '; '.join(error.messages))
    else:
        messages.success(
            request,
            f'{documento.get_tipo_documento_display()} N° {documento.numero_documento} confirmado. El inventario fue actualizado.',
        )
    return redirect('detalle_documento', pk=pk)


@lectura_inventario
def inventario_stock(request):
    """Inventario / stock en tiempo real con alertas de stock crítico y mínimo."""
    articulos = Articulo.objects.select_related('categoria').filter(activo=True).order_by('nombre')
    return render(request, 'inventario/stock.html', {'articulos': articulos})


@lectura_cardex
def historial_movimientos(request):
    """Cardex: historial de movimientos. SOLO LECTURA (no existe ninguna acción de editar ni borrar)."""
    movimientos = MovimientoInventario.objects.select_related('articulo', 'documento', 'usuario', 'obra')
    q = request.GET.get('q', '').strip()
    tipo = request.GET.get('tipo', '').strip()
    if q:
        movimientos = movimientos.filter(
            Q(articulo__nombre__icontains=q) | Q(articulo__codigo_interno__icontains=q)
            | Q(referencia__icontains=q) | Q(usuario__username__icontains=q)
        )
    if tipo in dict(MovimientoInventario.TIPOS_MOVIMIENTO):
        movimientos = movimientos.filter(tipo_movimiento=tipo)
    pagina = Paginator(movimientos, 50).get_page(request.GET.get('page'))
    return render(request, 'inventario/movimientos.html', {
        'movimientos': pagina, 'q': q, 'tipo_seleccionado': tipo,
        'tipos': MovimientoInventario.TIPOS_MOVIMIENTO,
    })


@lectura_inventario
@require_GET
def api_articulo_info(request, pk):
    """API JSON: stock y costo actual de un artículo para la interfaz interactiva."""
    articulo = get_object_or_404(Articulo, pk=pk)
    return JsonResponse({
        'id': articulo.id,
        'codigo_interno': articulo.codigo_interno,
        'nombre': articulo.nombre,
        'unidad_medida': articulo.get_unidad_medida_display(),
        'stock_actual': float(articulo.stock_actual),
        'ultimo_costo_compra': articulo.ultimo_costo_compra,
        'pmp_costo_actual': articulo.pmp_costo_actual,
        'ubicacion': articulo.ubicacion_bodega,
    })
