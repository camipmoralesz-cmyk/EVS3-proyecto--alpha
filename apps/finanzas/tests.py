from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.entidades.models import ContactoEntidad, CuentaBancaria, Proveedor
from apps.inventario.models import DocumentoEntrada
from apps.obras.models import Obra

User = get_user_model()


class BaseFinanzasTestCase(TestCase):
    """Configuración base de usuarios y roles para pruebas de Finanzas."""

    @classmethod
    def setUpTestData(cls):
        cls.grupo_finanzas, _ = Group.objects.get_or_create(name='finanzas')
        cls.grupo_bodega, _ = Group.objects.get_or_create(name='bodega')

        cls.user_finanzas = User.objects.create_user(
            username='finanzas_user',
            password='Password123!'
        )
        cls.user_finanzas.groups.add(cls.grupo_finanzas)

        cls.user_bodega = User.objects.create_user(
            username='bodega_user',
            password='Password123!'
        )
        cls.user_bodega.groups.add(cls.grupo_bodega)

        cls.superuser = User.objects.create_superuser(
            username='admin_root',
            email='admin@fyag.cl',
            password='Password123!'
        )


class FinanzasAccesoRolTests(BaseFinanzasTestCase):
    """Pruebas de control de acceso por rol para Finanzas (Etapa 1)."""

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


class FinanzasEntidadesTests(BaseFinanzasTestCase):
    """Pruebas de CRUD y borrado condicional de Proveedores y Mandantes en Finanzas (Etapa 2)."""

    def setUp(self):
        self.client.force_login(self.user_finanzas)

    def _payload_entidad(self, **overrides):
        datos = {
            'rut': '76.543.210-3',
            'razon_social': 'Frío Industrial SpA',
            'nombre_fantasia': 'FríoInd',
            'giro': 'Refrigeración industrial',
            'tipo': Proveedor.Tipo.PROVEEDOR,
            'telefono': '+56 42 222 3344',
            'email': 'contacto@frioind.cl',
            'direccion': 'Av. O’Higgins 500, Chillán',
            'contactos-TOTAL_FORMS': '1',
            'contactos-INITIAL_FORMS': '0',
            'contactos-MIN_NUM_FORMS': '0',
            'contactos-MAX_NUM_FORMS': '1000',
            'contactos-0-nombre': 'Marta Rivas',
            'contactos-0-cargo': ContactoEntidad.Cargo.FINANZAS,
            'contactos-0-rut': '12.345.678-5',
            'contactos-0-email': 'mrivas@frioind.cl',
            'contactos-0-telefono': '+56 9 8765 4321',
            'cuentas-TOTAL_FORMS': '1',
            'cuentas-INITIAL_FORMS': '0',
            'cuentas-MIN_NUM_FORMS': '0',
            'cuentas-MAX_NUM_FORMS': '1000',
            'cuentas-0-banco': 'Banco de Chile',
            'cuentas-0-tipo_cuenta': CuentaBancaria.TipoCuenta.CORRIENTE,
            'cuentas-0-numero_cuenta': '0098765432',
            'cuentas-0-email_pago': 'pagos@frioind.cl',
        }
        datos.update(overrides)
        return datos

    def test_crear_editar_y_listar_proveedor_con_contactos_y_cuentas(self):
        r_crear = self.client.post(reverse('finanzas:entidad_crear'), data=self._payload_entidad())
        self.assertRedirects(r_crear, reverse('finanzas:entidades_lista'))

        entidad = Proveedor.objects.get(rut='76.543.210-3')
        self.assertEqual(entidad.contactos.count(), 1)
        self.assertEqual(entidad.cuentas.count(), 1)

        contacto = entidad.contactos.first()
        cuenta = entidad.cuentas.first()
        payload_edit = self._payload_entidad(
            razon_social='Frío Industrial Editado SpA',
            tipo=Proveedor.Tipo.MANDANTE,
            **{
                'contactos-INITIAL_FORMS': '1',
                'contactos-0-id': str(contacto.pk),
                'contactos-0-entidad': str(entidad.pk),
                'cuentas-INITIAL_FORMS': '1',
                'cuentas-0-id': str(cuenta.pk),
                'cuentas-0-entidad': str(entidad.pk),
            }
        )
        r_editar = self.client.post(
            reverse('finanzas:entidad_editar', args=[entidad.pk]),
            data=payload_edit,
        )
        self.assertRedirects(r_editar, reverse('finanzas:entidades_lista'))
        entidad.refresh_from_db()
        self.assertEqual(entidad.razon_social, 'Frío Industrial Editado SpA')
        self.assertEqual(entidad.tipo, Proveedor.Tipo.MANDANTE)

    def test_activar_y_desactivar_entidad(self):
        entidad = Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='Proveedor Activo SpA',
            activo=True,
        )
        r = self.client.post(reverse('finanzas:entidad_cambiar_estado', args=[entidad.pk]))
        self.assertRedirects(r, reverse('finanzas:entidades_lista'))
        entidad.refresh_from_db()
        self.assertFalse(entidad.activo)

    def test_borrar_entidad_sin_datos_asociados_con_confirmacion(self):
        entidad = Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='Proveedor Sin Datos SpA',
            tipo=Proveedor.Tipo.PROVEEDOR,
        )
        r_lista = self.client.get(reverse('finanzas:entidades_lista'))
        url_eliminar = reverse('finanzas:entidad_eliminar', args=[entidad.pk])
        self.assertContains(r_lista, f'href="{url_eliminar}"')

        r_confirm = self.client.get(url_eliminar)
        self.assertEqual(r_confirm.status_code, 200)
        self.assertContains(r_confirm, 'Confirmar eliminación definitiva')

        r_post = self.client.post(url_eliminar)
        self.assertRedirects(r_post, reverse('finanzas:entidades_lista'))
        self.assertFalse(Proveedor.objects.filter(pk=entidad.pk).exists())

    def test_no_permite_borrar_proveedor_con_documento_asociado(self):
        proveedor = Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='Proveedor Con Factura SpA',
            tipo=Proveedor.Tipo.PROVEEDOR,
        )
        DocumentoEntrada.objects.create(
            proveedor=proveedor,
            tipo_documento=DocumentoEntrada.TIPO_FACTURA,
            numero_documento='F-1001',
            fecha_emision=date(2026, 5, 10),
            monto_neto=150000,
        )
        url_eliminar = reverse('finanzas:entidad_eliminar', args=[proveedor.pk])

        r_lista = self.client.get(reverse('finanzas:entidades_lista'))
        self.assertNotContains(r_lista, f'href="{url_eliminar}"')

        r_post = self.client.post(url_eliminar)
        self.assertRedirects(r_post, reverse('finanzas:entidades_lista'))
        self.assertTrue(Proveedor.objects.filter(pk=proveedor.pk).exists())

    def test_no_permite_borrar_mandante_con_obra_asociada(self):
        mandante = Proveedor.objects.create(
            rut='77.987.654-3',
            razon_social='Mandante Con Obra S.A.',
            tipo=Proveedor.Tipo.MANDANTE,
            activo=True,
        )
        Obra.objects.create(
            nombre='Planta Frigorífica Sur',
            mandante=mandante,
            presupuesto_total=50000000,
        )
        url_eliminar = reverse('finanzas:entidad_eliminar', args=[mandante.pk])

        r_lista = self.client.get(reverse('finanzas:entidades_lista'))
        self.assertNotContains(r_lista, f'href="{url_eliminar}"')

        r_post = self.client.post(url_eliminar)
        self.assertRedirects(r_post, reverse('finanzas:entidades_lista'))
        self.assertTrue(Proveedor.objects.filter(pk=mandante.pk).exists())


class FinanzasPresupuestosTests(BaseFinanzasTestCase):
    """Pruebas de listado y edición de presupuestos de obras en Finanzas (Etapa 3)."""

    def setUp(self):
        self.client.force_login(self.user_finanzas)
        self.mandante = Proveedor.objects.create(
            rut='77.987.654-3',
            razon_social='Agroexportadora Ñuble S.A.',
            tipo=Proveedor.Tipo.MANDANTE,
            activo=True,
        )
        self.obra = Obra.objects.create(
            nombre='Cámara de Frío San Carlos',
            mandante=self.mandante,
            presupuesto_total=Decimal('15000000.00'),
            estado=Obra.Estado.ACTIVA,
        )

    def test_listar_obras_y_presupuestos(self):
        r = self.client.get(reverse('finanzas:presupuestos_lista'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Cámara de Frío San Carlos')
        self.assertContains(r, 'Agroexportadora Ñuble S.A.')

    def test_editar_presupuesto_total_valido(self):
        url = reverse('finanzas:presupuesto_editar', args=[self.obra.pk])
        r = self.client.post(url, data={'presupuesto_total': '28500000.50'})
        self.assertRedirects(r, reverse('finanzas:presupuestos_lista'))
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.presupuesto_total, Decimal('28500000.50'))

    def test_editar_presupuesto_negativo_falla(self):
        url = reverse('finanzas:presupuesto_editar', args=[self.obra.pk])
        r = self.client.post(url, data={'presupuesto_total': '-5000'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'El presupuesto no puede ser negativo.')
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.presupuesto_total, Decimal('15000000.00'))

    def test_borrar_presupuesto_en_obra_activa_lo_deja_en_cero(self):
        url = reverse('finanzas:presupuesto_eliminar', args=[self.obra.pk])
        r_get = self.client.get(url)
        self.assertEqual(r_get.status_code, 200)
        self.assertContains(r_get, 'Confirmar borrado de presupuesto')

        r_post = self.client.post(url)
        self.assertRedirects(r_post, reverse('finanzas:presupuestos_lista'))
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.presupuesto_total, Decimal('0.00'))
        self.assertTrue(Obra.objects.filter(pk=self.obra.pk).exists())

    def test_no_permite_borrar_presupuesto_en_obra_cerrada(self):
        self.obra.estado = Obra.Estado.CERRADA
        self.obra.save(update_fields=['estado'])
        url = reverse('finanzas:presupuesto_eliminar', args=[self.obra.pk])

        r_lista = self.client.get(reverse('finanzas:presupuestos_lista'))
        self.assertNotContains(r_lista, f'href="{url}"')

        r_post = self.client.post(url)
        self.assertRedirects(r_post, reverse('finanzas:presupuestos_lista'))
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.presupuesto_total, Decimal('15000000.00'))
