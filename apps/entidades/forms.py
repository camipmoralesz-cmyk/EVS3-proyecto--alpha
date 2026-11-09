# Formularios de HU-07: ficha de proveedor/mandante, sus contactos y sus
# cuentas bancarias. Los contactos y cuentas se editan como "formsets inline",
# es decir, varios sub-formularios hijos dentro del formulario de la ficha.

from django import forms
from django.forms import inlineformset_factory

from .models import ContactoEntidad, CuentaBancaria, Proveedor
from .validators import rut_canonico, validar_rut


class ProveedorForm(forms.ModelForm):
    class Meta:
        model = Proveedor
        fields = [
            'rut',
            'razon_social',
            'nombre_fantasia',
            'giro',
            'tipo',
            'telefono',
            'email',
            'direccion',
        ]
        widgets = {
            'rut': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 76.543.210-3'}),
            'razon_social': forms.TextInput(attrs={'class': 'form-control'}),
            'nombre_fantasia': forms.TextInput(attrs={'class': 'form-control'}),
            'giro': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Venta de equipos de refrigeración'}),
            'tipo': forms.Select(attrs={'class': 'form-select'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: +56 42 222 3344'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'direccion': forms.TextInput(attrs={'class': 'form-control'}),
        }

    # Validación del RUT: primero se revisa formato y dígito verificador
    # (los validadores del modelo recién corren DESPUÉS de este método),
    # luego se pasa a la forma canónica y se revisa que no exista otra ficha
    # con el mismo RUT escrito de otra manera.
    def clean_rut(self):
        rut = self.cleaned_data.get('rut')
        validar_rut(rut)
        rut = rut_canonico(rut)
        qs = Proveedor.objects.filter(rut=rut)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Ya existe una ficha registrada con este RUT.")
        return rut


class ContactoForm(forms.ModelForm):
    class Meta:
        model = ContactoEntidad
        fields = ['nombre', 'cargo', 'rut', 'email', 'telefono']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control'}),
            'cargo': forms.Select(attrs={'class': 'form-select'}),
            'rut': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control'}),
        }

    # El RUT del representante es opcional: si viene, se valida y se canoniza.
    def clean_rut(self):
        rut = self.cleaned_data.get('rut')
        if not rut:
            return rut
        validar_rut(rut)
        return rut_canonico(rut)


class CuentaForm(forms.ModelForm):
    class Meta:
        model = CuentaBancaria
        fields = ['banco', 'tipo_cuenta', 'numero_cuenta', 'email_pago']
        widgets = {
            'banco': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Banco Estado'}),
            'tipo_cuenta': forms.Select(attrs={'class': 'form-select'}),
            'numero_cuenta': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric'}),
            'email_pago': forms.EmailInput(attrs={'class': 'form-control'}),
        }


# Formsets inline: manejan "N contactos" y "N cuentas" de UNA ficha.
# extra=1 -> muestra un formulario vacío para agregar uno nuevo.
# can_delete=True -> agrega una casilla "Eliminar" en cada fila existente.
ContactoFormSet = inlineformset_factory(
    Proveedor,
    ContactoEntidad,
    form=ContactoForm,
    extra=1,
    can_delete=True,
)

CuentaFormSet = inlineformset_factory(
    Proveedor,
    CuentaBancaria,
    form=CuentaForm,
    extra=1,
    can_delete=True,
)
