from django.db import models

class Proveedor(models.Model):
    rut = models.CharField(max_length=12, unique=True, verbose_name="RUT / Identificación")
    razon_social = models.CharField(max_length=150, verbose_name="Razón Social")
    nombre_fantasia = models.CharField(max_length=150, blank=True, null=True, verbose_name="Nombre de Fantasía")
    giro = models.CharField(max_length=150, blank=True, null=True, verbose_name="Giro Comercial")
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
