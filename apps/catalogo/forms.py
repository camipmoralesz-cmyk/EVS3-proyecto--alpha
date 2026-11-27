#este formulario incluye las calidaciones que capturan
#el intento de duplicar un codigo y muestran el mensaje de error HU-06.


from django import forms
from django.utils import timezone

from .models import Articulo, Categoria

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
            'sector_bodega',
            'stock_minimo',
            'stock_critico',
            'precio_lista',
            'descripcion',
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
            'sector_bodega': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Bodega Central'}),
            'precio_lista': forms.NumberInput(attrs={'class': 'form-control', 'min': '0', 'step': '1'}),
            'descripcion': forms.Textarea(attrs={'class': 'form-control', 'rows': 3,
                                                 'placeholder': 'Especificaciones técnicas, marca, modelo...'}),
        }

    # Campos del Anexo C opcionales: si no vienen se conserva el valor actual o el por defecto
    OPCIONALES = ('sector_bodega', 'precio_lista', 'descripcion')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for nombre in self.OPCIONALES:
            self.fields[nombre].required = False
        self._precio_anterior = self.instance.precio_lista

    def clean_sector_bodega(self):
        return (self.cleaned_data.get('sector_bodega') or '').strip() or self.instance.sector_bodega or 'Bodega Central'

    def clean_precio_lista(self):
        precio = self.cleaned_data.get('precio_lista')
        if precio is None:
            return self.instance.precio_lista or 0
        if precio < 0:
            raise forms.ValidationError("El precio de lista no puede ser negativo.")
        return precio

    def save(self, commit=True):
        articulo = super().save(commit=False)
        # Se registra cuándo cambió el precio de lista
        if articulo.precio_lista != self._precio_anterior or (not articulo.pk and articulo.precio_lista):
            articulo.fecha_actualizacion_precio = timezone.now()
        if commit:
            articulo.save()
        return articulo

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


class CategoriaForm(forms.ModelForm):
    class Meta:
        model = Categoria
        fields = ['nombre']
        widgets = {'nombre': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Gases refrigerantes'})}

    def clean_nombre(self):
        nombre = (self.cleaned_data.get('nombre') or '').strip()
        if not nombre:
            raise forms.ValidationError("Ingrese el nombre de la categoría.")
        if Categoria.objects.filter(nombre__iexact=nombre).exists():
            raise forms.ValidationError(f"La categoría '{nombre}' ya existe.")
        return nombre
