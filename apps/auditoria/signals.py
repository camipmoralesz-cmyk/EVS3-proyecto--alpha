
from apps.inventario.models import MovimientoInventario
from .models import MovimientoCardex


@receiver(post_save, sender=MovimientoInventario)
def sincronizar_movimiento_a_cardex(sender, instance, created, **kwargs):
    """
    Cada vez que el módulo de Inventario registra un movimiento operativo,
    se asienta automáticamente una copia inmutable en MovimientoCardex para auditoría.
    """
    if not created:
        return

    # Evitar duplicados si el movimiento fue generado por una anulación desde Auditoría
    if instance.referencia and instance.referencia.startswith("ANULACION_AUDITORIA:"):
        return

    mapa_tipos = {
        'ENTRADA': 'INGRESO',
        'SALIDA': 'EGRESO',
        'AJUSTE': 'AJUSTE_INVENTARIO',
    }

    tipo_cardex = mapa_tipos.get(instance.tipo_movimiento, 'INGRESO')
    if instance.documento and instance.documento.tipo_documento == 'NOTA_CREDITO':
        tipo_cardex = 'DEVOLUCION_PROVEEDOR'

    # Si es salida, la cantidad en Cardex se guarda negativa para mantener la suma algebraica
    cantidad_signed = int(instance.cantidad) if instance.tipo_movimiento == 'ENTRADA' else -int(abs(instance.cantidad))

    doc_ref = ""
    if instance.documento:
        doc_ref = f"{instance.documento.get_tipo_documento_display()} N° {instance.documento.numero_documento}"

    MovimientoCardex.objects.create(
        articulo=instance.articulo,
        tipo_movimiento=tipo_cardex,
        cantidad=cantidad_signed,
        saldo_resultante=int(instance.stock_posterior),
        valor_unitario=instance.costo_unitario,
        usuario=instance.usuario or get_current_user(),
        documento_referencia=doc_ref,
        justificacion=instance.referencia or f"Movimiento automático desde Inventario ({doc_ref or 'Sin documento'})",
        es_reversa=False
    )