from decimal import Decimal

from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator
from django.utils import timezone


class ObservacionFactura(models.Model):
    """Reporte de Finanzas a Gerencia asociado a un documento de entrada."""

    documento = models.ForeignKey(
        'inventario.DocumentoEntrada',
        on_delete=models.PROTECT,
        related_name='observaciones_finanzas',
        verbose_name='Documento',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='observaciones_facturas',
        verbose_name='Usuario',
    )
    texto = models.TextField(verbose_name='Observación')
    fecha = models.DateTimeField(auto_now_add=True, verbose_name='Fecha')
    estado = models.CharField(max_length=20, default='PENDIENTE', verbose_name='Estado')

    class Meta:
        ordering = ['-fecha']
        verbose_name = 'Observación de factura'
        verbose_name_plural = 'Observaciones de facturas'

    def __str__(self):
        return f'Observación de {self.documento} ({self.estado})'


class PagoProveedor(models.Model):
    objects = models.Manager()

    class MedioPago(models.TextChoices):
        TRANSFERENCIA = 'TRANSFERENCIA', 'Transferencia'
        CHEQUE = 'CHEQUE', 'Cheque'
        EFECTIVO = 'EFECTIVO', 'Efectivo'
        TARJETA = 'TARJETA', 'Tarjeta'
        OTRO = 'OTRO', 'Otro'

    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        PAGADO = 'PAGADO', 'Pagado'
        ANULADO = 'ANULADO', 'Anulado'

    documento = models.ForeignKey(
        'inventario.DocumentoEntrada',
        on_delete=models.PROTECT,
        related_name='pagos_proveedor',
        verbose_name='Documento',
    )
    fecha = models.DateField(default=timezone.localdate, verbose_name='Fecha')
    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Monto (CLP)',
    )
    medio_pago = models.CharField(
        max_length=20,
        choices=MedioPago.choices,
        verbose_name='Medio de pago',
    )
    estado = models.CharField(
        max_length=12,
        choices=Estado.choices,
        default=Estado.PENDIENTE,
        verbose_name='Estado',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='pagos_proveedor_registrados',
        verbose_name='Usuario',
    )

    class Meta:
        ordering = ['-fecha', '-id']
        verbose_name = 'Pago a proveedor'
        verbose_name_plural = 'Pagos a proveedores'

    def __str__(self):
        return f'Pago de ${self.monto} para {self.documento}'


class SaldoInicialEmpresa(models.Model):
    objects = models.Manager()

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal('30000.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Saldo inicial de la empresa (CLP)',
    )

    class Meta:
        verbose_name = 'Saldo inicial de la empresa'
        verbose_name_plural = 'Saldo inicial de la empresa'

    def __str__(self):
        return f'Saldo inicial: ${self.monto} CLP'
