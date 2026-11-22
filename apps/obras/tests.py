
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.entidades.models import Proveedor
from .models import Obra


class ObraModelTest(TestCase):

    def setUp(self):
        self.mandante = Proveedor.objects.create(
            rut='76543210-3',
            razon_social='Empresa Mandante de Prueba',
            tipo=Proveedor.Tipo.MANDANTE,
            activo=True,
        )

    def test_crear_obra_correctamente(self):
        obra = Obra.objects.create(
            nombre='Construcción de prueba',
            mandante=self.mandante,
            presupuesto_total=Decimal('1500000.00'),
        )

        self.assertEqual(obra.nombre, 'Construcción de prueba')
        self.assertEqual(obra.mandante, self.mandante)
        self.assertEqual(
            obra.presupuesto_total,
            Decimal('1500000.00')
        )
        self.assertEqual(obra.estado, Obra.Estado.ACTIVA)

    def test_presupuesto_negativo_no_es_valido(self):
        obra = Obra(
            nombre='Obra con presupuesto negativo',
            mandante=self.mandante,
            presupuesto_total=Decimal('-1000.00'),
        )

        with self.assertRaises(ValidationError):
            obra.full_clean()

    def test_no_aceptar_proveedor_como_mandante(self):
        proveedor = Proveedor.objects.create(
            rut='76123456-0',
            razon_social='Proveedor de Prueba',
            tipo=Proveedor.Tipo.PROVEEDOR,
            activo=True,
        )

        obra = Obra(
            nombre='Obra con proveedor incorrecto',
            mandante=proveedor,
            presupuesto_total=Decimal('100000.00'),
        )

        with self.assertRaises(ValidationError):
            obra.full_clean()

    def test_no_aceptar_mandante_inactivo(self):
        self.mandante.activo = False
        self.mandante.save()

        obra = Obra(
            nombre='Obra con mandante inactivo',
            mandante=self.mandante,
            presupuesto_total=Decimal('100000.00'),
        )

        with self.assertRaises(ValidationError):
            obra.full_clean()

    def test_nombre_de_obra(self):
        obra = Obra(
            nombre='Obra de prueba',
            mandante=self.mandante,
            presupuesto_total=Decimal('500000.00'),
        )

        self.assertEqual(str(obra), 'Obra de prueba')
