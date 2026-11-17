from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class FinanzasAccesoRolTests(TestCase):
    """Pruebas de control de acceso por rol para Finanzas (Etapa 1)."""

    def setUp(self):
        self.grupo_finanzas, _ = Group.objects.get_or_create(name='finanzas')
        self.grupo_bodega, _ = Group.objects.get_or_create(name='bodega')

        self.user_finanzas = User.objects.create_user(
            username='finanzas_user',
            password='Password123!'
        )
        self.user_finanzas.groups.add(self.grupo_finanzas)

        self.user_bodega = User.objects.create_user(
            username='bodega_user',
            password='Password123!'
        )
        self.user_bodega.groups.add(self.grupo_bodega)

        self.superuser = User.objects.create_superuser(
            username='admin_root',
            email='admin@fyag.cl',
            password='Password123!'
        )

    def test_sin_sesion_redirige_a_login(self):
        url = reverse('finanzas:panel')
        respuesta = self.client.get(url)
        self.assertEqual(respuesta.status_code, 302)
        self.assertIn(reverse('usuarios:login'), respuesta.url)

    def test_otro_rol_recibe_403(self):
        self.client.force_login(self.user_bodega)
        respuesta = self.client.get(reverse('finanzas:panel'))
        self.assertEqual(respuesta.status_code, 403)

    def test_rol_finanzas_accede_y_ve_enlace_sidebar(self):
        self.client.force_login(self.user_finanzas)
        respuesta = self.client.get(reverse('finanzas:panel'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Panel de Finanzas')
        self.assertContains(respuesta, f'href="{reverse("finanzas:panel")}"')

    def test_otro_rol_no_ve_enlace_finanzas_en_sidebar(self):
        self.client.force_login(self.user_bodega)
        respuesta = self.client.get(reverse('lista_entidades'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertNotContains(respuesta, f'href="{reverse("finanzas:panel")}"')

    def test_superusuario_accede_al_panel(self):
        self.client.force_login(self.superuser)
        respuesta = self.client.get(reverse('finanzas:panel'))
        self.assertEqual(respuesta.status_code, 200)
