from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from .models import ContactoEntidad, CuentaBancaria, Proveedor
from .validators import (
    calcular_dv,
    formatear_rut,
    normalizar_rut,
    rut_canonico,
    validar_rut,
)


class ValidadorRutTests(TestCase):
    """Pruebas unitarias del RUT chileno (criterio de aceptación 1 de HU-07)."""

    def test_rut_validos(self):
        validos = [
            '12.345.678-5',
            '76.543.210-3',
            '77.987.654-3',
            '11.111.111-1',
            '1.000.005-K',
            '1.000.005-k',   # acepta la k minúscula
            '76543210-3',    # acepta sin puntos
        ]
        for rut in validos:
            with self.subTest(rut=rut):
                validar_rut(rut)  # no debe lanzar excepción

    def test_rut_con_dv_incorrecto(self):
        # 76.543.210 -> DV correcto es 3 ; 76.123.456 -> DV correcto es 0
        for rut in ['76.543.210-1', '76.123.456-7']:
            with self.subTest(rut=rut):
                with self.assertRaisesMessage(ValidationError, 'dígito verificador'):
                    validar_rut(rut)

    def test_rut_con_formato_invalido(self):
        for rut in ['', 'abc', '1-9', '123']:
            with self.subTest(rut=rut):
                with self.assertRaises(ValidationError):
                    validar_rut(rut)

    def test_calcular_dv(self):
        self.assertEqual(calcular_dv('12345678'), '5')
        self.assertEqual(calcular_dv('76543210'), '3')
        self.assertEqual(calcular_dv('76123456'), '0')  # resto 11 -> "0"
        self.assertEqual(calcular_dv('1000005'), 'K')   # resto 10 -> "K"

    def test_normalizar_rut(self):
        self.assertEqual(normalizar_rut('76.543.210-3'), '76543210-3')
        self.assertEqual(normalizar_rut(' 1.000.005-k '), '1000005-K')
        self.assertEqual(normalizar_rut('765432103'), '76543210-3')
        self.assertEqual(normalizar_rut(None), '')

    def test_formatear_rut(self):
        self.assertEqual(formatear_rut('12345678-5'), '12.345.678-5')
        self.assertEqual(formatear_rut('1000005k'), '1.000.005-K')
        # Si no parece RUT, se devuelve normalizado sin fallar
        self.assertEqual(formatear_rut('123'), '12-3')

    def test_rut_canonico_unifica_formatos(self):
        self.assertEqual(rut_canonico('76543210-3'), '76.543.210-3')
        self.assertEqual(rut_canonico('76.543.210-3'), '76.543.210-3')
        self.assertEqual(rut_canonico('76543210-3'), rut_canonico('76.543.210-3'))


class EntidadesViewsTests(TestCase):
    """Pruebas de vistas, formularios y filtros de HU-07."""

    def _payload_base(self, **overrides):
        """Datos POST base con management forms vacíos de contactos y cuentas."""
        datos = {
            'rut': '76543210-3',
            'razon_social': 'Frío Austral SpA',
            'nombre_fantasia': 'Frío Austral',
            'giro': 'Equipos de refrigeración industrial',
            'tipo': Proveedor.Tipo.PROVEEDOR,
            'telefono': '+56 42 222 3344',
            'email': 'ventas@frioaustral.cl',
            'direccion': 'Av. O’Higgins 123, Chillán',
            'contactos-TOTAL_FORMS': '0',
            'contactos-INITIAL_FORMS': '0',
            'contactos-MIN_NUM_FORMS': '0',
            'contactos-MAX_NUM_FORMS': '1000',
            'cuentas-TOTAL_FORMS': '0',
            'cuentas-INITIAL_FORMS': '0',
            'cuentas-MIN_NUM_FORMS': '0',
            'cuentas-MAX_NUM_FORMS': '1000',
        }
        datos.update(overrides)
        return datos

    def test_crear_ficha_con_dos_contactos_y_una_cuenta_guarda_canonica(self):
        payload = self._payload_base(
            **{
                'contactos-TOTAL_FORMS': '2',
                'contactos-0-nombre': 'Carlos Pérez',
                'contactos-0-cargo': ContactoEntidad.Cargo.COMERCIAL,
                'contactos-0-rut': '12345678-5',
                'contactos-0-email': 'cperez@frioaustral.cl',
                'contactos-0-telefono': '+56 9 8765 4321',
                'contactos-1-nombre': 'Ana Soto',
                'contactos-1-cargo': ContactoEntidad.Cargo.FINANZAS,
                'contactos-1-rut': '',
                'contactos-1-email': 'asoto@frioaustral.cl',
                'contactos-1-telefono': '+56 9 1122 3344',
                'cuentas-TOTAL_FORMS': '1',
                'cuentas-0-banco': 'Banco de Chile',
                'cuentas-0-tipo_cuenta': CuentaBancaria.TipoCuenta.CORRIENTE,
                'cuentas-0-numero_cuenta': '0012345678',
                'cuentas-0-email_pago': 'pagos@frioaustral.cl',
            }
        )
        respuesta = self.client.post(reverse('crear_entidad'), data=payload)
        self.assertRedirects(respuesta, reverse('lista_entidades'))

        self.assertEqual(Proveedor.objects.count(), 1)
        ficha = Proveedor.objects.first()
        # Se guarda en formato canónico con puntos y guion
        self.assertEqual(ficha.rut, '76.543.210-3')
        self.assertEqual(ficha.contactos.count(), 2)
        self.assertEqual(ficha.cuentas.count(), 1)
        # El RUT del representante también se guarda canónico
        contacto_con_rut = ficha.contactos.get(nombre='Carlos Pérez')
        self.assertEqual(contacto_con_rut.rut, '12.345.678-5')

    def test_crear_ficha_con_rut_invalido_no_guarda_y_muestra_error_dv(self):
        payload = self._payload_base(rut='76.543.210-1')
        respuesta = self.client.post(reverse('crear_entidad'), data=payload)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Proveedor.objects.count(), 0)
        self.assertContains(respuesta, 'El dígito verificador del RUT no es válido.')

    def test_rut_duplicado_en_distinto_formato_se_rechaza(self):
        Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='Existente SpA',
            tipo=Proveedor.Tipo.PROVEEDOR,
        )
        # Se intenta registrar el mismo RUT pero sin puntos
        payload = self._payload_base(rut='76543210-3', razon_social='Duplicada SpA')
        respuesta = self.client.post(reverse('crear_entidad'), data=payload)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(Proveedor.objects.count(), 1)
        self.assertContains(respuesta, 'Ya existe una ficha registrada con este RUT.')

    def test_busqueda_por_rut_razon_social_giro_y_filtro_por_tipo(self):
        prov = Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='TermoFrío Chillán Ltda.',
            giro='Mantención de cámaras frigoríficas',
            tipo=Proveedor.Tipo.PROVEEDOR,
        )
        mandante = Proveedor.objects.create(
            rut='77.987.654-3',
            razon_social='Agroexportadora Ñuble S.A.',
            giro='Exportación de berries congelados',
            tipo=Proveedor.Tipo.MANDANTE,
        )
        url = reverse('lista_entidades')

        # 1. Búsqueda por RUT parcial con puntos
        r_rut_puntos = self.client.get(url, {'q': '76.543.210'})
        self.assertContains(r_rut_puntos, prov.razon_social)
        self.assertNotContains(r_rut_puntos, mandante.razon_social)

        # 2. Búsqueda por RUT parcial sin puntos
        r_rut_sin_puntos = self.client.get(url, {'q': '76543210'})
        self.assertContains(r_rut_sin_puntos, prov.razon_social)
        self.assertNotContains(r_rut_sin_puntos, mandante.razon_social)

        # 3. Búsqueda por razón social
        r_razon = self.client.get(url, {'q': 'Agroexportadora'})
        self.assertContains(r_razon, mandante.razon_social)
        self.assertNotContains(r_razon, prov.razon_social)

        # 4. Búsqueda por giro comercial
        r_giro = self.client.get(url, {'q': 'frigoríficas'})
        self.assertContains(r_giro, prov.razon_social)
        self.assertNotContains(r_giro, mandante.razon_social)

        # 5. Filtro por tipo MANDANTE
        r_tipo = self.client.get(url, {'tipo': Proveedor.Tipo.MANDANTE})
        self.assertContains(r_tipo, mandante.razon_social)
        self.assertNotContains(r_tipo, prov.razon_social)

    def test_desactivar_ficha_no_borra_registro(self):
        ficha = Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='Proveedor Activo SpA',
            activo=True,
        )
        respuesta = self.client.post(reverse('cambiar_estado_entidad', args=[ficha.pk]))
        self.assertRedirects(respuesta, reverse('lista_entidades'))

        ficha.refresh_from_db()
        self.assertFalse(ficha.activo)
        self.assertEqual(Proveedor.objects.count(), 1)

    def test_editar_ficha_existente_con_formsets(self):
        ficha = Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='Nombre Antiguo SpA',
            giro='Giro antiguo',
            tipo=Proveedor.Tipo.PROVEEDOR,
        )
        contacto = ContactoEntidad.objects.create(
            entidad=ficha,
            nombre='Contacto Original',
            cargo=ContactoEntidad.Cargo.TECNICO,
            email='original@empresa.cl',
        )
        cuenta = CuentaBancaria.objects.create(
            entidad=ficha,
            banco='Banco Estado',
            tipo_cuenta=CuentaBancaria.TipoCuenta.VISTA,
            numero_cuenta='12345678',
        )

        payload = self._payload_base(
            rut='76.543.210-3',
            razon_social='Nombre Actualizado SpA',
            giro='Giro actualizado',
            tipo=Proveedor.Tipo.MANDANTE,
            **{
                'contactos-TOTAL_FORMS': '1',
                'contactos-INITIAL_FORMS': '1',
                'contactos-0-id': str(contacto.pk),
                'contactos-0-entidad': str(ficha.pk),
                'contactos-0-nombre': 'Contacto Editado',
                'contactos-0-cargo': ContactoEntidad.Cargo.COMERCIAL,
                'contactos-0-rut': '11.111.111-1',
                'contactos-0-email': 'editado@empresa.cl',
                'contactos-0-telefono': '+56 9 9999 8888',
                'cuentas-TOTAL_FORMS': '1',
                'cuentas-INITIAL_FORMS': '1',
                'cuentas-0-id': str(cuenta.pk),
                'cuentas-0-entidad': str(ficha.pk),
                'cuentas-0-banco': 'Banco Santander',
                'cuentas-0-tipo_cuenta': CuentaBancaria.TipoCuenta.CORRIENTE,
                'cuentas-0-numero_cuenta': '87654321',
                'cuentas-0-email_pago': 'tesoreria@empresa.cl',
            }
        )
        respuesta = self.client.post(reverse('editar_entidad', args=[ficha.pk]), data=payload)
        self.assertRedirects(respuesta, reverse('lista_entidades'))

        ficha.refresh_from_db()
        contacto.refresh_from_db()
        cuenta.refresh_from_db()
        self.assertEqual(ficha.razon_social, 'Nombre Actualizado SpA')
        self.assertEqual(ficha.tipo, Proveedor.Tipo.MANDANTE)
        self.assertEqual(contacto.nombre, 'Contacto Editado')
        self.assertEqual(contacto.cargo, ContactoEntidad.Cargo.COMERCIAL)
        self.assertEqual(cuenta.banco, 'Banco Santander')
        self.assertEqual(cuenta.numero_cuenta, '87654321')
