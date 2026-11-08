from django.contrib import admin
from .models import MovimientoCardex

@admin.register(MovimientoCardex)
class MovimientoCardexAdmin(admin.ModelAdmin):
    list_display = ('id', 'fecha_hora', 'articulo', 'tipo_movimiento', 'cantidad', 'saldo_resultante', 'usuario', 'es_reversa')
    list_filter = ('tipo_movimiento', 'es_reversa', 'fecha_hora')
    search_fields = ('articulo__nombre', 'justificacion', 'usuario__username')
    readonly_fields = ('fecha_hora', 'articulo', 'tipo_movimiento', 'cantidad', 'saldo_resultante', 'valor_unitario', 'usuario', 'obra', 'tecnico', 'justificacion', 'es_reversa', 'movimiento_reversado')

    # Impedir borrado físico desde el Admin Django
    def has_delete_permission(self, request, obj=None):
        return False
        
    def has_add_permission(self, request):
        return False
