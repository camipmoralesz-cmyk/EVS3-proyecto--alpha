# Los ingresos y salidas del sistema ya no se guardan como MovimientoInventario:
# se registran en LogAcceso (apps/auditoria/signals.py) para no mezclar accesos
# con los movimientos de stock de Bodega.
