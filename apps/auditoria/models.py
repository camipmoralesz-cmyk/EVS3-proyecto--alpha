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


class MovimientoCardex(models.Model):
    """
    Libro histórico e inalterable de movimientos de bodega (RF06 / HU-12).
    """
    TIPO_MOVIMIENTO_CHOICES = [
        ('INGRESO', 'Ingreso por Compra / Factura'),
        ('EGRESO', 'Egreso a Obra'),
        ('MERMA', 'Merma / Pérdida'),
        ('DEVOLUCION_FAENA', 'Devolución de Faena'),
        ('DEVOLUCION_PROVEEDOR', 'Devolución a Proveedor'),
        ('USO_INTERNO', 'Consumo Uso Interno'),
        ('AJUSTE_INVENTARIO', 'Ajuste por Inventario Físico'),
        ('ANULACION', 'Contra-Asiento de Anulación'),
    ]

    articulo = models.ForeignKey('catalogo.Articulo', on_delete=models.PROTECT, related_name='movimientos')
    tipo_movimiento = models.CharField(max_length=25, choices=TIPO_MOVIMIENTO_CHOICES)
    cantidad = models.IntegerField()
    saldo_resultante = models.IntegerField()
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    fecha_hora = models.DateTimeField(default=timezone.now)

    # Trazabilidad de responsables y respaldo documental (RF04, RF05)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    obra_referencia = models.CharField(max_length=120, blank=True, default='', help_text="Código o nombre de obra")
    tecnico_referencia = models.CharField(max_length=120, blank=True, default='', help_text="Técnico receptor")
    documento_referencia = models.CharField(max_length=100, blank=True, default='', help_text="N° Factura, Guía, NC o Vale")

    justificacion = models.TextField(help_text="Motivo obligatorio para mermas, ajustes o anulaciones")

    # Trazabilidad de Contra-Asientos (HU-12)
    es_reversa = models.BooleanField(default=False)
    movimiento_reversado = models.OneToOneField(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='contra_asiento'
    )

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = "Movimiento de Cardex"
        verbose_name_plural = "Movimientos de Cardex"

    def save(self, *args, **kwargs):
        # Impide editar registros existentes (RF06: Append-Only)
        if self.pk is not None:
            raise PermissionDenied("Operación no permitida: no se puede modificar un movimiento ya registrado.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # Impide borrado físico individual (RF06)
        raise PermissionDenied("Operación no permitida: los movimientos del Cardex no se eliminan; debe generar una anulación.")

    def __str__(self):
        return f"#{self.id} | {self.fecha_hora.strftime('%Y-%m-%d %H:%M')} | {self.tipo_movimiento} | {self.articulo}"


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