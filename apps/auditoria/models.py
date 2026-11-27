from django.db import models
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import PermissionDenied


class AppendOnlyQuerySet(models.QuerySet):
    """
    Bloquea operaciones masivas (.update() y .delete()) a nivel de ORM
    para garantizar inmutabilidad (RF06 y RNF02).
    """
    def delete(self):
        raise PermissionDenied("Operación no permitida: los registros de auditoría no pueden eliminarse.")

    def update(self, **kwargs):
        raise PermissionDenied("Operación no permitida: los registros de auditoría son inmutables.")


class BitacoraAuditoria(models.Model):
    """
    Bitácora inmutable de cambios críticos del sistema (RNF02).
    """
    ACCION_CHOICES = [
        ('CREAR', 'Creación'),
        ('EDITAR', 'Modificación'),
        ('ELIMINAR', 'Eliminación / Desactivación'),
        ('ANULAR', 'Anulación / Contra-asiento'),
        ('EXPORTAR', 'Exportación de Reporte'),
    ]

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    fecha_hora = models.DateTimeField(default=timezone.now)
    ip_origen = models.GenericIPAddressField(null=True, blank=True)
    modulo = models.CharField(max_length=60)
    accion = models.CharField(max_length=20, choices=ACCION_CHOICES)
    modelo_afectado = models.CharField(max_length=60)
    objeto_id = models.CharField(max_length=50)
    descripcion = models.TextField()
    valores_anteriores = models.JSONField(null=True, blank=True)
    valores_nuevos = models.JSONField(null=True, blank=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = "Registro de Bitácora"
        verbose_name_plural = "Bitácora de Auditoría"

    def save(self, *args, **kwargs):
        # Inmutabilidad de bitácora (RNF02)
        if self.pk is not None:
            raise PermissionDenied("Operación no permitida: la bitácora de auditoría no puede modificarse.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Operación no permitida: la bitácora de auditoría no puede eliminarse.")

    def __str__(self):
        return f"{self.fecha_hora.strftime('%Y-%m-%d %H:%M')} | {self.usuario} | {self.accion} {self.modelo_afectado}"


class LogAcceso(models.Model):
    """
    Registro de intentos de acceso exitosos y fallidos (Seguridad TI).
    """
    username_intentado = models.CharField(max_length=150)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True)
    fecha_hora = models.DateTimeField(default=timezone.now)
    ip_origen = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True, default='')
    exitoso = models.BooleanField(default=False)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = "Log de Acceso"
        verbose_name_plural = "Logs de Acceso"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionDenied("Operación no permitida: los registros de acceso no pueden modificarse.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Operación no permitida: los registros de acceso no pueden eliminarse.")