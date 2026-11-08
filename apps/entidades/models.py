from django.core.validators import RegexValidator
from django.db import models

from .validators import formatear_rut, rut_canonico, validar_rut

# Teléfono: dígitos, espacios, +, paréntesis y guiones (entre 7 y 20 caracteres).
validar_telefono = RegexValidator(
    regex=r'^[0-9+\s()-]{7,20}$',
    message='Teléfono inválido. Use solo números, espacios, +, paréntesis o guiones (7 a 20 caracteres).',
)

# Número de cuenta: solo dígitos, entre 6 y 20.
validar_numero_cuenta = RegexValidator(
    regex=r'^\d{6,20}$',
    message='El número de cuenta debe tener solo dígitos (entre 6 y 20).',
)


class Proveedor(models.Model):
    """
    Ficha de una entidad externa: proveedor o empresa mandante (cliente).
    Se mantiene el nombre "Proveedor" (de HU-01) porque inventario depende de él;
    el campo "tipo" indica si la ficha es de un proveedor o de un mandante (HU-07).
    """

    class Tipo(models.TextChoices):
        PROVEEDOR = 'PROVEEDOR', 'Proveedor'
        MANDANTE = 'MANDANTE', 'Mandante'

    rut = models.CharField(max_length=12, unique=True, validators=[validar_rut], verbose_name="RUT / Identificación")
    razon_social = models.CharField(max_length=150, verbose_name="Razón Social")
    nombre_fantasia = models.CharField(max_length=150, blank=True, null=True, verbose_name="Nombre de Fantasía")
    giro = models.CharField(max_length=150, blank=True, null=True, verbose_name="Giro Comercial")
    tipo = models.CharField(max_length=10, choices=Tipo.choices, default=Tipo.PROVEEDOR, verbose_name="Tipo de entidad")
    telefono = models.CharField(max_length=30, blank=True, null=True, verbose_name="Teléfono")
    email = models.EmailField(blank=True, null=True, verbose_name="Correo Electrónico")
    direccion = models.CharField(max_length=200, blank=True, null=True, verbose_name="Dirección")
    activo = models.BooleanField(default=True, verbose_name="Activo")
    fecha_creacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Proveedor"
        verbose_name_plural = "Proveedores"
        ordering = ['razon_social']

    def __str__(self):
        return f"{self.rut} - {self.razon_social}"

    @property
    def rut_formateado(self):
        """RUT con puntos y guion, para mostrar en pantalla."""
        return formatear_rut(self.rut)

    def clean(self):
        # Se canoniza antes de que Django revise la unicidad (validate_unique),
        # así "76543210-3" y "76.543.210-3" se detectan como el mismo RUT.
        if self.rut:
            self.rut = rut_canonico(self.rut)

    def save(self, *args, **kwargs):
        # Segunda barrera: cualquier camino que guarde la ficha la deja canónica.
        if self.rut:
            self.rut = rut_canonico(self.rut)
        super().save(*args, **kwargs)


class ContactoEntidad(models.Model):
    """Persona de contacto de una entidad (una entidad puede tener muchos)."""

    class Cargo(models.TextChoices):
        COMERCIAL = 'COMERCIAL', 'Ejecutivo comercial'
        TECNICO = 'TECNICO', 'Encargado técnico'
        FINANZAS = 'FINANZAS', 'Contacto de finanzas'
        OTRO = 'OTRO', 'Otro'

    entidad = models.ForeignKey(Proveedor, on_delete=models.CASCADE, related_name='contactos', verbose_name="Entidad")
    nombre = models.CharField(max_length=150, verbose_name="Nombre")
    cargo = models.CharField(max_length=10, choices=Cargo.choices, default=Cargo.COMERCIAL, verbose_name="Cargo / Área")
    rut = models.CharField(max_length=12, blank=True, validators=[validar_rut], verbose_name="RUT del representante")
    email = models.EmailField(blank=True, verbose_name="Correo Electrónico")
    telefono = models.CharField(max_length=20, blank=True, validators=[validar_telefono], verbose_name="Teléfono")

    class Meta:
        verbose_name = "Contacto de entidad"
        verbose_name_plural = "Contactos de entidad"
        ordering = ['entidad', 'cargo', 'nombre']

    def __str__(self):
        return f"{self.nombre} ({self.get_cargo_display()})"

    def save(self, *args, **kwargs):
        if self.rut:
            self.rut = rut_canonico(self.rut)
        super().save(*args, **kwargs)


class CuentaBancaria(models.Model):
    """Datos bancarios de una entidad, para facilitar el pago a proveedores."""

    # TODO (seguridad): el diseño pide restringir estos datos a los roles de
    # Finanzas/Administración (requiere el módulo de usuarios/RBAC) y cifrar
    # numero_cuenta en reposo (requiere definir una clave de cifrado segura).

    class TipoCuenta(models.TextChoices):
        CORRIENTE = 'CORRIENTE', 'Cuenta corriente'
        VISTA = 'VISTA', 'Cuenta vista / RUT'
        AHORRO = 'AHORRO', 'Cuenta de ahorro'

    entidad = models.ForeignKey(Proveedor, on_delete=models.CASCADE, related_name='cuentas', verbose_name="Entidad")
    banco = models.CharField(max_length=100, verbose_name="Banco")
    tipo_cuenta = models.CharField(max_length=10, choices=TipoCuenta.choices, default=TipoCuenta.CORRIENTE, verbose_name="Tipo de cuenta")
    numero_cuenta = models.CharField(max_length=20, validators=[validar_numero_cuenta], verbose_name="Número de cuenta")
    email_pago = models.EmailField(blank=True, verbose_name="Correo para aviso de pago")

    class Meta:
        verbose_name = "Cuenta bancaria"
        verbose_name_plural = "Cuentas bancarias"
        ordering = ['entidad', 'banco']

    def __str__(self):
        return f"{self.banco} - {self.get_tipo_cuenta_display()} N° {self.numero_cuenta}"
