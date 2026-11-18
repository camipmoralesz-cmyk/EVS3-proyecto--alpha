from datetime import date
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from apps.catalogo.models import Articulo, Categoria
from apps.entidades.models import ContactoEntidad, CuentaBancaria, Proveedor
from apps.finanzas.models import ObservacionFactura, PagoProveedor, SaldoInicialEmpresa
from apps.inventario.models import DetalleDocumento, DocumentoEntrada
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


class FinanzasFacturasTests(BaseFinanzasTestCase):
    """Pruebas de consulta y valorización de facturas en Finanzas (Etapa 4)."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        proveedor = Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='Proveedor de Prueba SpA',
        )
        categoria = Categoria.objects.create(nombre='Materiales de prueba')
        articulo = Articulo.objects.create(
            codigo_interno='FIN-001',
            nombre='Perfil de acero',
            categoria=categoria,
            ubicacion_bodega='Bodega central',
            pmp_costo_actual=1250,
        )
        cls.documento = DocumentoEntrada.objects.create(
            proveedor=proveedor,
            numero_documento='F-1001',
            fecha_emision=date(2026, 11, 1),
            registrado_por=cls.user_finanzas,
            monto_neto=2500,
        )
        DetalleDocumento.objects.create(
            documento=cls.documento,
            articulo=articulo,
            cantidad=Decimal('2.00'),
            precio_unitario_base=1300,
            precio_unitario_final=1250,
            subtotal_linea=2500,
        )

    def test_finanzas_lista_documentos_y_puede_buscar(self):
        self.client.force_login(self.user_finanzas)

        respuesta = self.client.get(reverse('finanzas:facturas_lista'), {'q': 'F-1001'})

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'F-1001')
        self.assertContains(respuesta, '$2500 CLP')
        self.assertContains(respuesta, reverse('finanzas:factura_detalle', args=[self.documento.pk]))

    def test_finanzas_ve_desglose_subtotal_neto_y_pmp_sin_acciones_de_edicion(self):
        self.client.force_login(self.user_finanzas)
        url = reverse('finanzas:factura_detalle', args=[self.documento.pk])

        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Subtotal línea')
        self.assertContains(respuesta, '$2500 CLP')
        self.assertContains(respuesta, '$1250 CLP')
        self.assertNotContains(respuesta, 'Editar')
        self.assertNotContains(respuesta, 'Borrar')

    def test_finanzas_reporta_factura_a_gerencia_sin_modificarla(self):
        self.client.force_login(self.user_finanzas)
        url = reverse('finanzas:factura_detalle', args=[self.documento.pk])

        respuesta = self.client.post(url, {
            'texto': 'Revisar el monto neto de este documento.',
            'numero_documento': 'F-9999',
            'monto_neto': '1',
            'tipo_documento': DocumentoEntrada.TIPO_BOLETA,
        })

        self.assertRedirects(respuesta, url)
        observacion = ObservacionFactura.objects.get(documento=self.documento)
        self.assertEqual(observacion.usuario, self.user_finanzas)
        self.assertEqual(observacion.texto, 'Revisar el monto neto de este documento.')
        self.assertEqual(observacion.estado, 'PENDIENTE')
        self.documento.refresh_from_db()
        self.assertEqual(self.documento.numero_documento, 'F-1001')
        self.assertEqual(self.documento.monto_neto, 2500)
        self.assertEqual(self.documento.tipo_documento, DocumentoEntrada.TIPO_FACTURA)

    def test_no_guarda_un_reporte_sin_texto(self):
        self.client.force_login(self.user_finanzas)
        url = reverse('finanzas:factura_detalle', args=[self.documento.pk])

        respuesta = self.client.post(url, {'texto': '   '})

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(ObservacionFactura.objects.filter(documento=self.documento).count(), 0)
        self.assertContains(respuesta, 'Reportar a Gerencia')

    def test_otro_rol_no_puede_consultar_facturas_de_finanzas(self):
        self.client.force_login(self.user_bodega)

        respuesta = self.client.get(reverse('finanzas:facturas_lista'))
        detalle = self.client.get(
            reverse('finanzas:factura_detalle', args=[self.documento.pk]),
        )
        reporte = self.client.post(
            reverse('finanzas:factura_detalle', args=[self.documento.pk]),
            {'texto': 'Reporte sin autorización.'},
        )

        self.assertEqual(respuesta.status_code, 403)
        self.assertEqual(detalle.status_code, 403)
        self.assertEqual(reporte.status_code, 403)
        self.assertFalse(ObservacionFactura.objects.filter(documento=self.documento).exists())


class FinanzasPagosTests(BaseFinanzasTestCase):
    def setUp(self):
        self.client.force_login(self.user_finanzas)
        proveedor = Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='Proveedor para pagos SpA',
        )
        self.documento = DocumentoEntrada.objects.create(
            proveedor=proveedor,
            numero_documento='PAGO-1001',
            fecha_emision=date(2026, 11, 17),
            monto_neto=30000,
        )

    def _payload(self, **overrides):
        datos = {
            'documento': self.documento.pk,
            'fecha': '2026-11-17',
            'monto': '12000.00',
            'medio_pago': PagoProveedor.MedioPago.TRANSFERENCIA,
            'estado': PagoProveedor.Estado.PAGADO,
        }
        datos.update(overrides)
        return datos

    def test_crear_y_listar_pago(self):
        respuesta = self.client.post(
            reverse('finanzas:pago_crear'),
            self._payload(),
        )

        self.assertRedirects(respuesta, reverse('finanzas:pagos_lista'))
        pago = PagoProveedor.objects.get(documento=self.documento)
        self.assertEqual(pago.usuario, self.user_finanzas)
        self.assertEqual(pago.monto, Decimal('12000.00'))

        listado = self.client.get(reverse('finanzas:pagos_lista'))
        self.assertEqual(listado.status_code, 200)
        self.assertContains(listado, 'PAGO-1001')
        self.assertContains(listado, '$12000')

    def test_editar_pago_y_conservar_usuario_que_lo_registro(self):
        pago = PagoProveedor.objects.create(
            documento=self.documento,
            fecha=date(2026, 11, 16),
            monto=Decimal('10000.00'),
            medio_pago=PagoProveedor.MedioPago.EFECTIVO,
            estado=PagoProveedor.Estado.PENDIENTE,
            usuario=self.user_bodega,
        )

        respuesta = self.client.post(
            reverse('finanzas:pago_editar', args=[pago.pk]),
            self._payload(monto='15000.00'),
        )

        self.assertRedirects(respuesta, reverse('finanzas:pagos_lista'))
        pago.refresh_from_db()
        self.assertEqual(pago.monto, Decimal('15000.00'))
        self.assertEqual(pago.usuario, self.user_bodega)

    def test_rechazar_pago_mayor_al_neto_del_documento(self):
        respuesta = self.client.post(
            reverse('finanzas:pago_crear'),
            self._payload(monto='30000.01'),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'El monto supera el saldo disponible')
        self.assertFalse(PagoProveedor.objects.filter(documento=self.documento).exists())

    def test_no_permitir_que_pagos_activos_acumulados_superen_el_neto(self):
        PagoProveedor.objects.create(
            documento=self.documento,
            fecha=date(2026, 11, 16),
            monto=Decimal('25000.00'),
            medio_pago=PagoProveedor.MedioPago.TRANSFERENCIA,
            estado=PagoProveedor.Estado.PAGADO,
            usuario=self.user_finanzas,
        )

        respuesta = self.client.post(
            reverse('finanzas:pago_crear'),
            self._payload(monto='5001.00'),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'El monto supera el saldo disponible')
        self.assertEqual(PagoProveedor.objects.filter(documento=self.documento).count(), 1)

    def test_usuario_de_bodega_no_puede_ver_ni_crear_pagos(self):
        self.client.force_login(self.user_bodega)

        listado = self.client.get(reverse('finanzas:pagos_lista'))
        crear = self.client.get(reverse('finanzas:pago_crear'))
        crear_post = self.client.post(
            reverse('finanzas:pago_crear'),
            self._payload(),
        )

        self.assertEqual(listado.status_code, 403)
        self.assertEqual(crear.status_code, 403)
        self.assertEqual(crear_post.status_code, 403)
        self.assertFalse(PagoProveedor.objects.filter(documento=self.documento).exists())


class FinanzasSaldoPanelTests(BaseFinanzasTestCase):
    def setUp(self):
        self.client.force_login(self.user_finanzas)
        self.proveedor = Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='Proveedor para saldo SpA',
        )

    def _crear_documento(self, numero, monto):
        return DocumentoEntrada.objects.create(
            proveedor=self.proveedor,
            tipo_documento=DocumentoEntrada.TIPO_FACTURA,
            numero_documento=numero,
            fecha_emision=date(2026, 11, 17),
            monto_neto=monto,
            estado=DocumentoEntrada.ESTADO_CONFIRMADO,
        )

    def test_solo_pago_pagado_disminuye_el_saldo_inicial(self):
        self.assertEqual(SaldoInicialEmpresa.objects.get(pk=1).monto, Decimal('30000.00'))
        documento = self._crear_documento('SALDO-1001', 10000)

        url = reverse('finanzas:panel')
        respuesta = self.client.get(url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Saldo disponible para compras')
        self.assertEqual(respuesta.context['saldo_disponible'], Decimal('30000.00'))

        pago = PagoProveedor.objects.create(
            documento=documento,
            fecha=date(2026, 11, 17),
            monto=Decimal('10000.00'),
            medio_pago=PagoProveedor.MedioPago.TRANSFERENCIA,
            estado=PagoProveedor.Estado.PENDIENTE,
            usuario=self.user_finanzas,
        )
        pendiente = self.client.get(url)
        self.assertEqual(pendiente.context['saldo_disponible'], Decimal('30000.00'))

        pago.estado = PagoProveedor.Estado.PAGADO
        pago.save(update_fields=['estado'])
        pagado = self.client.get(url)
        self.assertEqual(pagado.context['pagos_efectuados'], Decimal('10000.00'))
        self.assertEqual(pagado.context['saldo_disponible'], Decimal('20000.00'))

    def test_pago_anulado_no_se_descuenta_del_saldo(self):
        documento = self._crear_documento('SALDO-ANULADO', 10000)
        PagoProveedor.objects.create(
            documento=documento,
            fecha=date(2026, 11, 17),
            monto=Decimal('10000.00'),
            medio_pago=PagoProveedor.MedioPago.TRANSFERENCIA,
            estado=PagoProveedor.Estado.ANULADO,
            usuario=self.user_finanzas,
        )

        respuesta = self.client.get(reverse('finanzas:panel'))

        self.assertEqual(respuesta.context['pagos_efectuados'], Decimal('0.00'))
        self.assertEqual(respuesta.context['saldo_disponible'], Decimal('30000.00'))

    def test_panel_muestra_contadores_reales_de_facturas_pagos_y_presupuestos(self):
        factura = self._crear_documento('PANEL-FACT-1', 10000)
        DocumentoEntrada.objects.create(
            proveedor=self.proveedor,
            tipo_documento=DocumentoEntrada.TIPO_BOLETA,
            numero_documento='PANEL-BOL-1',
            fecha_emision=date(2026, 11, 17),
            monto_neto=5000,
        )
        PagoProveedor.objects.create(
            documento=factura,
            fecha=date(2026, 11, 17),
            monto=Decimal('5000.00'),
            medio_pago=PagoProveedor.MedioPago.TRANSFERENCIA,
            estado=PagoProveedor.Estado.PENDIENTE,
            usuario=self.user_finanzas,
        )
        mandante = Proveedor.objects.create(
            rut='77.987.654-3',
            razon_social='Mandante para panel S.A.',
            tipo=Proveedor.Tipo.MANDANTE,
        )
        Obra.objects.create(
            nombre='Obra para panel',
            mandante=mandante,
            presupuesto_total=Decimal('1250000.00'),
        )

        respuesta = self.client.get(reverse('finanzas:panel'))

        self.assertEqual(respuesta.context['facturas_count'], 1)
        self.assertEqual(respuesta.context['pagos_pendientes_count'], 1)
        self.assertEqual(respuesta.context['presupuestos_total'], Decimal('1250000.00'))
        self.assertContains(respuesta, 'Facturas registradas')
        self.assertContains(respuesta, 'Pagos pendientes')
        self.assertContains(respuesta, 'Presupuestos totales')


class FinanzasCuentaMaskingTests(BaseFinanzasTestCase):
    def setUp(self):
        self.entidad = Proveedor.objects.create(
            rut='76.543.210-3',
            razon_social='Proveedor con cuenta de prueba SpA',
        )
        self.cuenta = CuentaBancaria.objects.create(
            entidad=self.entidad,
            banco='Banco de Prueba',
            tipo_cuenta=CuentaBancaria.TipoCuenta.CORRIENTE,
            numero_cuenta='0012345678',
        )
        self.url = reverse('editar_entidad', args=[self.entidad.pk])

    def test_bodega_solo_ve_la_cuenta_enmascarada_y_no_puede_sobrescribirla(self):
        self.client.force_login(self.user_bodega)
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, '****5678')
        self.assertNotContains(respuesta, '0012345678')

        respuesta_post = self.client.post(self.url, {
            'rut': self.entidad.rut,
            'razon_social': 'Proveedor actualizado SpA',
            'nombre_fantasia': '',
            'giro': '',
            'tipo': Proveedor.Tipo.PROVEEDOR,
            'telefono': '',
            'email': '',
            'direccion': '',
            'contactos-TOTAL_FORMS': '0',
            'contactos-INITIAL_FORMS': '0',
            'contactos-MIN_NUM_FORMS': '0',
            'contactos-MAX_NUM_FORMS': '1000',
            'cuentas-TOTAL_FORMS': '1',
            'cuentas-INITIAL_FORMS': '1',
            'cuentas-MIN_NUM_FORMS': '0',
            'cuentas-MAX_NUM_FORMS': '1000',
            'cuentas-0-id': str(self.cuenta.pk),
            'cuentas-0-entidad': str(self.entidad.pk),
            'cuentas-0-banco': 'Banco de Prueba',
            'cuentas-0-tipo_cuenta': CuentaBancaria.TipoCuenta.CORRIENTE,
            'cuentas-0-numero_cuenta': '99999999',
            'cuentas-0-email_pago': '',
        })

        self.assertRedirects(respuesta_post, reverse('lista_entidades'))
        self.cuenta.refresh_from_db()
        self.assertEqual(self.cuenta.numero_cuenta, '0012345678')

    def test_finanzas_y_superusuario_ven_el_numero_completo(self):
        for usuario in (self.user_finanzas, self.superuser):
            with self.subTest(usuario=usuario.username):
                self.client.force_login(usuario)
                respuesta = self.client.get(self.url)
                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(respuesta, '0012345678')
