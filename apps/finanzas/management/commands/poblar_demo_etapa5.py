from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.catalogo.models import Articulo, Categoria
from apps.entidades.models import Proveedor
from apps.inventario.models import DocumentoEntrada, DetalleDocumento, MovimientoInventario


class Command(BaseCommand):
    help = 'Crea datos locales de demostración para probar reportes de facturas en Finanzas.'

    @transaction.atomic
    def handle(self, *args, **options):
        categoria, _ = Categoria.objects.get_or_create(
            nombre='Materiales de prueba Finanzas',
        )
        proveedor, _ = Proveedor.objects.get_or_create(
            rut='76.111.222-8',
            defaults={
                'razon_social': 'Proveedor de Prueba Etapa 5 SpA',
                'nombre_fantasia': 'Proveedor Demo',
                'giro': 'Venta de materiales para demostración',
                'tipo': Proveedor.Tipo.PROVEEDOR,
                'telefono': '+56 9 5555 0101',
                'email': 'demo@fyag.cl',
                'direccion': 'Dirección de prueba, Santiago',
                'activo': True,
            },
        )
        usuario = get_user_model().objects.filter(is_superuser=True).first()

        documento, _ = DocumentoEntrada.objects.get_or_create(
            proveedor=proveedor,
            tipo_documento=DocumentoEntrada.TIPO_FACTURA,
            numero_documento='DEMO-ET5-001',
            defaults={
                'fecha_emision': timezone.localdate(),
                'registrado_por': usuario,
                'observaciones': 'Documento de demostración para probar los reportes de Finanzas.',
                'estado': DocumentoEntrada.ESTADO_CONFIRMADO,
            },
        )

        items = [
            ('TEST-FIN-001', 'Tornillo galvanizado de prueba', 'UND', Decimal('10.00'), 250),
            ('TEST-FIN-002', 'Cable eléctrico de prueba', 'MTS', Decimal('8.00'), 850),
            ('TEST-FIN-003', 'Pintura anticorrosiva de prueba', 'CIL', Decimal('3.00'), 6900),
        ]
        monto_neto = 0

        for codigo, nombre, unidad, cantidad, precio in items:
            articulo, _ = Articulo.objects.get_or_create(
                codigo_interno=codigo,
                defaults={
                    'nombre': nombre,
                    'categoria': categoria,
                    'unidad_medida': unidad,
                    'ubicacion_bodega': 'Bodega de pruebas',
                },
            )
            subtotal = int(cantidad * precio)
            monto_neto += subtotal
            DetalleDocumento.objects.update_or_create(
                documento=documento,
                articulo=articulo,
                defaults={
                    'cantidad': cantidad,
                    'precio_unitario_base': precio,
                    'precio_unitario_final': precio,
                    'subtotal_linea': subtotal,
                },
            )

            if not MovimientoInventario.objects.filter(
                documento=documento,
                articulo=articulo,
            ).exists():
                stock_anterior = articulo.stock_actual
                stock_posterior = stock_anterior + cantidad
                costo_total = (
                    Decimal(str(stock_anterior)) * Decimal(articulo.pmp_costo_actual)
                    + cantidad * Decimal(precio)
                )
                pmp = int(
                    (costo_total / Decimal(str(stock_posterior))).quantize(
                        Decimal('1'),
                        rounding=ROUND_HALF_UP,
                    )
                )
                articulo.stock_actual = stock_posterior
                articulo.pmp_costo_actual = pmp
                articulo.ultimo_costo_compra = precio
                articulo.save(update_fields=[
                    'stock_actual',
                    'pmp_costo_actual',
                    'ultimo_costo_compra',
                ])
                MovimientoInventario.objects.create(
                    articulo=articulo,
                    documento=documento,
                    tipo_movimiento=MovimientoInventario.TIPO_ENTRADA,
                    cantidad=cantidad,
                    stock_anterior=stock_anterior,
                    stock_posterior=stock_posterior,
                    costo_unitario=precio,
                    usuario=usuario,
                    referencia=f'Demostración de factura {documento.numero_documento}',
                )

        documento.monto_neto = monto_neto
        documento.save(update_fields=['monto_neto'])
        self.stdout.write(self.style.SUCCESS(
            f'Datos de demostración disponibles: factura {documento.numero_documento}, '
            f'neto ${documento.monto_neto} CLP.'
        ))
