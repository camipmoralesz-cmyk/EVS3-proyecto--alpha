from django.db import models
from django.conf import settings
from decimal import Decimal
from apps.catalogo.models import Articulo
from apps.entidades.models import Proveedor

class DocumentoEntrada(models.Model):
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

    ESTADOS = [
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


class MovimientoInventario(models.Model):
    TIPO_ENTRADA = 'ENTRADA'
    TIPO_SALIDA = 'SALIDA'
    TIPO_AJUSTE = 'AJUSTE'

    TIPOS_MOVIMIENTO = [
        (TIPO_ENTRADA, 'Entrada de Mercadería'),
        (TIPO_SALIDA, 'Salida / Ajuste Nota de Crédito'),
        (TIPO_AJUSTE, 'Ajuste de Inventario'),
    ]

    articulo = models.ForeignKey(
        Articulo,
        on_delete=models.PROTECT,
        related_name='movimientos_inventario',
        verbose_name="Artículo"
    )
    documento = models.ForeignKey(
        DocumentoEntrada,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos_generados',
        verbose_name="Documento Origen"
    )
    tipo_movimiento = models.CharField(
        max_length=15,
        choices=TIPOS_MOVIMIENTO,
        verbose_name="Tipo de Movimiento"
    )
    cantidad = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Cantidad"
    )
    stock_anterior = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Stock Anterior"
    )
    stock_posterior = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Stock Posterior"
    )
    costo_unitario = models.IntegerField(
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
        verbose_name="Referencia / Glosa"
    )

    class Meta:
        verbose_name = "Movimiento de Inventario"
        verbose_name_plural = "Movimientos de Inventario"
        ordering = ['-fecha']

    def __str__(self):
        return f"[{self.tipo_movimiento}] {self.articulo.codigo_interno} ({self.cantidad}) - {self.fecha.strftime('%Y-%m-%d %H:%M')}"
