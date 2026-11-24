from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import DecimalField, F, Q, Sum
from django.contrib.auth.models import User
from django.utils.functional import cached_property
from apps.catalogo.models import Articulo
from apps.entidades.models import Proveedor


class Obra(models.Model):
    objects = models.Manager()

    class Estado(models.TextChoices):
        ACTIVA = 'ACTIVA', 'Activa'
        INACTIVA = 'INACTIVA', 'Inactiva'
        CERRADA = 'CERRADA', 'Cerrada'

    # Tipos de servicio del Anexo C
    class TipoServicio(models.TextChoices):
        PROYECTO = 'PROYECTO', 'Proyecto'
        MANTENCION = 'MANTENCION', 'Mantención'
        CLIMATIZACION = 'CLIMATIZACION', 'Climatización'
        ELECTRICO = 'ELECTRICO', 'Proyecto eléctrico'
        EMERGENCIA = 'EMERGENCIA', 'Emergencia'
        GARANTIA = 'GARANTIA', 'Garantía'
        VENTA_REPUESTOS = 'VENTA_REPUESTOS', 'Venta de repuestos'
        MEJORAS = 'MEJORAS', 'Mejoras'

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
        null=True,
        blank=True,
        verbose_name="Presupuesto total"
    )

    estado = models.CharField(
        max_length=10,
        choices=Estado.choices,
        default=Estado.ACTIVA,
        verbose_name="Estado de la obra"
    )

    numero_presupuesto = models.CharField(
        max_length=50, blank=True, default='',
        verbose_name="N° Presupuesto asociado"
    )

    tipo_servicio = models.CharField(
        max_length=30, choices=TipoServicio.choices, default=TipoServicio.PROYECTO,
        verbose_name="Tipo de servicio"
    )

    supervisor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='obras_supervisadas',
        verbose_name="Supervisor / Técnico responsable"
    )

    # --- Datos para evaluar la rentabilidad del proyecto ---
    tarifa_hora_mano_obra = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('15000.00'),
        validators=[MinValueValidator(0)],
        verbose_name="Tarifa hora mano de obra (CLP)"
    )

    costo_mano_obra_estimado = models.DecimalField(
        max_digits=14, decimal_places=2, default=0,
        validators=[MinValueValidator(0)],
        verbose_name="Costo fijo mano de obra (CLP)"
    )

    margen_esperado_porcentaje = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal('20.00'),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name="Margen de ganancia esperado (%)"
    )

    fecha_creacion = models.DateTimeField(
        auto_now_add=True
    )

    class Meta:
        verbose_name = "Obra"
        verbose_name_plural = "Obras"
        ordering = ['nombre']

    def __str__(self):
        return self.nombre

    # ------------------------------------------------------------------
    # Evaluación financiera (presupuesto cliente vs. costos reales)
    # ------------------------------------------------------------------
    @cached_property
    def costo_materiales(self):
        """CLP de materiales egresados a la obra menos lo devuelto a bodega."""
        if not self.pk:
            return Decimal('0')
        from apps.inventario.models import MovimientoInventario as M

        def total(tipo):
            valor = self.movimientos_inventario.filter(tipo_movimiento=tipo).aggregate(
                v=Sum(F('cantidad') * F('costo_unitario'),
                      output_field=DecimalField(max_digits=18, decimal_places=2))
            )['v']
            return valor or Decimal('0')

        return total(M.TIPO_EGRESO_OBRA) - total(M.TIPO_DEVOLUCION_OBRA)

    @cached_property
    def total_horas_trabajadas(self):
        if not self.pk:
            return Decimal('0')
        return self.hojas_servicio.aggregate(h=Sum('horas_invertidas'))['h'] or Decimal('0')

    @property
    def costo_mano_obra_real(self):
        """Costo fijo + horas registradas en hojas de servicio x tarifa hora."""
        return (Decimal(self.costo_mano_obra_estimado or 0)
                + Decimal(self.total_horas_trabajadas or 0) * Decimal(self.tarifa_hora_mano_obra or 0))

    @property
    def costo_total_real(self):
        return Decimal(self.costo_materiales) + self.costo_mano_obra_real

    @property
    def utilidad_actual(self):
        return Decimal(self.presupuesto_total or 0) - self.costo_total_real

    @property
    def utilidad_absoluta(self):
        # Monto sin signo para el indicador de ganancia / pérdida
        return abs(self.utilidad_actual)

    @property
    def margen_real_porcentaje(self):
        if self.presupuesto_total and self.presupuesto_total > 0:
            return round((self.utilidad_actual / Decimal(self.presupuesto_total)) * 100, 1)
        return Decimal('0.0')

    @property
    def es_rentable(self):
        return self.utilidad_actual >= 0

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

        if self.presupuesto_total is not None and self.presupuesto_total < 0:
            raise ValidationError({
                'presupuesto_total': 'El presupuesto no puede ser negativo.'
            })

        # REGLA DE NEGOCIO: no se cierra una obra con pedidos de materiales sin resolver en Bodega
        if self.pk and self.estado == self.Estado.CERRADA:
            # Solicitudes de terreno sin enlace a Bodega o cuyo despacho sigue pendiente
            materiales_pendientes = self.solicitudes_materiales.filter(estado='PENDIENTE').filter(
                Q(solicitud_despacho__isnull=True) | Q(solicitud_despacho__estado='PENDIENTE')
            ).exists()
            despachos_pendientes = self.solicitudes_despacho.filter(estado='PENDIENTE').exists()
            if materiales_pendientes or despachos_pendientes:
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

    # Pedido que recibe Bodega en /inventario/despachos/ (de ahí sale su estado real)
    solicitud_despacho = models.OneToOneField(
        'inventario.SolicitudDespacho', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='solicitud_obra', verbose_name="Solicitud de despacho en Bodega"
    )

    class Meta:
        verbose_name = "Solicitud de Material"
        verbose_name_plural = "Solicitudes de Materiales"
        ordering = ['-fecha_solicitud']

    @property
    def estado_bodega(self):
        """Estado real en Bodega (Pendiente / Despachada / Rechazada) si está enlazada."""
        if self.solicitud_despacho_id:
            return self.solicitud_despacho.get_estado_display()
        return self.get_estado_display()

    def __str__(self):
        return f"Solicitud #{self.pk or 'Nueva'} - {self.articulo.nombre} ({self.cantidad} un.)"


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
