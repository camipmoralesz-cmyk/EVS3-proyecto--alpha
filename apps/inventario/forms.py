from django import forms

from apps.catalogo.models import Articulo
from apps.entidades.models import Proveedor
from apps.obras.models import Obra
from .models import DocumentoEntrada, MovimientoInventario as M
from .services import MIN_JUSTIFICACION, SALIDAS_TIPIFICADAS, sectores_disponibles, tecnicos_disponibles


class DocumentoEntradaForm(forms.ModelForm):
    class Meta:
        model = DocumentoEntrada
        fields = [
            'proveedor',
            'tipo_documento',
            'numero_documento',
            'fecha_emision',
            'observaciones'
        ]
        widgets = {
            'proveedor': forms.Select(attrs={'class': 'form-select select2', 'required': 'required'}),
            'tipo_documento': forms.Select(attrs={'class': 'form-select', 'required': 'required'}),
            'numero_documento': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: F-98234', 'required': 'required'}),
            'fecha_emision': forms.DateInput(attrs={'class': 'form-control', 'type': 'date', 'required': 'required'}),
            'observaciones': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Notas u observaciones del ingreso'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Bodega solo SELECCIONA proveedores: únicamente los activos y de tipo proveedor (no mandantes).
        self.fields['proveedor'].queryset = Proveedor.objects.filter(activo=True, tipo=Proveedor.Tipo.PROVEEDOR)


class SalidaTipificadaForm(forms.Form):
    """Merma, devolución (desde obra / a proveedor) y uso interno. Justificación siempre obligatoria."""

    tipo = forms.ChoiceField(
        label="Tipo de movimiento",
        choices=[(t, dict(M.TIPOS_MOVIMIENTO)[t]) for t in SALIDAS_TIPIFICADAS],
    )
    articulo = forms.ModelChoiceField(queryset=Articulo.objects.none(), label="Artículo")
    cantidad = forms.DecimalField(label="Cantidad", min_value=0.01, max_digits=10, decimal_places=2)
    obra = forms.ModelChoiceField(queryset=Obra.objects.none(), required=False, label="Obra (devolución desde obra)")
    proveedor = forms.ModelChoiceField(queryset=Proveedor.objects.none(), required=False,
                                       label="Proveedor (devolución a proveedor)")
    justificacion = forms.CharField(
        label="Justificación (obligatoria)", min_length=MIN_JUSTIFICACION,
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Ej: Pallets dañados por agua en el patio'}),
        error_messages={'min_length': f"La justificación debe tener al menos {MIN_JUSTIFICACION} caracteres."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['articulo'].queryset = Articulo.objects.filter(activo=True).order_by('nombre')
        self.fields['obra'].queryset = Obra.objects.exclude(estado=Obra.Estado.INACTIVA)
        self.fields['proveedor'].queryset = Proveedor.objects.filter(activo=True, tipo=Proveedor.Tipo.PROVEEDOR)
        for nombre, campo in self.fields.items():
            clase = 'form-select' if isinstance(campo.widget, forms.Select) else 'form-control'
            campo.widget.attrs.setdefault('class', clase)

    def clean(self):
        datos = super().clean()
        tipo = datos.get('tipo')
        if tipo == M.TIPO_DEVOLUCION_OBRA and not datos.get('obra'):
            self.add_error('obra', "Seleccione la obra desde la que se devuelve el material.")
        if tipo == M.TIPO_DEVOLUCION_PROVEEDOR and not datos.get('proveedor'):
            self.add_error('proveedor', "Seleccione el proveedor al que se devuelve el material.")
        return datos


class TecnicoChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.get_full_name() or obj.get_username()


class DespachoForm(forms.Form):
    tecnico = TecnicoChoiceField(queryset=tecnicos_disponibles().none(), label="Técnico receptor",
                                 empty_label="Seleccione al técnico que recibe...")
    firma = forms.CharField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tecnico'].queryset = tecnicos_disponibles()
        self.fields['tecnico'].widget.attrs['class'] = 'form-select'


class AbrirSesionForm(forms.Form):
    sector = forms.ChoiceField(label="Sector (ubicación en bodega)", choices=[])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sector'].choices = [('', 'Seleccione un sector...')] + [(s, s) for s in sectores_disponibles()]
        self.fields['sector'].widget.attrs['class'] = 'form-select'
