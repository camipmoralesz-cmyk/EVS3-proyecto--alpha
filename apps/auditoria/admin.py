from django.contrib import admin
from .models import MovimientoCardex, BitacoraAuditoria, LogAcceso


class SoloLecturaAuditoriaAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MovimientoCardex)
class MovimientoCardexAdmin(SoloLecturaAuditoriaAdmin):
    list_display = (
        'id', 'fecha_hora', 'articulo', 'tipo_movimiento',
        'cantidad', 'saldo_resultante', 'usuario', 'es_reversa'
    )
    list_filter = ('tipo_movimiento', 'es_reversa', 'fecha_hora')
    search_fields = (
        'articulo__nombre', 'justificacion', 'usuario__username',
        'documento_referencia', 'obra_referencia'
    )


@admin.register(BitacoraAuditoria)
class BitacoraAuditoriaAdmin(SoloLecturaAuditoriaAdmin):
    list_display = (
        'id', 'fecha_hora', 'usuario', 'ip_origen',
        'modulo', 'accion', 'modelo_afectado', 'objeto_id'
    )
    list_filter = ('modulo', 'accion', 'fecha_hora')
    search_fields = ('usuario__username', 'descripcion', 'modelo_afectado', 'objeto_id')


@admin.register(LogAcceso)
class LogAccesoAdmin(SoloLecturaAuditoriaAdmin):
    list_display = ('id', 'fecha_hora', 'username_intentado', 'exitoso', 'ip_origen')
    list_filter = ('exitoso', 'fecha_hora')
    search_fields = ('username_intentado', 'ip_origen')