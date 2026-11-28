from django.conf import settings
from django.db import models
from django.db.models import Q
from decimal import Decimal
from apps.catalogo.models import Articulo
from apps.entidades.models import Proveedor

class DocumentoEntrada(models.Model):
    objects = models.Manager()

    TIPO_FACTURA = 'FACTURA'
    TIPO_BOLETA = 'BOLETA'
    TIPO_GUIA = 'GUIA_DESPACHO'
    TIPO_NOTA_CREDITO = 'NOTA_CREDITO'

    TIPOS_DOCUMENTO = [
        (TIPO_FACTURA, 'Factura'),
        (TIPO_BOLETA, 'Boleta'),
        (TIPO_GUIA, 'Guía de Despacho'),
        (TIPO_NOTA_CREDITO, 'Nota de Crédito'),
    ]

    ESTADO_CONFIRMADO = 'CONFIRMADO'
    ESTADO_ANULADO = 'ANULADO'
    ESTADO_BORRADOR = 'BORRADOR'

    ESTADOS = [
        (ESTADO_BORRADOR, 'Borrador'),
        (ESTADO_CONFIRMADO, 'Confirmado'),
        (ESTADO_ANULADO, 'Anulado'),
    ]

    proveedor = models.ForeignKey(
        Proveedor,
        on_delete=models.PROTECT,
        related_name='documentos_entrada',
        verbose_name="Proveedor"
    )
    tipo_documento = models.CharField(
        max_length=20,
        choices=TIPOS_DOCUMENTO,
        default=TIPO_FACTURA,
        verbose_name="Tipo de Documento"
    )
    numero_documento = models.CharField(
        max_length=50,
        verbose_name="Número de Documento"
    )
    fecha_emision = models.DateField(
        verbose_name="Fecha de Emisión del Documento"
    )
    fecha_registro = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha de Registro en Sistema"
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='documentos_registrados',
        verbose_name="Registrado por"
    )
    observaciones = models.TextField(
        blank=True,
        null=True,
        verbose_name="Observaciones"
    )
    monto_neto = models.IntegerField(
        default=0,
        verbose_name="Monto Neto Total"
    )
    estado = models.CharField(
        max_length=15,
        choices=ESTADOS,
        default=ESTADO_CONFIRMADO,
        verbose_name="Estado"
    )

    class Meta:
        verbose_name = "Documento de Entrada"
        verbose_name_plural = "Documentos de Entrada"
        ordering = ['-fecha_registro']
        indexes = [
            models.Index(fields=['proveedor', 'tipo_documento', 'numero_documento']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['proveedor', 'tipo_documento', 'numero_documento'],
                name='uniq_documento_proveedor_tipo_numero',
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_documento_display()} N° {self.numero_documento} - {self.proveedor.razon_social}"

    @property
    def es_nota_credito(self):
        return self.tipo_documento == self.TIPO_NOTA_CREDITO


class DetalleDocumento(models.Model):
    documento = models.ForeignKey(
        DocumentoEntrada,
        on_delete=models.CASCADE,
        related_name='detalles',
        verbose_name="Documento"
    )
    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.PROTECT,
        related_name='detalles_documento',
        verbose_name="Artículo / Material"
    )
    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Cantidad"
    )
    precio_unitario_base = models.IntegerField(
        verbose_name="Precio Base Unitario (CLP)"
    )
    
    # Capacidad de aplicar hasta tres descuentos independientes
    descuento_1_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Descuento 1 (%)"
    )
    descuento_2_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Descuento 2 (%)"
    )
    descuento_3_porcentaje = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Descuento 3 (%)"
    )
    
    precio_unitario_final = models.IntegerField(
        verbose_name="Precio Unitario Final (con descuentos)"
    )
    subtotal_linea = models.IntegerField(
        verbose_name="Subtotal Línea"
    )

    class Meta:
        verbose_name = "Detalle de Documento"
        verbose_name_plural = "Detalles de Documentos"

    def __str__(self):
        return f"{self.articulo.nombre} x {self.cantidad} ({self.documento})"


class CardexInalterableError(Exception):
    """Se intentó modificar o eliminar un movimiento ya registrado en el Cardex."""


class MovimientoQuerySet(models.QuerySet):
    """El Cardex es append-only: ninguna operación masiva puede alterar el historial."""

    def update(self, **kwargs):
        raise CardexInalterableError("Los movimientos del Cardex no se pueden modificar.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise CardexInalterableError("Los movimientos del Cardex no se pueden modificar.")

    def delete(self):
        raise CardexInalterableError("Los movimientos del Cardex no se pueden eliminar. Use una anulación (contra-asiento).")


class MovimientoInventario(models.Model):
    """Cardex de bodega. Inalterable: solo se insertan registros nuevos.
    Las correcciones las hace Gerencia con un contra-asiento (HU-12), nunca editando."""

    TIPO_ENTRADA = 'ENTRADA'
    TIPO_SALIDA = 'SALIDA'
    TIPO_AJUSTE = 'AJUSTE'
    TIPO_ANULACION = 'ANULACION'
    TIPO_INGRESO_SISTEMA = 'INGRESO_SISTEMA'
    TIPO_SALIDA_SISTEMA = 'SALIDA_SISTEMA'
    TIPO_SALIDA = 'SALIDA'                      # Salida por Nota de Crédito
    TIPO_AJUSTE = 'AJUSTE'                      # histórico (ya no se genera)
    TIPO_EGRESO_OBRA = 'EGRESO_OBRA'
    TIPO_MERMA = 'MERMA'
    TIPO_DEVOLUCION_OBRA = 'DEVOLUCION_OBRA'            # sobrante que vuelve de la obra (suma)
    TIPO_DEVOLUCION_PROVEEDOR = 'DEVOLUCION_PROVEEDOR'  # se devuelve al proveedor (resta)
    TIPO_USO_INTERNO = 'USO_INTERNO'
    TIPO_AJUSTE_POS = 'AJUSTE_POS'              # regularización inventario físico (+)
    TIPO_AJUSTE_NEG = 'AJUSTE_NEG'              # regularización inventario físico (-)

    TIPOS_MOVIMIENTO = [
        (TIPO_ENTRADA, 'Ingreso de Materiales'),
        (TIPO_SALIDA, 'Salida de Materiales'),
        (TIPO_AJUSTE, 'Ajuste de Inventario'),
        (TIPO_ANULACION, 'Contra-Asiento / Anulación'),
        (TIPO_INGRESO_SISTEMA, 'Ingreso de Personal al Sistema'),
        (TIPO_SALIDA_SISTEMA, 'Salida de Personal del Sistema'),
        (TIPO_EGRESO_OBRA, 'Egreso a Obra'),
        (TIPO_MERMA, 'Merma'),
        (TIPO_DEVOLUCION_OBRA, 'Devolución desde Obra'),
        (TIPO_DEVOLUCION_PROVEEDOR, 'Devolución a Proveedor'),
        (TIPO_USO_INTERNO, 'Uso Interno'),
        (TIPO_AJUSTE_POS, 'Ajuste Inv. Físico (+)'),
        (TIPO_AJUSTE_NEG, 'Ajuste Inv. Físico (−)'),
    ]

    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='movimientos_inventario',
        verbose_name="Artículo"
    )
    documento = models.ForeignKey(
        DocumentoEntrada,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='movimientos_generados',
        verbose_name="Documento Origen"
    )
    tipo_movimiento = models.CharField(
        max_length=25,
        choices=TIPOS_MOVIMIENTO,
        verbose_name="Tipo de Movimiento"
    )
    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Cantidad"
    )
    stock_anterior = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Stock Anterior"
    )
    stock_posterior = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=Decimal('0.00'),
        verbose_name="Stock Posterior"
    )
    costo_unitario = models.IntegerField(
        default=0,
        verbose_name="Costo Unitario Aplicado"
    )
    fecha = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Fecha y Hora del Movimiento"
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Usuario Responsable"
    )
    referencia = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Referencia / Motivo"
    )
    # --- Trazabilidad de los movimientos de bodega ---
    obra = models.ForeignKey(
        'obras.Obra', on_delete=models.PROTECT, null=True, blank=True,
        related_name='movimientos_inventario', verbose_name="Obra"
    )
    proveedor = models.ForeignKey(
        Proveedor, on_delete=models.PROTECT, null=True, blank=True,
        related_name='movimientos_inventario', verbose_name="Proveedor (devoluciones)"
    )
    tecnico = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='movimientos_recibidos', verbose_name="Técnico receptor"
    )
    despacho = models.ForeignKey(
        'Despacho', on_delete=models.PROTECT, null=True, blank=True,
        related_name='movimientos', verbose_name="Vale de salida"
    )
    sesion_inventario = models.ForeignKey(
        'SesionInventario', on_delete=models.PROTECT, null=True, blank=True,
        related_name='movimientos', verbose_name="Sesión de inventario físico"
    )
    orden_restock = models.ForeignKey(
        'OrdenRestock', on_delete=models.PROTECT, null=True, blank=True,
        related_name='movimientos', verbose_name="Orden de restock"
    )
    justificacion = models.TextField(blank=True, default='', verbose_name="Justificación")
    # Contra-asiento (ANULACION): movimiento que revierte. OneToOne = una sola anulación por movimiento.
    movimiento_anulado = models.OneToOneField(
        'self', on_delete=models.PROTECT, null=True, blank=True,
        related_name='anulacion', verbose_name="Movimiento anulado"
    )

    objects = MovimientoQuerySet.as_manager()

    class Meta:
        verbose_name = "Movimiento de Inventario"
        verbose_name_plural = "Movimientos de Inventario"
        ordering = ['-fecha', '-id']

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise CardexInalterableError("Un movimiento ya registrado en el Cardex no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise CardexInalterableError("Un movimiento del Cardex no se puede eliminar. Use una anulación (contra-asiento).")

    @property
    def suma_stock(self):
        return self.stock_posterior >= self.stock_anterior

    @property
    def valor_total(self):
        return int(self.cantidad * self.costo_unitario)

    @property
    def cantidad_con_signo(self):
        """Cantidad positiva si sumó stock y negativa si restó (vista del Cardex)."""
        return self.cantidad if self.suma_stock else -self.cantidad

    @property
    def es_anulacion(self):
        return self.tipo_movimiento == self.TIPO_ANULACION

    def __str__(self):
        ref_art = self.articulo.codigo_interno if self.articulo else 'SISTEMA'
        fecha_txt = self.fecha.strftime('%Y-%m-%d %H:%M') if self.fecha else ''
        return f"[{self.tipo_movimiento}] {ref_art} ({self.cantidad}) - {fecha_txt}"
        return f"[{self.tipo_movimiento}] {self.articulo.codigo_interno} ({self.cantidad}) - {self.fecha.strftime('%Y-%m-%d %H:%M')}"


# ---------------------------------------------------------------------------
# Solicitudes y despachos a obra (HU-02)
# ---------------------------------------------------------------------------
class SolicitudDespacho(models.Model):
    """Pedido de materiales que crea el Supervisor de Obra. Bodega solo despacha contra una solicitud."""

    class Estado(models.TextChoices):
        PENDIENTE = 'PENDIENTE', 'Pendiente'
        DESPACHADA = 'DESPACHADA', 'Despachada'
        RECHAZADA = 'RECHAZADA', 'Rechazada'

    obra = models.ForeignKey('obras.Obra', on_delete=models.PROTECT, related_name='solicitudes_despacho')
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='solicitudes_despacho')
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.PENDIENTE)
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    observaciones = models.TextField(blank=True)
    motivo_rechazo = models.TextField(blank=True)

    class Meta:
        verbose_name = "Solicitud de despacho"
        verbose_name_plural = "Solicitudes de despacho"
        ordering = ['-fecha_solicitud']

    def __str__(self):
        return f"Solicitud #{self.pk} - {self.obra}"


class DetalleSolicitud(models.Model):
    solicitud = models.ForeignKey(SolicitudDespacho, on_delete=models.CASCADE, related_name='detalles')
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, related_name='detalles_solicitud')
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.articulo.nombre} x {self.cantidad}"


class Despacho(models.Model):
    """Vale de salida: deja constancia del despacho, del técnico receptor y de su firma."""

    solicitud = models.OneToOneField(SolicitudDespacho, on_delete=models.PROTECT, related_name='despacho')
    despachado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       related_name='despachos_realizados')
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                related_name='despachos_recibidos', verbose_name="Técnico receptor")
    fecha = models.DateTimeField(auto_now_add=True)
    firma_recepcion = models.TextField(help_text="Firma del técnico: imagen PNG en base64 (data URL)")

    class Meta:
        verbose_name = "Despacho (vale de salida)"
        verbose_name_plural = "Despachos (vales de salida)"
        ordering = ['-fecha']

    @property
    def obra(self):
        return self.solicitud.obra

    @property
    def mandante(self):
        return self.solicitud.obra.mandante

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise CardexInalterableError("Un vale de salida ya emitido no se puede modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise CardexInalterableError("Un vale de salida no se puede eliminar.")

    def __str__(self):
        return f"Vale de salida #{self.pk} - Solicitud #{self.solicitud_id}"


# ---------------------------------------------------------------------------
# Inventario físico por sector (HU-05)
# ---------------------------------------------------------------------------
class SesionInventario(models.Model):
    class Estado(models.TextChoices):
        ABIERTA = 'ABIERTA', 'Abierta'
        CERRADA = 'CERRADA', 'Cerrada'

    sector = models.CharField(max_length=50, verbose_name="Sector (ubicación en bodega)")
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ABIERTA)
    abierta_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='sesiones_inventario_abiertas')
    fecha_apertura = models.DateTimeField(auto_now_add=True)
    cerrada_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                    related_name='sesiones_inventario_cerradas')
    fecha_cierre = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True)
    valor_diferencia_total = models.IntegerField(default=0, verbose_name="Valorización de la diferencia (CLP)")

    class Meta:
        verbose_name = "Sesión de inventario físico"
        verbose_name_plural = "Sesiones de inventario físico"
        ordering = ['-fecha_apertura']
        constraints = [
            # Solo una sesión abierta por sector a la vez.
            models.UniqueConstraint(fields=['sector'], condition=Q(estado='ABIERTA'),
                                    name='una_sesion_abierta_por_sector'),
        ]

    def save(self, *args, **kwargs):
        # Una sesión cerrada no se puede reabrir ni editar.
        if self.pk and SesionInventario.objects.filter(pk=self.pk, estado=self.Estado.CERRADA).exists():
            raise CardexInalterableError("Una sesión de inventario cerrada no se puede reabrir ni modificar.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise CardexInalterableError("Una sesión de inventario no se puede eliminar.")

    def __str__(self):
        return f"Inventario #{self.pk} - {self.sector} ({self.get_estado_display()})"


class DetalleSesionInventario(models.Model):
    sesion = models.ForeignKey(SesionInventario, on_delete=models.CASCADE, related_name='detalles')
    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, related_name='detalles_inventario')
    stock_sistema = models.DecimalField(max_digits=10, decimal_places=2)
    stock_contado = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    diferencia = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valor_diferencia = models.IntegerField(default=0)

    class Meta:
        ordering = ['articulo__nombre']
        constraints = [
            models.UniqueConstraint(fields=['sesion', 'articulo'], name='un_detalle_por_articulo_y_sesion'),
        ]

    def save(self, *args, **kwargs):
        if SesionInventario.objects.filter(pk=self.sesion_id, estado=SesionInventario.Estado.CERRADA).exists():
            raise CardexInalterableError("La sesión está cerrada: el conteo no se puede modificar.")
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# Restock: Bodega solicita -> Finanzas aprueba el presupuesto -> Técnico/Bodega recibe e ingresa
# ---------------------------------------------------------------------------
class OrdenRestock(models.Model):
    ESTADO_PENDIENTE_FINANZAS = 'PENDIENTE_FINANZAS'
    ESTADO_APROBADA_FINANZAS = 'APROBADA_FINANZAS'
    ESTADO_INSERTADA = 'INSERTADA'
    ESTADO_RECHAZADA = 'RECHAZADA'

    ESTADOS = [
        (ESTADO_PENDIENTE_FINANZAS, '1. Pendiente Aprobación Finanzas'),
        (ESTADO_APROBADA_FINANZAS, '2. Presupuesto Aprobado (Pendiente Revisión Técnica)'),
        (ESTADO_INSERTADA, '3. Revisado por Técnico e Insertado en Stock'),
        (ESTADO_RECHAZADA, 'Rechazada por Finanzas'),
    ]

    articulo = models.ForeignKey(Articulo, on_delete=models.PROTECT, related_name='ordenes_restock')
    proveedor = models.ForeignKey(Proveedor, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name='ordenes_restock')
    cantidad = models.DecimalField(max_digits=10, decimal_places=2)
    costo_unitario = models.IntegerField(default=0, verbose_name="Costo unitario estimado (CLP)")
    estado = models.CharField(max_length=25, choices=ESTADOS, default=ESTADO_PENDIENTE_FINANZAS)

    solicitado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                       related_name='restocks_solicitados')
    aprobado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='restocks_aprobados')
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='restocks_revisados')
    fecha_solicitud = models.DateTimeField(auto_now_add=True)
    fecha_aprobacion = models.DateTimeField(null=True, blank=True)
    fecha_recepcion = models.DateTimeField(null=True, blank=True)
    observaciones = models.TextField(blank=True, default='')

    class Meta:
        verbose_name = "Orden de restock"
        verbose_name_plural = "Órdenes de restock"
        ordering = ['-fecha_solicitud']

    @property
    def monto_total(self):
        return int(self.cantidad * self.costo_unitario)

    def __str__(self):
        return f"Restock #{self.pk} - {self.articulo.nombre} x {self.cantidad}"
