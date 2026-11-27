"""Enlaza las filas antiguas del Cardex con su movimiento del Kardex operativo.

Solo se enlaza cuando hay una coincidencia única en ambos sentidos (mismo artículo,
cantidad, saldo resultante, usuario, tipo compatible y fecha con pocos segundos de
diferencia). Lo que no calza queda sin vínculo y la vista de Auditoría rechaza anularlo
con un mensaje claro. Esta migración no anula ni crea movimientos: solo completa vínculos.
"""
import re
from datetime import timedelta

from django.db import migrations

# Tipo del Kardex operativo -> tipos posibles en el Cardex (igual que la señal)
TIPOS_COMPATIBLES = {
    'ENTRADA': {'INGRESO'},
    'SALIDA': {'EGRESO', 'DEVOLUCION_PROVEEDOR'},
    'EGRESO_OBRA': {'EGRESO'},
    'MERMA': {'MERMA'},
    'DEVOLUCION_OBRA': {'DEVOLUCION_FAENA'},
    'DEVOLUCION_PROVEEDOR': {'DEVOLUCION_PROVEEDOR'},
    'USO_INTERNO': {'USO_INTERNO'},
    'AJUSTE_POS': {'AJUSTE_INVENTARIO'},
    'AJUSTE_NEG': {'AJUSTE_INVENTARIO'},
    'AJUSTE': {'AJUSTE_INVENTARIO'},
    'ANULACION': {'ANULACION'},
}
TOLERANCIA = timedelta(seconds=10)
RE_ANULACION = re.compile(r'^ANULADO ID#(\d+) ')


def enlazar(apps, schema_editor):
    Cardex = apps.get_model('auditoria', 'MovimientoCardex')
    Inventario = apps.get_model('inventario', 'MovimientoInventario')

    ya_enlazados = set(Cardex.objects.exclude(movimiento_inventario__isnull=True)
                       .values_list('movimiento_inventario_id', flat=True))
    # Los contra-asientos hechos solo en Auditoría (es_reversa=True) no tienen movimiento de inventario
    pendientes = list(Cardex.objects.filter(movimiento_inventario__isnull=True, es_reversa=False))

    candidatos = {}
    for fila in pendientes:
        qs = Inventario.objects.filter(
            articulo_id=fila.articulo_id,
            cantidad=abs(fila.cantidad),
            stock_posterior=fila.saldo_resultante,
            fecha__gte=fila.fecha_hora - TOLERANCIA,
            fecha__lte=fila.fecha_hora + TOLERANCIA,
        ).exclude(pk__in=ya_enlazados)
        coincidencias = [m.pk for m in qs if fila.tipo_movimiento in TIPOS_COMPATIBLES.get(m.tipo_movimiento, set())
                         and (m.usuario_id is None or m.usuario_id == fila.usuario_id)]
        if len(coincidencias) == 1:
            candidatos[fila.pk] = coincidencias[0]

    # Un movimiento de inventario reclamado por dos filas del Cardex es ambiguo: no se enlaza
    usos = {}
    for inv_id in candidatos.values():
        usos[inv_id] = usos.get(inv_id, 0) + 1
    for cardex_id, inv_id in candidatos.items():
        if usos[inv_id] == 1:
            Cardex.objects.filter(pk=cardex_id).update(movimiento_inventario_id=inv_id)

    # Anulaciones hechas desde el Kardex antes del cambio: se marcan como reversa del asiento original
    for fila in Cardex.objects.filter(tipo_movimiento='ANULACION', es_reversa=False,
                                      movimiento_inventario__isnull=False):
        inv = Inventario.objects.filter(pk=fila.movimiento_inventario_id).first()
        coincidencia = RE_ANULACION.match(inv.referencia or '') if inv else None
        if not coincidencia:
            continue
        original = Cardex.objects.filter(movimiento_inventario_id=int(coincidencia.group(1))).first()
        if original and not Cardex.objects.filter(movimiento_reversado=original).exists():
            Cardex.objects.filter(pk=fila.pk).update(es_reversa=True, movimiento_reversado=original)


class Migration(migrations.Migration):

    dependencies = [
        ('auditoria', '0004_movimientocardex_movimiento_inventario'),
    ]

    operations = [
        migrations.RunPython(enlazar, migrations.RunPython.noop),
    ]
