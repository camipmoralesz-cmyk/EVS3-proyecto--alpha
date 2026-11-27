from django import forms
from .models import MovimientoCardex


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