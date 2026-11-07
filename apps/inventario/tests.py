from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from apps.catalogo.models import Categoria, Articulo
from apps.entidades.models import Proveedor
from apps.inventario.models import DocumentoEntrada, DetalleDocumento, MovimientoInventario
from apps.inventario.services import (
    calcular_descuentos_sucesivos,
    calcular_subtotal_linea,
    registrar_documento_entrada
)

class CalculoDescuentosTest(TestCase):
    """
    Pruebas unitarias para la lógica matemática de descuentos sucesivos (HU-01).
    """
    def test_sin_descuentos(self):
        # Precio base 10.000 sin descuentos -> 10.000
        resultado = calcular_descuentos_sucesivos(10000, 0, 0, 0)
        self.assertEqual(resultado, 10000)

    def test_un_descuento(self):
        # 10.000 con 10% de descuento -> 9.000
        resultado = calcular_descuentos_sucesivos(10000, 10, 0, 0)
        self.assertEqual(resultado, 9000)

    def test_dos_descuentos_sucesivos(self):
        # 10.000 con 10% -> 9.000; luego 5% sobre 9.000 -> 8.550
        resultado = calcular_descuentos_sucesivos(10000, 10, 5, 0)
        self.assertEqual(resultado, 8550)

    def test_tres_descuentos_sucesivos_independientes(self):
        # 10.000 con 10% -> 9.000; luego 5% -> 8.550; luego 2% -> 8.379
        resultado = calcular_descuentos_sucesivos(10000, 10, 5, 2)
        self.assertEqual(resultado, 8379)

    def test_descuento_invalido_lanza_error(self):
        with self.assertRaises(ValidationError):
            calcular_descuentos_sucesivos(10000, 105, 0, 0)
        with self.assertRaises(ValidationError):
            calcular_descuentos_sucesivos(10000, -5, 0, 0)

    def test_subtotal_linea(self):
        # 8.379 * 5 unidades = 41.895
        subtotal = calcular_subtotal_linea(8379, 5)
        self.assertEqual(subtotal, 41895)


class TransaccionInventarioTest(TestCase):
    """
    Pruebas para verificar la atomicidad y seguridad en la actualización
    de stock, costos y registro de movimientos de inventario (HU-01).
    """
    def setUp(self):
        self.categoria = Categoria.objects.create(nombre="Materiales Básicos")
        self.articulo1 = Articulo.objects.create(
            codigo_interno="CBL-001",
            nombre="Cable de Cobre 2.5mm",
            categoria=self.categoria,
            unidad_medida="MTS",
            ubicacion_bodega="Pasillo 1 - Estante A",
            stock_actual=Decimal('100.00'),
            stock_minimo=Decimal('20.00'),
            stock_critico=Decimal('10.00'),
            pmp_costo_actual=1500,
            ultimo_costo_compra=1500
        )
        self.articulo2 = Articulo.objects.create(
            codigo_interno="DIS-002",
            nombre="Disyuntor Monofásico 16A",
            categoria=self.categoria,
            unidad_medida="UND",
            ubicacion_bodega="Pasillo 2 - Estante C",
            stock_actual=Decimal('50.00'),
            stock_minimo=Decimal('10.00'),
            stock_critico=Decimal('5.00'),
            pmp_costo_actual=4000,
            ultimo_costo_compra=4000
        )
        self.proveedor = Proveedor.objects.create(
            rut="76.999.888-1",
            razon_social="Distribuidora Eléctrica Central S.A."
        )

    def test_ingreso_factura_actualiza_stock_y_costos_exitosamente(self):
        datos_doc = {
            'proveedor': self.proveedor,
            'tipo_documento': DocumentoEntrada.TIPO_FACTURA,
            'numero_documento': 'FAC-8899',
            'fecha_emision': '2026-11-07',
            'observaciones': 'Ingreso conforme de materiales'
        }
        lineas = [
            {
                'articulo_id': self.articulo1.id,
                'cantidad': Decimal('50.00'),
                'precio_unitario_base': 2000,
                'descuento_1_porcentaje': Decimal('10.00'),
                'descuento_2_porcentaje': Decimal('5.00'),
                'descuento_3_porcentaje': Decimal('0.00'),
            },
            {
                'articulo_id': self.articulo2.id,
                'cantidad': Decimal('20.00'),
                'precio_unitario_base': 5000,
                'descuento_1_porcentaje': Decimal('0.00'),
                'descuento_2_porcentaje': Decimal('0.00'),
                'descuento_3_porcentaje': Decimal('0.00'),
            }
        ]

        doc = registrar_documento_entrada(datos_doc, lineas)

        # 1. Verificar Documento creado
        self.assertEqual(doc.numero_documento, 'FAC-8899')
        self.assertEqual(doc.detalles.count(), 2)

        # 2. Verificar actualización de Articulo 1:
        # Precio final = 2000 * 0.9 * 0.95 = 1710
        # Stock: 100 + 50 = 150
        self.articulo1.refresh_from_db()
        self.assertEqual(self.articulo1.stock_actual, Decimal('150.00'))
        self.assertEqual(self.articulo1.ultimo_costo_compra, 1710)

        # 3. Verificar Articulo 2:
        # Stock: 50 + 20 = 70
        self.articulo2.refresh_from_db()
        self.assertEqual(self.articulo2.stock_actual, Decimal('70.00'))
        self.assertEqual(self.articulo2.ultimo_costo_compra, 5000)

        # 4. Total Neto del documento
        # Subtotal art1 = 1710 * 50 = 85.500
        # Subtotal art2 = 5000 * 20 = 100.000
        # Total = 185.500
        self.assertEqual(doc.monto_neto, 185500)

        # 5. Verificar logs de auditoría en MovimientoInventario
        movs = MovimientoInventario.objects.filter(documento=doc)
        self.assertEqual(movs.count(), 2)
        mov1 = movs.get(articulo=self.articulo1)
        self.assertEqual(mov1.stock_anterior, Decimal('100.00'))
        self.assertEqual(mov1.stock_posterior, Decimal('150.00'))
        self.assertEqual(mov1.tipo_movimiento, MovimientoInventario.TIPO_ENTRADA)

    def test_nota_credito_disminuye_stock(self):
        datos_doc = {
            'proveedor': self.proveedor,
            'tipo_documento': DocumentoEntrada.TIPO_NOTA_CREDITO,
            'numero_documento': 'NC-101',
            'fecha_emision': '2026-11-07',
            'observaciones': 'Devolución de 10 unidades de disyuntor defectuoso'
        }
        lineas = [
            {
                'articulo_id': self.articulo2.id,
                'cantidad': Decimal('10.00'),
                'precio_unitario_base': 4000,
                'descuento_1_porcentaje': 0,
                'descuento_2_porcentaje': 0,
                'descuento_3_porcentaje': 0,
            }
        ]

        doc = registrar_documento_entrada(datos_doc, lineas)

        self.articulo2.refresh_from_db()
        # Stock original era 50, disminuye a 40
        self.assertEqual(self.articulo2.stock_actual, Decimal('40.00'))

        # Log de auditoría debe registrar SALIDA
        mov = MovimientoInventario.objects.get(documento=doc)
        self.assertEqual(mov.tipo_movimiento, MovimientoInventario.TIPO_SALIDA)
        self.assertEqual(mov.stock_anterior, Decimal('50.00'))
        self.assertEqual(mov.stock_posterior, Decimal('40.00'))

    def test_atomicidad_rollback_si_falla_una_linea(self):
        """
        Verifica que si una línea falla (ej. nota de crédito con más stock del existente),
        la transacción completa se revierte sin dejar registros huérfanos ni alterar stocks.
        """
        datos_doc = {
            'proveedor': self.proveedor,
            'tipo_documento': DocumentoEntrada.TIPO_NOTA_CREDITO,
            'numero_documento': 'NC-FALLIDA',
            'fecha_emision': '2026-11-07',
        }
        lineas = [
            {
                # Línea 1 válida: descuenta 10 del artículo 1
                'articulo_id': self.articulo1.id,
                'cantidad': Decimal('10.00'),
                'precio_unitario_base': 1500,
                'descuento_1_porcentaje': 0,
            },
            {
                # Línea 2 INVÁLIDA: intenta descontar 999 unidades cuando solo hay 50
                'articulo_id': self.articulo2.id,
                'cantidad': Decimal('999.00'),
                'precio_unitario_base': 4000,
                'descuento_1_porcentaje': 0,
            }
        ]

        # Debe lanzar ValidationError
        with self.assertRaises(ValidationError):
            registrar_documento_entrada(datos_doc, lineas)

        # Verificar que el documento NO se creó
        self.assertFalse(DocumentoEntrada.objects.filter(numero_documento='NC-FALLIDA').exists())

        # Verificar que el stock de artículo 1 NO se modificó (Rollback atómico)
        self.articulo1.refresh_from_db()
        self.assertEqual(self.articulo1.stock_actual, Decimal('100.00'))

        # Verificar que no quedaron movimientos huérfanos
        self.assertEqual(MovimientoInventario.objects.count(), 0)
