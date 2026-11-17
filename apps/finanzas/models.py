from django.conf import settings
from django.db import models


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
