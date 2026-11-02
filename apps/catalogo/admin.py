from django.contrib import admin

from django.contrib import admin
from .models import Categoria, Articulo

@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ('id', 'nombre')

@admin.register(Articulo)
class ArticuloAdmin(admin.ModelAdmin):
    list_display = ('codigo_interno', 'nombre', 'categoria', 'ubicacion_bodega', 'stock_actual', 'stock_minimo', 'stock_critico')
    search_fields = ('codigo_interno', 'codigo_barras', 'nombre')
    list_filter = ('categoria', 'unidad_medida')