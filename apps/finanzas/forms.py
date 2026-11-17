from django import forms
from django.db.models import Sum
from django.utils.formats import number_format

from apps.inventario.models import DocumentoEntrada
from apps.obras.models import Obra

from .models import ObservacionFactura, PagoProveedor


class ObservacionFacturaForm(forms.ModelForm):
    class Meta:
        model = ObservacionFactura
        fields = ['texto']
        labels = {
            'texto': 'Motivo del reporte',
        }
        widgets = {
            'texto': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe qué debe revisar Gerencia.',
            }),
        }


class PagoProveedorForm(forms.ModelForm):
    class Meta:
        model = PagoProveedor
        fields = ['documento', 'fecha', 'monto', 'medio_pago', 'estado']
        labels = {
            'documento': 'Factura o documento',
            'monto': 'Monto (CLP)',
        }
        widgets = {
            'documento': forms.Select(attrs={'class': 'form-select'}),
            'fecha': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'monto': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0.01',
                'step': '0.01',
            }),
            'medio_pago': forms.Select(attrs={'class': 'form-select'}),
            'estado': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['documento'].queryset = DocumentoEntrada.objects.select_related(
            'proveedor',
        ).order_by('-fecha_emision', '-id')

    def clean(self):
        cleaned_data = super().clean()
        documento = cleaned_data.get('documento')
        monto = cleaned_data.get('monto')
        if documento is None or monto is None:
            return cleaned_data

        pagos_existentes = PagoProveedor.objects.filter(documento=documento).exclude(
            estado=PagoProveedor.Estado.ANULADO,
        )
        if self.instance.pk:
            pagos_existentes = pagos_existentes.exclude(pk=self.instance.pk)
        total_existente = pagos_existentes.aggregate(total=Sum('monto'))['total'] or 0
        disponible = documento.monto_neto - total_existente
        if monto > disponible:
            self.add_error(
                'monto',
                'El monto supera el saldo disponible del documento '
                f'(${number_format(disponible, decimal_pos=2)} CLP).',
            )
        return cleaned_data


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
