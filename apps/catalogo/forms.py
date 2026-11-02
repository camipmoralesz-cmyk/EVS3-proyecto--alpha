#este formulario incluye las calidaciones que capturan
#el intento de duplicar un codigo y muestran el mensaje de error HU-06.


from django import forms
from .models import Articulo

class ArticuloForm(forms.ModelForm):
    class Meta:
        model = Articulo
        fields = [
            'codigo_interno', 
            'codigo_barras', 
            'nombre', 
            'categoria',
            'unidad_medida', 
            'ubicacion_bodega', 
            'stock_minimo', 
            'stock_critico'
        ]
        widgets = {
            'codigo_interno': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: COMP-014'}),
            'codigo_barras': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Escanee o digite el código'}),
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'categoria': forms.Select(attrs={'class': 'form-select'}),
            'unidad_medida': forms.Select(attrs={'class': 'form-select'}),
            'ubicacion_bodega': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Pasillo 3 - Estante B'}),
            'stock_minimo': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'stock_critico': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    # Validación personalizada para Código Interno
    def clean_codigo_interno(self):
        codigo = self.cleaned_data.get('codigo_interno')
        qs = Articulo.objects.filter(codigo_interno__iexact=codigo)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("El código interno ya se encuentra registrado en el catálogo maestro.")
        return codigo

    # Validación personalizada para Código de Barras
    def clean_codigo_barras(self):
        codigo = self.cleaned_data.get('codigo_barras')
        if codigo:
            qs = Articulo.objects.filter(codigo_barras__iexact=codigo)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError("El código de barras / QR ya está asignado a otro artículo.")
        return codigo