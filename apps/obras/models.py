
from django.core.exceptions import ValidationError
from django.db import models

from apps.entidades.models import Proveedor


class Obra(models.Model):

    class Estado(models.TextChoices):
        ACTIVA = 'ACTIVA', 'Activa'
        INACTIVA = 'INACTIVA', 'Inactiva'
        CERRADA = 'CERRADA', 'Cerrada'

    nombre = models.CharField(
        max_length=150,
        verbose_name="Nombre de la obra"
    )

    mandante = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,
        related_name='obras',
        limit_choices_to={
            'tipo': 'MANDANTE',
            'activo': True
        },
        verbose_name="Cliente mandante"
    )

    presupuesto_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name="Presupuesto total"
    )

    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.ACTIVA,
        verbose_name="Estado de la obra"
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Obra"
        verbose_name_plural = "Obras"
        ordering = ['nombre']

    def clean(self):
        super().clean()

        if self.mandante_id:
            if self.mandante.tipo != Proveedor.Tipo.MANDANTE:
                raise ValidationError({
                    'mandante': 'La entidad seleccionada debe ser un mandante.'
                })

            if not self.mandante.activo:
                raise ValidationError({
                    'mandante': 'El mandante seleccionado debe estar activo.'
                })

        if self.presupuesto_total < 0:
            raise ValidationError({
                'presupuesto_total': 'El presupuesto no puede ser negativo.'
            })

    def __str__(self):
        return self.nombre
