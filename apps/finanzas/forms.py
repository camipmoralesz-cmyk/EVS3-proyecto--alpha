from decimal import Decimal

from django import forms
from django.db.models import Sum
from django.utils.formats import number_format

from apps.catalogo.models import Articulo
from apps.entidades.models import Proveedor
from apps.inventario.models import DocumentoEntrada, DetalleDocumento
from apps.inventario.services import (
    calcular_descuentos_sucesivos,
    calcular_subtotal_linea,
)
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
        ).filter(
            estado=DocumentoEntrada.ESTADO_CONFIRMADO,
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['presupuesto_total'].required = True

    def clean_presupuesto_total(self):
        monto = self.cleaned_data.get('presupuesto_total')
        if monto is not None and monto < 0:
            raise forms.ValidationError('El presupuesto no puede ser negativo.')
        return monto


class ObraForm(forms.ModelForm):
    class Meta:
        model = Obra
        fields = ['nombre', 'mandante', 'presupuesto_total', 'estado']
        labels = {
            'nombre': 'Nombre de la obra',
            'mandante': 'Cliente mandante',
            'presupuesto_total': 'Presupuesto inicial (CLP)',
            'estado': 'Estado',
        }
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'mandante': forms.Select(attrs={'class': 'form-select'}),
            'presupuesto_total': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': '0',
                'step': '0.01',
            }),
            'estado': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['presupuesto_total'].required = True


class BorradorFacturaForm(forms.ModelForm):
    class Meta:
        model = DocumentoEntrada
        fields = [
            'proveedor',
            'tipo_documento',
            'numero_documento',
            'fecha_emision',
            'observaciones',
        ]
        widgets = {
            'proveedor': forms.Select(attrs={'class': 'form-select'}),
            'tipo_documento': forms.Select(attrs={'class': 'form-select'}),
            'numero_documento': forms.TextInput(attrs={'class': 'form-control'}),
            'fecha_emision': forms.DateInput(attrs={
                'class': 'form-control',
                'type': 'date',
            }),
            'observaciones': forms.TextInput(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['proveedor'].queryset = Proveedor.objects.filter(
            tipo=Proveedor.Tipo.PROVEEDOR,
            activo=True,
        )

    def clean_tipo_documento(self):
        tipo_documento = self.cleaned_data['tipo_documento']
        if tipo_documento != DocumentoEntrada.TIPO_FACTURA:
            raise forms.ValidationError(
                'Finanzas solo puede crear borradores de facturas.',
            )
        return tipo_documento


class DetalleBorradorFacturaForm(forms.Form):
    articulo = forms.ModelChoiceField(queryset=Articulo.objects.none())
    cantidad = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        min_value=Decimal('0.01'),
    )
    precio_unitario_base = forms.IntegerField(min_value=0)
    descuento_1_porcentaje = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        required=False,
        initial=Decimal('0'),
    )
    descuento_2_porcentaje = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        required=False,
        initial=Decimal('0'),
    )
    descuento_3_porcentaje = forms.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal('0'),
        max_value=Decimal('100'),
        required=False,
        initial=Decimal('0'),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['articulo'].queryset = Articulo.objects.order_by('nombre')

    def clean(self):
        cleaned_data = super().clean()
        if any(name not in cleaned_data for name in (
            'cantidad',
            'precio_unitario_base',
            'descuento_1_porcentaje',
            'descuento_2_porcentaje',
            'descuento_3_porcentaje',
        )):
            return cleaned_data

        descuentos = (
            cleaned_data['descuento_1_porcentaje'] or Decimal('0'),
            cleaned_data['descuento_2_porcentaje'] or Decimal('0'),
            cleaned_data['descuento_3_porcentaje'] or Decimal('0'),
        )
        precio_final = calcular_descuentos_sucesivos(
            cleaned_data['precio_unitario_base'],
            *descuentos,
        )
        cleaned_data['precio_unitario_final'] = precio_final
        cleaned_data['subtotal_linea'] = calcular_subtotal_linea(
            precio_final,
            cleaned_data['cantidad'],
        )
        return cleaned_data

    def guardar(self, documento):
        return DetalleDocumento.objects.create(
            documento=documento,
            articulo=self.cleaned_data['articulo'],
            cantidad=self.cleaned_data['cantidad'],
            precio_unitario_base=self.cleaned_data['precio_unitario_base'],
            descuento_1_porcentaje=self.cleaned_data['descuento_1_porcentaje'] or 0,
            descuento_2_porcentaje=self.cleaned_data['descuento_2_porcentaje'] or 0,
            descuento_3_porcentaje=self.cleaned_data['descuento_3_porcentaje'] or 0,
            precio_unitario_final=self.cleaned_data['precio_unitario_final'],
            subtotal_linea=self.cleaned_data['subtotal_linea'],
        )
