
from django.contrib import admin
from .models import Obra


@admin.register(Obra)
class ObraAdmin(admin.ModelAdmin):

    list_display = (
        'nombre',
        'mandante',
        'presupuesto_total',
        'estado',
        'fecha_creacion',
    )

    list_filter = (
        'estado',
        'fecha_creacion',
    )

    search_fields = (
        'nombre',
        'mandante__razon_social',
        'mandante__rut',
    )

    ordering = ('nombre',)
