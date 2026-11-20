from django.contrib import admin
from .models import Categoria, Articulo


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')


@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    list_display = ('codigo_interno', 'nombre', 'categoria', 'ubicacion_bodega', 'stock_actual',
                    'stock_minimo', 'stock_critico', 'activo')
    search_fields = ('codigo_interno', 'codigo_barras', 'nombre')
    list_filter = ('categoria', 'unidad_medida', 'activo')
    # El stock y los costos solo cambian mediante movimientos / documentos de respaldo.
    # Si se pudieran editar aquí, se alteraría el inventario sin dejar rastro en el Cardex.
    readonly_fields = ('stock_actual', 'pmp_costo_actual', 'ultimo_costo_compra')

    def has_delete_permission(self, request, obj=None):
        return False  # los artículos se desactivan, no se eliminan
