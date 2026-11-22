from django.db import models
from django.contrib.auth.models import User

class ActaAprobacionInventario(models.Model):
    TIPO_CHOICES = [
        ('FISICO_BODEGA', 'Inventario Físico Bodega Central'),
        ('INVENTARIO_OBRA', 'Inventario de Obra / Proyecto Activo'),
        ('AUDITORIA_MENSUAL', 'Auditoría Mensual de Existencias'),
    ]

    tipo_acta = models.CharField(max_length=40, choices=TIPO_CHOICES)
    observacion = models.TextField(help_text="Justificación o notas de cuadratura de Gerencia")
    total_articulos_visados = models.PositiveIntegerField(default=0)
    articulos_criticos_detectados = models.PositiveIntegerField(default=0)
    aprobado_por = models.ForeignKey(
        User, 
        on_delete=models.PROTECT, # En PostgreSQL impide borrar al usuario si firmó un acta
        related_name='actas_aprobadas'
    )
    fecha_aprobacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_acta_aprobacion'
        ordering = ['-fecha_aprobacion']
        verbose_name = 'Acta de Aprobación de Inventario'
        verbose_name_plural = 'Actas de Aprobación de Inventarios'

    def __str__(self):
        return f"Acta #{self.id} - {self.get_tipo_acta_display()} ({self.fecha_aprobacion.strftime('%d/%m/%Y')})"
