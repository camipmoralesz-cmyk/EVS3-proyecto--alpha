from django import forms
from apps.inventario.models import MovimientoInventario


class FiltroCardexForm(forms.Form):
    """
    Formulario de búsqueda y filtrado avanzado para el Auditor y Gerencia.
    """
    tipo_movimiento = forms.ChoiceField(
        required=False,
        choices=[('', 'Todos los tipos')] + [
            (valor, etiqueta) for valor, etiqueta in MovimientoInventario.TIPOS_MOVIMIENTO
            if valor not in (MovimientoInventario.TIPO_INGRESO_SISTEMA, MovimientoInventario.TIPO_SALIDA_SISTEMA)
        ],
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