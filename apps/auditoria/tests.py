from django.test import TestCase

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
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