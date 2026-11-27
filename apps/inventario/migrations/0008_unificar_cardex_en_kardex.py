"""Unifica el Cardex de Auditoría en el Kardex (MovimientoInventario) antes de borrar la copia.

1. Los contra-asientos existentes quedan enlazados a su movimiento original
   (movimiento_anulado), leyendo la referencia "ANULADO ID#<id> ".
2. Las anulaciones antiguas hechas solo en el Cardex de Auditoría (cambiaron el stock pero
   no dejaron fila en el Kardex) se agregan al Kardex como ANULACION con su fecha, usuario,
   saldo y motivo originales. Así la historia completa queda en una sola tabla.
No se modifica ni se borra ningún movimiento existente del Kardex: solo se completan
vínculos nulos y se agregan los contra-asientos que faltaban.
"""
import re
from decimal import Decimal

from django.db import migrations

RE_ANULACION = re.compile(r'^ANULADO ID#(\d+) ')


def unificar(apps, schema_editor):
    Kardex = apps.get_model('inventario', 'MovimientoInventario')
    Cardex = apps.get_model('auditoria', 'MovimientoCardex')

    def ya_anulado(mov_id):
        return Kardex.objects.filter(movimiento_anulado_id=mov_id).exists()

    # 1. Contra-asientos del Kardex sin vínculo
    for contra in Kardex.objects.filter(tipo_movimiento='ANULACION', movimiento_anulado__isnull=True).order_by('id'):
        coincidencia = RE_ANULACION.match(contra.referencia or '')
        if not coincidencia:
            continue
        original_id = int(coincidencia.group(1))
        original = Kardex.objects.filter(pk=original_id).exclude(tipo_movimiento='ANULACION').first()
        if original and not ya_anulado(original_id):
            Kardex.objects.filter(pk=contra.pk).update(movimiento_anulado_id=original_id)

    # 2. Anulaciones que existen solo en el Cardex de Auditoría
    for fila in Cardex.objects.filter(es_reversa=True, movimiento_inventario__isnull=True).order_by('fecha_hora', 'id'):
        original_id = None
        if fila.movimiento_reversado_id:
            original_id = Cardex.objects.filter(pk=fila.movimiento_reversado_id).values_list(
                'movimiento_inventario_id', flat=True).first()
        if original_id and ya_anulado(original_id):
            original_id = None  # ya tiene contra-asiento en el Kardex: se registra sin duplicar el vínculo
        cantidad = Decimal(fila.cantidad)
        nuevo = Kardex.objects.create(
            articulo_id=fila.articulo_id,
            tipo_movimiento='ANULACION',
            cantidad=abs(cantidad),
            stock_anterior=Decimal(fila.saldo_resultante) - cantidad,
            stock_posterior=fila.saldo_resultante,
            costo_unitario=int(fila.valor_unitario or 0),
            usuario_id=fila.usuario_id,
            obra_id=fila.obra_id,
            referencia=(f"ANULADO ID#{original_id} " if original_id else "ANULACIÓN ")
                       + f"(histórica desde Cardex de Auditoría, asiento #{fila.pk})",
            justificacion=fila.justificacion,
            movimiento_anulado_id=original_id,
        )
        Kardex.objects.filter(pk=nuevo.pk).update(fecha=fila.fecha_hora)


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0007_movimientoinventario_movimiento_anulado'),
        ('auditoria', '0005_enlazar_cardex_con_inventario'),
    ]

    operations = [
        migrations.RunPython(unificar, migrations.RunPython.noop),
    ]
