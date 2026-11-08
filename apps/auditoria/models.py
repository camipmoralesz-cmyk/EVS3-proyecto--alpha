#Define el modelo MovimientoCardex (o la lógica del Kardex) que no permite borrado físico y soporta contra-asientos (reversas).

from django.db import models
from django.conf import settings
from django.utils import timezone

class MovimientoCardex(models.Model):
    TIPO_MOVIMIENTO_CHOICES = [
        ('INGRESO', 'Ingreso por Compra/Factura'),
        ('EGRESO', 'Egreso a Obra'),
        ('MERMA', 'Merma / Pérdida'),
        ('DEVOLUCION', 'Devolución de Faena'),
        ('ANULACION', 'Contra-Asiento de Anulación'),
    ]

    articulo = models.ForeignKey('catalogo.Articulo', on_delete=models.PROTECT, related_name='movimientos')
    tipo_movimiento = models.CharField(max_length=20, choices=TIPO_MOVIMIENTO_CHOICES)
    cantidad = models.IntegerField()  # Positivo para ingreso/devolución, negativo o ajustado para egreso/anulación
    saldo_resultante = models.IntegerField()
    valor_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    fecha_hora = models.DateTimeField(default=timezone.now)
    
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    obra = models.ForeignKey('obras.Obra', on_delete=models.PROTECT, null=True, blank=True)
    tecnico = models.ForeignKey('usuarios.Tecnico', on_delete=models.PROTECT, null=True, blank=True)
    
    justificacion = models.TextField(help_text="Motivo obligatorio para ajustes o anulaciones")
    
    # Trazabilidad de Auditoría (HU-12)
    es_reversa = models.BooleanField(default=False)
    movimiento_reversado = models.OneToOneField(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='contra_asiento'
    )

    class Meta:
        ordering = ['-fecha_hora']
        verbose_name = "Movimiento de Cardex"
        verbose_name_plural = "Movimientos de Cardex"

    def __str__(self):
        return f"{self.fecha_hora.strftime('%Y-%m-%d %H:%M')} | {self.tipo_movimiento} | {self.articulo.nombre}"
