import json
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import JsonResponse
from django.core.exceptions import ValidationError
from django.views.decorators.http import require_GET
from apps.catalogo.models import Articulo
from apps.entidades.models import Proveedor
from .models import DocumentoEntrada, DetalleDocumento, MovimientoInventario
from .forms import DocumentoEntradaForm
from .services import registrar_documento_entrada, calcular_descuentos_sucesivos, calcular_subtotal_linea

def registro_documento(request):
    """
    Vista para registrar un documento de entrada con múltiples líneas de ítems
    y cálculo en tiempo real de hasta 3 descuentos sucesivos.
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
                lineas_json = request.POST.get('lineas_json', '[]')
                lineas_raw = json.loads(lineas_json)

            if not proveedor_id:
                raise ValidationError("Debe seleccionar un proveedor.")
            if not tipo_documento:
                raise ValidationError("Debe indicar el tipo de documento.")
            if not numero_documento:
                raise ValidationError("Debe ingresar el número del documento.")
            if not fecha_emision:
                raise ValidationError("Debe ingresar la fecha de emisión.")
            if not lineas_raw:
                raise ValidationError("Debe ingresar al menos una línea de artículo.")

            proveedor = get_object_or_404(Proveedor, pk=proveedor_id)

            datos_documento = {
                'proveedor': proveedor,
                'tipo_documento': tipo_documento,
                'numero_documento': numero_documento,
                'fecha_emision': fecha_emision,
                'observaciones': observaciones,
            }

            usuario = request.user if request.user.is_authenticated else None
            documento = registrar_documento_entrada(datos_documento, lineas_raw, usuario=usuario)

            msg_exito = f"{documento.get_tipo_documento_display()} N° {documento.numero_documento} registrado exitosamente. Stock actualizado en tiempo real."

            if is_ajax:
                return JsonResponse({
                    'status': 'ok',
                    'message': msg_exito,
                    'documento_id': documento.id,
                    'redirect_url': f"/inventario/documentos/{documento.id}/"
                })

            messages.success(request, msg_exito)
            return redirect('detalle_documento', pk=documento.pk)

        except (ValidationError, Exception) as e:
            error_msg = e.message if hasattr(e, 'message') else str(e)
            if is_ajax:
                return JsonResponse({'status': 'error', 'message': error_msg}, status=400)
            messages.error(request, f"Error al registrar documento: {error_msg}")

    form = DocumentoEntradaForm()
    proveedores = Proveedor.objects.filter(activo=True)
    articulos = Articulo.objects.all().order_by('nombre')
    
    return render(request, 'inventario/registro_documento.html', {
        'form': form,
        'proveedores': proveedores,
        'articulos': articulos,
    })


def lista_documentos(request):
    """
    Listado histórico de documentos de entrada registrados.
    """
    documentos = DocumentoEntrada.objects.select_related('proveedor', 'registrado_por').prefetch_related('detalles').all()
    return render(request, 'inventario/lista_documentos.html', {
        'documentos': documentos
    })


def detalle_documento(request, pk):
    """
    Detalle completo de un documento y sus líneas con desglose de descuentos.
    """
    documento = get_object_or_404(DocumentoEntrada.objects.select_related('proveedor', 'registrado_por'), pk=pk)
    detalles = documento.detalles.select_related('articulo').all()
    movimientos = documento.movimientos_generados.select_related('articulo').all()

    return render(request, 'inventario/detalle_documento.html', {
        'documento': documento,
        'detalles': detalles,
        'movimientos': movimientos,
    })


def inventario_stock(request):
    """
    Vista de inventario / stock en tiempo real con alertas de stock crítico y mínimo.
    """
    articulos = Articulo.objects.select_related('categoria').all().order_by('nombre')
    return render(request, 'inventario/stock.html', {
        'articulos': articulos
    })


def historial_movimientos(request):
    """
    Log de auditoría de movimientos de inventario.
    """
    movimientos = MovimientoInventario.objects.select_related('articulo', 'documento', 'usuario').all()[:100]
    return render(request, 'inventario/movimientos.html', {
        'movimientos': movimientos
    })


@require_GET
def api_articulo_info(request, pk):
    """
    API JSON que retorna stock y costo actual de un artículo para la interfaz interactiva.
    """
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
