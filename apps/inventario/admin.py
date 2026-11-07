from django.contrib import admin
from .models import DocumentoEntrada, DetalleDocumento, MovimientoInventario

class DetalleDocumentoInline(admin.TabularInline):
    model = DetalleDocumento
    extra = 0
    readonly_fields = ('precio_unitario_final', 'subtotal_linea')

@admin.register(DocumentoEntrada)
class DocumentoEntradaAdmin(admin.ModelAdmin):
    list_display = ('numero_documento', 'tipo_documento', 'proveedor', 'fecha_emision', 'monto_neto', 'estado')
    list_filter = ('tipo_documento', 'estado', 'fecha_emision')
    search_fields = ('numero_documento', 'proveedor__razon_social', 'proveedor__rut')
    inlines = [DetalleDocumentoInline]

@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    list_display = ('articulo', 'tipo_movimiento', 'cantidad', 'stock_anterior', 'stock_posterior', 'costo_unitario', 'fecha', 'usuario')
    list_filter = ('tipo_movimiento', 'fecha')
    search_fields = ('articulo__codigo_interno', 'articulo__nombre', 'referencia')
    readonly_fields = ('articulo', 'documento', 'tipo_movimiento', 'cantidad', 'stock_anterior', 'stock_posterior', 'costo_unitario', 'fecha', 'usuario', 'referencia')
