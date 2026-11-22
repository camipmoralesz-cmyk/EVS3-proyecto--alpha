from django import forms
from .models import MovimientoCardex


class AnulacionControladaForm(forms.Form):
    """
    Formulario para que el Administrador General justifique la anulación
    de un movimiento mediante un contra-asiento inmutable.
    """
    movimiento_id = forms.IntegerField(widget=forms.HiddenInput())
    motivo_anulacion = forms.CharField(
        label="Motivo de la anulación",
        min_length=10,
        max_length=500,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Explique detalladamente el error operativo o motivo de la reversa (mín. 10 caracteres)...',
            'required': True
        })
    )


class FiltroCardexForm(forms.Form):
    """
    Formulario de búsqueda y filtrado avanzado para el Auditor y Gerencia.
    """
    tipo_movimiento = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos los tipos')] + list(MovimientoCardex._meta.get_field('tipo_movimiento').choices),
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    fecha_inicio = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    fecha_fin = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'})
    )
    usuario = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Usuario...'
        })
    )
    documento = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'N° Doc. o Obra...'
        })
    )