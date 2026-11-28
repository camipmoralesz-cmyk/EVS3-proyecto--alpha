from decimal import Decimal

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.catalogo.models import Articulo, Categoria
from apps.inventario.models import MovimientoInventario as M
from apps.inventario.services import registrar_movimiento
from .models import BitacoraAuditoria, LogAcceso

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
    """Kardex y Cardex de Auditoría son la misma tabla (MovimientoInventario). Se anula solo
    desde el Kardex de Gerencia; el Cardex es de solo lectura y muestra el contra-asiento."""

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
        self.client.force_login(self.gerente)

    def stock(self):
        self.articulo.refresh_from_db()
        return self.articulo.stock_actual

    def anular_core(self, motivo='Error de digitación'):
        return self.client.post(reverse('core:anular_movimiento', args=[self.entrada.pk]), {'motivo': motivo})

    def anular_auditoria(self, motivo='Error de digitación en la entrada'):
        return self.client.post(reverse('auditoria:anular_movimiento'),
                                {'movimiento_id': self.entrada.pk, 'motivo_anulacion': motivo})

    def html_cardex(self):
        return self.client.get(reverse('auditoria:lista_cardex')).content.decode()

    def test_cardex_y_kardex_muestran_el_mismo_movimiento(self):
        self.assertIn(f'#{self.entrada.pk}', self.html_cardex())
        self.assertIn(f'#{self.entrada.pk}', self.client.get(reverse('core:auditoria_kardex')).content.decode())
        # No existe una tabla aparte: solo hay un registro del movimiento
        self.assertEqual(M.objects.filter(articulo=self.articulo).count(), 1)

    def test_anular_en_core_y_luego_en_auditoria_se_rechaza(self):
        self.assertEqual(self.stock(), Decimal('100'))
        self.anular_core()
        self.assertEqual(self.stock(), Decimal('90'))

        r = self.anular_auditoria()
        self.assertRedirects(r, reverse('core:auditoria_kardex'))
        self.assertEqual(self.stock(), Decimal('90'))
        contra = M.objects.get(tipo_movimiento=M.TIPO_ANULACION)
        self.assertEqual(contra.movimiento_anulado, self.entrada)
        html = self.html_cardex()
        self.assertIn(f'Anulado por #{contra.pk}', html)
        self.assertIn(f'Reversa de #{self.entrada.pk}', html)

    def test_auditoria_no_anula_ni_siquiera_gerencia(self):
        r = self.anular_auditoria()
        self.assertRedirects(r, reverse('core:auditoria_kardex'))
        self.assertEqual(self.stock(), Decimal('100'))
        self.assertFalse(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).exists())

    def test_pantalla_unica_gerencia_anula_y_el_resto_solo_lee(self):
        url_anular = reverse('core:anular_movimiento', args=[self.entrada.pk])
        # Las dos URL muestran la misma pantalla
        for url in (reverse('auditoria:lista_cardex'), reverse('core:auditoria_kardex')):
            with self.subTest(url=url):
                html = self.client.get(url).content.decode()
                self.assertIn('Kardex Inmutable de Bodega', html)
                self.assertIn(url_anular, html)
        for usuario in (self.auditor, self.consulta, self.bodeguero):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                html = self.html_cardex()
                self.assertNotIn(url_anular, html)
                self.assertNotIn(reverse('auditoria:anular_movimiento'), html)
                self.assertIn('Vigente', html)
                self.assertIn('Modo solo lectura', html)

    def test_segunda_anulacion_se_rechaza_y_el_kardex_ya_no_ofrece_el_boton(self):
        self.anular_core()
        contra = M.objects.get(tipo_movimiento=M.TIPO_ANULACION)
        html = self.client.get(reverse('core:auditoria_kardex')).content.decode()
        self.assertIn(f'Anulado por #{contra.pk}', html)
        self.assertNotIn(reverse('core:anular_movimiento', args=[self.entrada.pk]), html)

        self.anular_core(motivo='Segundo intento de anulación')
        self.assertEqual(self.stock(), Decimal('90'))
        self.assertEqual(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).count(), 1)

    def test_la_base_impide_dos_contra_asientos_del_mismo_movimiento(self):
        from django.db import IntegrityError, transaction
        self.anular_core()
        with self.assertRaises(IntegrityError), transaction.atomic():
            M.objects.create(articulo=self.articulo, tipo_movimiento=M.TIPO_ANULACION, cantidad=10,
                             stock_anterior=90, stock_posterior=80, usuario=self.gerente,
                             referencia='Duplicado', movimiento_anulado=self.entrada)

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

    def test_motivo_corto_en_kardex_se_rechaza(self):
        r = self.anular_core(motivo='qww')
        self.assertRedirects(r, reverse('core:auditoria_kardex'))
        self.assertEqual(self.stock(), Decimal('100'))
        self.assertFalse(M.objects.filter(tipo_movimiento=M.TIPO_ANULACION).exists())

    def test_filtros_del_cardex_sobre_el_kardex(self):
        r = self.client.get(reverse('auditoria:lista_cardex'), {'tipo_movimiento': M.TIPO_ENTRADA,
                                                                'usuario': 'bodega_anula'})
        self.assertEqual(list(r.context['movimientos']), [self.entrada])
        r = self.client.get(reverse('auditoria:lista_cardex'), {'tipo_movimiento': M.TIPO_MERMA})
        self.assertEqual(list(r.context['movimientos']), [])

    def test_exportaciones_leen_el_kardex(self):
        for nombre in ('auditoria:exportar_cardex_excel', 'auditoria:exportar_cardex_pdf'):
            with self.subTest(exportacion=nombre):
                r = self.client.get(reverse(nombre))
                self.assertEqual(r.status_code, 200)
        self.assertEqual(BitacoraAuditoria.objects.filter(accion='EXPORTAR',
                                                          modelo_afectado='MovimientoInventario').count(), 2)

    def test_filtros_manipulados_no_rompen_el_kardex(self):
        # Valores inválidos en la URL se ignoran: la pantalla y los exportes responden 200.
        for params in ({'articulo': 'abc'}, {'fecha_inicio': 'abc'}, {'fecha_fin': '2026-13-45'}):
            for nombre in ('auditoria:lista_cardex', 'auditoria:exportar_cardex_excel',
                           'auditoria:exportar_cardex_pdf'):
                with self.subTest(params=params, vista=nombre):
                    self.assertEqual(self.client.get(reverse(nombre), params).status_code, 200)
        r = self.client.get(reverse('auditoria:lista_cardex'), {'fecha_inicio': 'abc'})
        self.assertIn(self.entrada, list(r.context['movimientos']))
