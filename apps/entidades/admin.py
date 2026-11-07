from django.contrib import admin
from .models import Proveedor

@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('rut', 'razon_social', 'nombre_fantasia', 'telefono', 'email', 'activo')
    search_fields = ('rut', 'razon_social', 'nombre_fantasia')
    list_filter = ('activo',)
