from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from .roles import roles_de, tiene_rol

User = get_user_model()


class TieneRolTests(TestCase):
    def _usuario_en(self, nombre_grupo, username):
        grupo, _ = Group.objects.get_or_create(name=nombre_grupo)
        user = User.objects.create_user(username=username, password='Password123!')
        user.groups.add(grupo)
        return user

    def test_grupo_auditor_sin_importar_mayusculas(self):
        for i, nombre in enumerate(('AUDITOR', 'Auditor', 'auditor')):
            with self.subTest(grupo=nombre):
                user = self._usuario_en(nombre, f'auditor_{i}')
                self.assertTrue(tiene_rol(user, 'auditor'))
                self.assertFalse(tiene_rol(user, 'consulta'))
                self.assertEqual([r['id'] for r in roles_de(user)], ['auditor'])

    def test_consulta_no_es_auditor(self):
        user = self._usuario_en('Consulta', 'consulta_1')
        self.assertTrue(tiene_rol(user, 'consulta'))
        self.assertFalse(tiene_rol(user, 'auditor'))
        self.assertTrue(tiene_rol(user, 'consulta', 'auditor'))

    def test_superusuario_pasa_siempre(self):
        admin = User.objects.create_superuser(username='root', email='root@fyag.cl', password='Password123!')
        self.assertTrue(tiene_rol(admin, 'auditor'))
        self.assertTrue(tiene_rol(admin, 'finanzas', 'bodega'))

    def test_sin_sesion_o_sin_grupo_no_tiene_rol(self):
        user = User.objects.create_user(username='sin_grupo', password='Password123!')
        self.assertFalse(tiene_rol(user, 'consulta', 'auditor'))
        self.assertFalse(tiene_rol(None, 'auditor'))

    def test_auditor_entra_a_su_panel_de_auditoria(self):
        user = self._usuario_en('Auditor', 'auditor_panel')
        self.client.force_login(user)
        respuesta = self.client.get(reverse('usuarios:login_por_rol'))
        self.assertRedirects(respuesta, reverse('auditoria:lista_cardex'))
        html = self.client.get(reverse('auditoria:lista_cardex')).content.decode()
        self.assertIn('Consultas Globales y Auditoría', html)
        self.assertIn(f'href="{reverse("auditoria:logs_acceso")}"', html)
