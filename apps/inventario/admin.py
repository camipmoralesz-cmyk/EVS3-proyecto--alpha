from django.contrib import admin
from .models import (
    DetalleDocumento, DetalleSolicitud, DocumentoEntrada, MovimientoInventario, SolicitudDespacho,
)


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

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MovimientoInventario)
class MovimientoInventarioAdmin(admin.ModelAdmin):
    """Cardex de solo lectura: no se agrega, edita ni elimina desde el admin."""
    list_display = ('articulo', 'tipo_movimiento', 'cantidad', 'stock_anterior', 'stock_posterior',
                    'costo_unitario', 'fecha', 'usuario')
    list_filter = ('tipo_movimiento', 'fecha')
    search_fields = ('articulo__codigo_interno', 'articulo__nombre', 'referencia')

    def get_readonly_fields(self, request, obj=None):
        return [f.name for f in self.model._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class DetalleSolicitudInline(admin.TabularInline):
    model = DetalleSolicitud
    extra = 1


@admin.register(SolicitudDespacho)
class SolicitudDespachoAdmin(admin.ModelAdmin):
    """Mientras no exista el módulo del Supervisor, las solicitudes se crean desde aquí."""
    list_display = ('id', 'obra', 'solicitante', 'estado', 'fecha_solicitud')
    list_filter = ('estado',)
    inlines = [DetalleSolicitudInline]
    readonly_fields = ('estado', 'motivo_rechazo')

    def has_delete_permission(self, request, obj=None):
        return False
