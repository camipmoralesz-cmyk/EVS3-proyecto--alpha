from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.catalogo.models import Articulo, Categoria
from apps.inventario.models import MovimientoInventario as M
from apps.inventario.services import registrar_movimiento
from .models import BitacoraAuditoria, LogAcceso, MovimientoCardex

User = get_user_model()


class AuditoriaSeguridadTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.grupo_auditor, _ = Group.objects.get_or_create(name='AUDITOR')
        self.auditor = User.objects.create_user(username='auditor_test', password='Password123!')
        self.auditor.groups.add(self.grupo_auditor)

        self.operario = User.objects.create_user(username='bodega_test', password='Password123!')

    def test_bitacora_inmutable_impide_editar_y_borrar(self):
        registro = BitacoraAuditoria.objects.create(
            usuario=self.auditor,
            modulo='Catalogo',
            accion='CREAR',
            modelo_afectado='Articulo',
            objeto_id='1',
            descripcion='Prueba inmutabilidad'
        )
        # Intentar editar individualmente debe lanzar PermissionDenied
        registro.descripcion = 'Alterado'
        with self.assertRaises(PermissionDenied):
            registro.save()

        # Intentar borrar individualmente o masivamente debe lanzar PermissionDenied
        with self.assertRaises(PermissionDenied):
            registro.delete()
        with self.assertRaises(PermissionDenied):
            BitacoraAuditoria.objects.all().delete()

    def test_acceso_rbc_auditor_vs_operario(self):
        # Un usuario sin rol auditor recibe 403 Forbidden
        self.client.login(username='bodega_test', password='Password123!')
        resp_denegado = self.client.get('/auditoria/cardex/')
        self.assertEqual(resp_denegado.status_code, 403)

        # Un auditor puede ver Cardex en modo lectura, pero NO puede anular
        self.client.login(username='auditor_test', password='Password123!')
        resp_ok = self.client.get('/auditoria/cardex/')
        self.assertEqual(resp_ok.status_code, 200)

        resp_anular = self.client.post('/auditoria/cardex/anular/', {'movimiento_id': 1, 'motivo_anulacion': 'Intento no autorizado'})
        self.assertEqual(resp_anular.status_code, 403)

    def test_logs_acceso_registran_exitos_y_fallos(self):
        self.client.login(username='auditor_test', password='Password123!')
        self.client.login(username='auditor_test', password='ClaveIncorrecta')
        self.assertTrue(LogAcceso.objects.filter(username_intentado='auditor_test', exitoso=True).exists())
        self.assertTrue(LogAcceso.objects.filter(username_intentado='auditor_test', exitoso=False).exists())


class AnulacionUnificadaTests(TestCase):
    """Se anula solo desde el Kardex de Gerencia; el Cardex de Auditoría es de solo lectura
    para todos y muestra el contra-asiento enlazado al asiento original."""

    @classmethod
    def setUpTestData(cls):
        cls.gerente = User.objects.create_user('gerente_anula', password='x')
        cls.gerente.groups.add(Group.objects.create(name='gerencia'))
        cls.bodeguero = User.objects.create_user('bodega_anula', password='x')
        cls.bodeguero.groups.add(Group.objects.create(name='bodega'))
        cls.auditor = User.objects.create_user('auditor_anula', password='x')
        cls.auditor.groups.add(Group.objects.create(name='Auditor'))
        cls.consulta = User.objects.create_user('consulta_anula', password='x')
        cls.consulta.groups.add(Group.objects.create(name='consulta'))

    def setUp(self):
        # Stock 100 después de una entrada de 10
        self.articulo = Articulo.objects.create(
            codigo_interno='AN-1', nombre='Válvula', categoria=Categoria.objects.create(nombre='Válvulas'),
            ubicacion_bodega='Pasillo D', stock_actual=Decimal('90'))
        self.entrada = registrar_movimiento(self.articulo.pk, M.TIPO_ENTRADA, 10, self.bodeguero, 'Entrada de prueba')
        self.asiento = MovimientoCardex.objects.get(movimiento_inventario=self.entrada)
        self.client.force_login(self.gerente)

    def stock(self):
        self.articulo.refresh_from_db()
        return self.articulo.stock_actual

    def anular_core(self, motivo='Error de digitación'):
        return self.client.post(reverse('core:anular_movimiento', args=[self.entrada.pk]), {'motivo': motivo})

    def anular_auditoria(self, asiento=None, motivo='Error de digitación en la entrada'):
        return self.client.post(reverse('auditoria:anular_movimiento'),
                                {'movimiento_id': (asiento or self.asiento).pk, 'motivo_anulacion': motivo})

    def test_anular_en_core_y_luego_en_auditoria_se_rechaza(self):
        self.assertEqual(self.stock(), Decimal('100'))
        self.anular_core()
        self.assertEqual(self.stock(), Decimal('90'))

        r = self.anular_auditoria()
        self.assertRedirects(r, reverse('core:auditoria_kardex'))
        self.assertEqual(self.stock(), Decimal('90'))
        self.assertEqual(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).count(), 1)
        self.assertEqual(MovimientoCardex.objects.filter(tipo_movimiento='ANULACION').count(), 1)
        # El contra-asiento copiado al Cardex queda enlazado al asiento original
        contra = MovimientoCardex.objects.get(tipo_movimiento='ANULACION')
        self.assertTrue(contra.es_reversa)
        self.assertEqual(contra.movimiento_reversado, self.asiento)
        self.assertEqual(self.asiento.contra_asiento, contra)

    def test_auditoria_no_anula_ni_siquiera_gerencia(self):
        r = self.anular_auditoria()
        self.assertRedirects(r, reverse('core:auditoria_kardex'))
        self.assertEqual(self.stock(), Decimal('100'))
        self.assertFalse(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).exists())
        self.assertFalse(MovimientoCardex.objects.filter(tipo_movimiento='ANULACION').exists())

    def test_cardex_es_solo_lectura_y_muestra_la_anulacion(self):
        self.anular_core()
        contra = MovimientoCardex.objects.get(tipo_movimiento='ANULACION')
        for usuario in (self.gerente, self.auditor):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                html = self.client.get(reverse('auditoria:lista_cardex')).content.decode()
                self.assertNotIn('modalAnular', html)
                self.assertNotIn(reverse('auditoria:anular_movimiento'), html)
                self.assertIn(f'Anulado por #{contra.pk}', html)

    def test_segunda_anulacion_en_core_se_rechaza(self):
        self.anular_core()
        self.anular_core(motivo='Segundo intento de anulación')
        self.assertEqual(self.stock(), Decimal('90'))
        self.assertEqual(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).count(), 1)

    def test_auditor_y_consulta_reciben_403_en_ambos_endpoints(self):
        for usuario in (self.auditor, self.consulta):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                self.assertEqual(self.anular_core().status_code, 403)
                self.assertEqual(self.anular_auditoria().status_code, 403)
        self.assertEqual(self.stock(), Decimal('100'))
        self.assertFalse(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).exists())

    def test_stock_negativo_se_rechaza(self):
        # Después de la entrada salen 95: anularla dejaría el stock en -5
        registrar_movimiento(self.articulo.pk, M.TIPO_AJUSTE_NEG, 95, self.bodeguero, 'Ajuste',
                             justificacion='Conteo físico con faltante')
        self.assertEqual(self.stock(), Decimal('5'))
        self.anular_core()
        self.assertEqual(self.stock(), Decimal('5'))
        self.assertFalse(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).exists())
        self.assertFalse(MovimientoCardex.objects.filter(tipo_movimiento='ANULACION').exists())

    def test_motivo_corto_en_kardex_se_rechaza(self):
        r = self.anular_core(motivo='qww')
        self.assertRedirects(r, reverse('core:auditoria_kardex'))
        self.assertEqual(self.stock(), Decimal('100'))
        self.assertFalse(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).exists())

    def test_anulacion_antigua_hecha_solo_en_auditoria_bloquea_el_kardex(self):
        # Contra-asiento previo a la unificación: existe solo en el Cardex
        MovimientoCardex.objects.create(
            articulo=self.articulo, tipo_movimiento='ANULACION', cantidad=Decimal('-10'),
            saldo_resultante=Decimal('90'), usuario=self.gerente, justificacion='Anulación antigua',
            es_reversa=True, movimiento_reversado=self.asiento)
        self.anular_core()
        self.assertEqual(self.stock(), Decimal('100'))
        self.assertFalse(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).exists())
