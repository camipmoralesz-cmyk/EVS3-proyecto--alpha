
from django import forms
from django.contrib.auth.models import User

from apps.usuarios.roles import ALIAS_ROLES
from .models import Obra


# Campos de evaluación financiera que se gestionan desde Obras y desde Finanzas
CAMPOS_FINANCIEROS = [
    'tipo_servicio',
    'numero_presupuesto',
    'supervisor',
    'tarifa_hora_mano_obra',
    'costo_mano_obra_estimado',
    'margen_esperado_porcentaje',
]

# Si no vienen en el POST se conserva el valor actual (o el por defecto del modelo)
_CONSERVAR_SI_VACIO = ('tipo_servicio', 'tarifa_hora_mano_obra',
                       'costo_mano_obra_estimado', 'margen_esperado_porcentaje')

WIDGETS_FINANCIEROS = {
    'tipo_servicio': forms.Select(attrs={'class': 'form-select'}),
    'numero_presupuesto': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: PRES-2026-014'}),
    'supervisor': forms.Select(attrs={'class': 'form-select'}),
    'tarifa_hora_mano_obra': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '1'}),
    'costo_mano_obra_estimado': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '1'}),
    'margen_esperado_porcentaje': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'max': '100', 'step': '0.01'}),
}


def responsables_de_obra():
    """Usuarios activos con rol Supervisor o Técnico (responsables en terreno)."""
    grupos = ALIAS_ROLES['supervisor'] + ALIAS_ROLES['tecnico']
    return User.objects.filter(is_active=True, groups__name__in=grupos).distinct().order_by('first_name', 'username')


class CamposFinancierosMixin:
    """Deja opcionales los campos financieros sin romper el guardado si no se envían."""

    def _preparar_campos_financieros(self):
        for nombre in CAMPOS_FINANCIEROS:
            if nombre in self.fields:
                self.fields[nombre].required = False
        if 'supervisor' in self.fields:
            self.fields['supervisor'].queryset = responsables_de_obra()
            self.fields['supervisor'].empty_label = 'Sin responsable asignado'

    def clean(self):
        datos = super().clean()
        for nombre in _CONSERVAR_SI_VACIO:
            if nombre in self.fields and datos.get(nombre) in (None, ''):
                datos[nombre] = getattr(self.instance, nombre)
        return datos


class ObraForm(CamposFinancierosMixin, forms.ModelForm):

    class Meta:
        model = Obra
        fields = [
            'nombre',
            'mandante',
            'presupuesto_total',
            'estado',
        ] + CAMPOS_FINANCIEROS

        widgets = {
            'nombre': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Nombre de la obra'
            }),
            'mandante': forms.Select(attrs={
                'class': 'form-select'
            }),
            'presupuesto_total': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01'
            }),
            'estado': forms.Select(attrs={
                'class': 'form-select'
            }),
            **WIDGETS_FINANCIEROS,
        }

        labels = {
            'nombre': 'Nombre de la obra',
            'mandante': 'Cliente mandante',
            'presupuesto_total': 'Presupuesto total',
            'estado': 'Estado',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._preparar_campos_financieros()

        self.fields['mandante'].queryset = (
            self.fields['mandante'].queryset.filter(
                tipo='MANDANTE',
                activo=True
            )
        )
