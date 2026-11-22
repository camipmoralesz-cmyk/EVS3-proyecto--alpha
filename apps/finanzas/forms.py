from django import forms
from apps.obras.models import Obra


class PresupuestoObraForm(forms.ModelForm):
    """Formulario exclusivo de Finanzas para editar el presupuesto_total de una Obra."""

    class Meta:
        model = Obra
        fields = ['presupuesto_total']
        labels = {
            'presupuesto_total': 'Presupuesto Total (CLP)',
        }
        widgets = {
            'presupuesto_total': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
                'placeholder': 'Ej: 25000000.00',
            }),
        }

    def clean_presupuesto_total(self):
        monto = self.cleaned_data.get('presupuesto_total')
        if monto is not None and monto < 0:
            raise forms.ValidationError('El presupuesto no puede ser negativo.')
        return monto
