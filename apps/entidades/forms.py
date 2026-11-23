# Formularios de HU-07: ficha de proveedor/mandante, sus contactos y sus
# cuentas bancarias. Los contactos y cuentas se editan como "formsets inline",
# es decir, varios sub-formularios hijos dentro del formulario de la ficha.

from django import forms
from django.forms import BaseInlineFormSet, inlineformset_factory

from apps.finanzas.utils import enmascarar_numero_cuenta, puede_ver_cuentas_bancarias
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
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._numero_cuenta_oculto = (
            self.instance.pk is not None
            and not puede_ver_cuentas_bancarias(user)
        )
        if self._numero_cuenta_oculto:
            self.fields['numero_cuenta'].disabled = True
            self.initial['numero_cuenta'] = enmascarar_numero_cuenta(
                self.instance.numero_cuenta,
            )

    class Meta:
        model = CuentaBancaria
        fields = ['banco', 'tipo_cuenta', 'numero_cuenta', 'email_pago']
        widgets = {
            'banco': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Banco Estado'}),
            'tipo_cuenta': forms.Select(attrs={'class': 'form-select'}),
            'numero_cuenta': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric'}),
            'email_pago': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def clean_numero_cuenta(self):
        if self._numero_cuenta_oculto:
            return self.instance.numero_cuenta
        return self.cleaned_data['numero_cuenta']


class BaseContactoFormSet(BaseInlineFormSet):
    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        # Si la fila solo trae vacíos y el cargo por defecto (sin nombre, rut,
        # email ni teléfono), se trata como fila extra vacía para que no bloquee
        # el guardado pidiendo "Nombre *".
        if self.is_bound and i >= self.initial_form_count():
            prefijo = form.add_prefix
            sin_datos = not any(
                (self.data.get(prefijo(campo)) or '').strip()
                for campo in ('nombre', 'rut', 'email', 'telefono')
            )
            if sin_datos:
                form.empty_permitted = True
                form.initial['cargo'] = self.data.get(prefijo('cargo'), form.initial.get('cargo'))
        return form


class BaseCuentaFormSet(BaseInlineFormSet):
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs['user'] = self.user
        return kwargs

    def _construct_form(self, i, **kwargs):
        form = super()._construct_form(i, **kwargs)
        if self.is_bound and i >= self.initial_form_count():
            prefijo = form.add_prefix
            sin_datos = not any(
                (self.data.get(prefijo(campo)) or '').strip()
                for campo in ('banco', 'numero_cuenta', 'email_pago')
            )
            if sin_datos:
                form.empty_permitted = True
                form.initial['tipo_cuenta'] = self.data.get(prefijo('tipo_cuenta'), form.initial.get('tipo_cuenta'))
        return form


# Formsets inline: manejan "N contactos" y "N cuentas" de UNA ficha.
# extra=1 -> muestra un formulario vacío para agregar uno nuevo.
# can_delete=True -> agrega una casilla "Eliminar" en cada fila existente.
ContactoFormSet = inlineformset_factory(
    Proveedor,
    ContactoEntidad,
    form=ContactoForm,
    formset=BaseContactoFormSet,
    extra=1,
    can_delete=True,
)

CuentaFormSet = inlineformset_factory(
    Proveedor,
    CuentaBancaria,
    form=CuentaForm,
    formset=BaseCuentaFormSet,
    extra=1,
    can_delete=True,
)
