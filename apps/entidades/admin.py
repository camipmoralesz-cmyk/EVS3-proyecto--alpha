from django.contrib import admin

from .models import ContactoEntidad, CuentaBancaria, Proveedor


class ContactoEntidadInline(admin.TabularInline):
    model = ContactoEntidad
    extra = 1


class CuentaBancariaInline(admin.TabularInline):
    model = CuentaBancaria
    extra = 1


@admin.register(Proveedor)
class ProveedorAdmin(admin.ModelAdmin):
    list_display = ('rut', 'razon_social', 'nombre_fantasia', 'tipo', 'telefono', 'email', 'activo')
    search_fields = ('rut', 'razon_social', 'nombre_fantasia', 'giro')
    list_filter = ('tipo', 'activo')
    inlines = [ContactoEntidadInline, CuentaBancariaInline]
