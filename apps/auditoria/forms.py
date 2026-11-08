#El formulario para ingresar la anulación con la justificación obligatoria.
from django import forms
from .models import MovimientoCardex

class AnulacionControladaForm(forms.Form):
    movimiento_id = forms.IntegerField(
        widget=forms.HiddenInput(),
        required=True
    )
    motivo_anulacion = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Escriba obligatoriamente el motivo de la anulación...'
        }),
        label="Motivo del Ajuste / Anulación",
        required=True,
        min_length=10
    )
    