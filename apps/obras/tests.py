
import base64
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.catalogo.models import Articulo, Categoria
from apps.entidades.models import Proveedor
from apps.inventario.models import DetalleSolicitud, MovimientoInventario as M, SolicitudDespacho
from apps.inventario.services import despachar, registrar_salida_tipificada
from .models import HojaServicioObra, Obra, SolicitudMaterialObra

# PNG mínimo válido (1x1) para la firma del técnico, igual que en tests_bodega
PNG = 'data:image/png;base64,' + base64.b64encode(
    b'\x89PNG\r\n\x1a\n' + b'\x00' * 40).decode()


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


class ObraEvaluacionFinancieraTest(TestCase):
    """Costos reales de la obra: materiales netos (egresos - devoluciones) + mano de obra."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        grupos = {n: Group.objects.create(name=n) for n in ('bodega', 'tecnico', 'supervisor')}
        cls.bodeguero = User.objects.create_user('bodeguero_obra', password='x')
        cls.bodeguero.groups.add(grupos['bodega'])
        cls.tecnico = User.objects.create_user('tecnico_obra', password='x')
        cls.tecnico.groups.add(grupos['tecnico'])
        cls.supervisor = User.objects.create_user('supervisor_obra', password='x')
        cls.supervisor.groups.add(grupos['supervisor'])
        cls.mandante = Proveedor.objects.create(rut='76543210-3', razon_social='Mandante Financiero SpA',
                                                tipo=Proveedor.Tipo.MANDANTE)
        cls.articulo = Articulo.objects.create(
            codigo_interno='OB-1', nombre='Panel aislante', categoria=Categoria.objects.create(nombre='Paneles'),
            ubicacion_bodega='Pasillo B', stock_actual=Decimal('50'), pmp_costo_actual=20000,
            ultimo_costo_compra=20000)

    def _obra_con_costos(self, presupuesto):
        obra = Obra.objects.create(
            nombre=f'Obra {presupuesto}', mandante=self.mandante, presupuesto_total=Decimal(presupuesto),
            costo_mano_obra_estimado=Decimal('100000'), tarifa_hora_mano_obra=Decimal('15000'),
        )
        # Egreso de 10 unidades a $20.000 mediante el despacho real de Bodega
        solicitud = SolicitudDespacho.objects.create(obra=obra, solicitante=self.supervisor)
        DetalleSolicitud.objects.create(solicitud=solicitud, articulo=self.articulo, cantidad=10)
        despachar(solicitud.pk, self.bodeguero, self.tecnico.pk, PNG)
        # Devolución de 2 unidades desde la obra
        registrar_salida_tipificada(M.TIPO_DEVOLUCION_OBRA, self.articulo.pk, 2, self.bodeguero,
                                    'Sobrante devuelto desde la obra', obra=obra)
        for horas in ('5', '3'):
            HojaServicioObra.objects.create(
                obra=obra, tecnico_responsable='Técnico de prueba', descripcion_trabajo='Montaje de paneles',
                horas_invertidas=Decimal(horas), fecha_servicio=timezone.localdate(), registrado_por=self.supervisor,
            )
        # costo_materiales y total_horas_trabajadas son cached_property: se relee la obra
        return Obra.objects.get(pk=obra.pk)

    def test_obra_con_ganancia(self):
        obra = self._obra_con_costos('1000000')
        self.assertEqual(obra.costo_materiales, Decimal('160000'))
        self.assertEqual(obra.costo_mano_obra_estimado, Decimal('100000'))
        self.assertEqual(obra.total_horas_trabajadas, Decimal('8'))
        self.assertEqual(obra.costo_mano_obra_real, Decimal('220000'))
        self.assertEqual(obra.costo_total_real, Decimal('380000'))
        self.assertEqual(obra.utilidad_actual, Decimal('620000'))
        self.assertEqual(obra.margen_real_porcentaje, Decimal('62.0'))
        self.assertTrue(obra.es_rentable)

    def test_obra_con_perdida(self):
        obra = self._obra_con_costos('300000')
        self.assertEqual(obra.costo_total_real, Decimal('380000'))
        self.assertEqual(obra.utilidad_actual, Decimal('-80000'))
        self.assertEqual(obra.margen_real_porcentaje, Decimal('-26.7'))
        self.assertFalse(obra.es_rentable)

    def test_pedido_de_material_crea_solicitud_enlazada_en_bodega(self):
        obra = Obra.objects.create(nombre='Obra pedido', mandante=self.mandante, supervisor=self.supervisor)
        self.client.force_login(self.supervisor)
        r = self.client.post(reverse('obras:lista_solicitudes'), {
            'obra': obra.pk, 'articulo': self.articulo.pk, 'cantidad': '4', 'sector': 'Cámara 2',
        })
        self.assertRedirects(r, reverse('obras:lista_solicitudes'))
        solicitud = SolicitudMaterialObra.objects.get(obra=obra)
        self.assertEqual(solicitud.estado, SolicitudMaterialObra.EstadoSolicitud.PENDIENTE)
        despacho = solicitud.solicitud_despacho
        self.assertIsNotNone(despacho)
        self.assertEqual(despacho.solicitud_obra, solicitud)
        self.assertEqual(despacho.estado, SolicitudDespacho.Estado.PENDIENTE)
        self.assertEqual(despacho.obra, obra)
        self.assertEqual(list(despacho.detalles.values_list('articulo_id', 'cantidad')),
                         [(self.articulo.pk, Decimal('4'))])
        # Bodega todavía no descuenta stock: solo despacha desde su bandeja
        self.articulo.refresh_from_db()
        self.assertEqual(self.articulo.stock_actual, Decimal('50'))
