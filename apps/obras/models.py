from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import User
from apps.catalogo.models import Articulo
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

        # REGLA DE NEGOCIO: No se puede cambiar el estado a CERRADA si hay solicitudes pendientes
                if self.pk and self.estado == self.Estado.CERRADA:
                    solicitudes_pendientes = self.solicitudes_materiales.filter(estado='PENDIENTE').exists()
                if solicitudes_pendientes:
                    raise ValidationError({
                        'estado': 'No se puede cerrar la obra porque existen solicitudes de materiales pendientes de despacho por Bodega.'
                    })


class SolicitudMaterialObra(models.Model):
    """
    Permite al supervisor solicitar materiales para su obra asignada.
    Restricción: El supervisor solicita, Bodega ejecuta y descuenta stock.
    """
    class EstadoSolicitud(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente de Despacho por Bodega'
        APROBADA = 'APROBADA', 'Despachado y Entregado'
        RECHAZADA = 'RECHAZADA', 'Rechazada'

    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name='solicitudes_materiales',
        verbose_name="Obra"
    )
    
    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.PROTECT,
        verbose_name="Artículo / Insumo"
    )
    
    cantidad = models.PositiveIntegerField(
        verbose_name="Cantidad solicitada"
    )
    
    estado = models.CharField(
        max_length=20,
        choices=EstadoSolicitud.choices,
        default=EstadoSolicitud.PENDIENTE,
        verbose_name="Estado de solicitud"
    )
    
    solicitado_por = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        verbose_name="Supervisor solicitante"
    )
    
    fecha_solicitud = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Solicitud de Material"
        verbose_name_plural = "Solicitudes de Materiales"
        ordering = ['-fecha_solicitud']

    def __str__(self):
        return f"Solicitud #{id or 'Nueva'} - {self.articulo.nombre} ({self.cantidad} un.)"


class HojaServicioObra(models.Model):
    """
    Registro de trabajos o servicios técnicos ejecutados en la obra.
    """
    obra = models.ForeignKey(
        Obra,
        on_delete=models.CASCADE,
        related_name='hojas_servicio',
        verbose_name="Obra"
    )
    
    tecnico_responsable = models.CharField(
        max_length=120,
        verbose_name="Personal técnico en terreno"
    )
    
    descripcion_trabajo = models.TextField(
        verbose_name="Descripción de labores de refrigeración / agroindustria"
    )
    
    horas_invertidas = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="Horas hombre invertidas"
    )
    
    fecha_servicio = models.DateField(
        verbose_name="Fecha de ejecución"
    )
    
    registrado_por = models.ForeignKey(
        User,
        on_delete=models.PROTECT,
        verbose_name="Supervisor que registra"
    )

    class Meta:
        verbose_name = "Hoja de Servicio"
        verbose_name_plural = "Hojas de Servicio"
        ordering = ['-fecha_servicio']

    def __str__(self):
        return f"Servicio en {self.obra.nombre} - {self.fecha_servicio}"
