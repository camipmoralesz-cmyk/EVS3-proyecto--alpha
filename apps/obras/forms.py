
from django import forms
from .models import Obra


class ObraForm(forms.ModelForm):

    class Meta:
        model = Obra
        fields = [
            'nombre',
            'mandante',
            'presupuesto_total',
            'estado',
        ]

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
        }

        labels = {
            'nombre': 'Nombre de la obra',
            'mandante': 'Cliente mandante',
            'presupuesto_total': 'Presupuesto total',
            'estado': 'Estado',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['mandante'].queryset = (
            self.fields['mandante'].queryset.filter(
                tipo='MANDANTE',
                activo=True
            )
        )
