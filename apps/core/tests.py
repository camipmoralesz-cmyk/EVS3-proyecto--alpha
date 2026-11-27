from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.catalogo.models import Articulo, Categoria
from apps.inventario.models import MovimientoInventario as M
from apps.inventario.services import registrar_movimiento


class KardexAuditorSoloLecturaTests(TestCase):
    """El auditor consulta el mismo Kardex de Gerencia, pero sin anular ni registrar."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.gerente = User.objects.create_user('gerente', password='x')
        cls.gerente.groups.add(Group.objects.create(name='gerencia'))
        cls.auditor = User.objects.create_user('auditor', password='x')
        cls.auditor.groups.add(Group.objects.create(name='Auditor'))
        cls.bodeguero = User.objects.create_user('bodeguero', password='x')
        cls.bodeguero.groups.add(Group.objects.create(name='bodega'))
        cls.articulo = Articulo.objects.create(
            codigo_interno='K-1', nombre='Compresor', categoria=Categoria.objects.create(nombre='Equipos'),
            ubicacion_bodega='Pasillo C', stock_actual=Decimal('0'))
        cls.mov = registrar_movimiento(cls.articulo.pk, M.TIPO_AJUSTE_POS, 5, cls.bodeguero, 'Carga inicial',
                                       justificacion='Conteo inicial de bodega')

    def test_auditor_ve_el_kardex_sin_acciones_de_anulacion(self):
        self.client.force_login(self.auditor)
        r = self.client.get(reverse('core:auditoria_kardex'))
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn('Compresor', html)
        self.assertIn('Modo solo lectura', html)
        self.assertNotIn(reverse('core:anular_movimiento', args=[self.mov.pk]), html)
        self.assertNotIn('modalContraAsiento"', html)
        self.assertNotIn(reverse('core:exportar_pdf', args=['kardex']), html)
        # Enlace en su panel del sidebar
        self.assertIn(f'href="{reverse("core:auditoria_kardex")}"', html)

    def test_auditor_no_puede_anular_por_post(self):
        self.client.force_login(self.auditor)
        total = M.objects.count()
        r = self.client.post(reverse('core:anular_movimiento', args=[self.mov.pk]), {'motivo': 'Intento del auditor'})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(M.objects.count(), total)
        self.articulo.refresh_from_db()
        self.assertEqual(self.articulo.stock_actual, Decimal('5'))

    def test_auditor_no_registra_movimientos(self):
        self.client.force_login(self.auditor)
        for nombre in ('registro_documento', 'salida_tipificada', 'lista_solicitudes'):
            with self.subTest(vista=nombre):
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403)

    def test_gerencia_mantiene_la_anulacion(self):
        self.client.force_login(self.gerente)
        html = self.client.get(reverse('core:auditoria_kardex')).content.decode()
        self.assertIn(reverse('core:anular_movimiento', args=[self.mov.pk]), html)
        self.assertNotIn('Modo solo lectura', html)
        self.client.post(reverse('core:anular_movimiento', args=[self.mov.pk]), {'motivo': 'Error de digitación'})
        self.assertTrue(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).exists())

    def test_bodega_lee_el_kardex_unico_y_tecnico_no_accede(self):
        # Kardex único: Bodega lo consulta en solo lectura; Técnico y Supervisor no lo ven
        self.client.force_login(self.bodeguero)
        r = self.client.get(reverse('core:auditoria_kardex'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Modo solo lectura')
        self.assertNotContains(r, reverse('core:anular_movimiento', args=[self.mov.pk]))
        tecnico = get_user_model().objects.create_user('tecnico_kardex', password='x')
        tecnico.groups.add(Group.objects.create(name='tecnico'))
        self.client.force_login(tecnico)
        self.assertEqual(self.client.get(reverse('core:auditoria_kardex')).status_code, 403)
