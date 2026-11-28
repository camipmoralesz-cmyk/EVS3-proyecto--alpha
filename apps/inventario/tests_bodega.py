"""Pruebas del rol Administrador de Bodega / Logística (HU-01, 02, 04, 05, 06)."""
import base64
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.catalogo.models import Articulo, Categoria
from apps.entidades.models import Proveedor
from apps.obras.models import Obra
from .models import (
    CardexInalterableError, DocumentoEntrada, MovimientoInventario as M, OrdenRestock, SesionInventario,
    SolicitudDespacho, DetalleSolicitud,
)
from .services import (
    SECTOR_CHECKLIST_GENERAL, abrir_sesion_inventario, cerrar_sesion_inventario, crear_orden_restock, despachar,
    guardar_conteo, recibir_orden_restock, registrar_checklist_general, registrar_documento_entrada,
    registrar_movimiento, registrar_salida_tipificada, resolver_orden_restock,
)

# PNG mínimo válido (1x1) para simular la firma del técnico
PNG = 'data:image/png;base64,' + base64.b64encode(
    b'\x89PNG\r\n\x1a\n' + b'\x00' * 40).decode()


class BaseBodega(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.grupos = {n: Group.objects.create(name=n) for n in
                      ('bodega', 'gerencia', 'finanzas', 'supervisor', 'tecnico')}

        def crear(nombre, grupo):
            u = User.objects.create_user(nombre, password='x')
            u.groups.add(cls.grupos[grupo])
            return u
        cls.bodeguero = crear('bodeguero', 'bodega')
        cls.gerente = crear('gerente', 'gerencia')
        cls.finanzas = crear('finanzas', 'finanzas')
        cls.supervisor = crear('supervisor', 'supervisor')
        cls.tecnico = crear('tecnico', 'tecnico')
        cls.sin_rol = User.objects.create_user('sinrol', password='x')

        cat = Categoria.objects.create(nombre='Refrigeración')
        cls.art = Articulo.objects.create(
            codigo_interno='A-1', nombre='Cañería de cobre', categoria=cat, ubicacion_bodega='Pasillo A',
            stock_actual=Decimal('10'), pmp_costo_actual=1000, ultimo_costo_compra=1000)
        cls.art2 = Articulo.objects.create(
            codigo_interno='A-2', nombre='Gas R410', categoria=cat, ubicacion_bodega='Pasillo A',
            stock_actual=Decimal('5'), pmp_costo_actual=2000, ultimo_costo_compra=2000)
        cls.proveedor = Proveedor.objects.create(rut='76.999.888-1', razon_social='Proveedor SA')
        cls.mandante = Proveedor.objects.create(rut='76.543.210-3', razon_social='Cliente SpA',
                                                tipo=Proveedor.Tipo.MANDANTE)
        cls.obra = Obra.objects.create(nombre='Planta Chillán', mandante=cls.mandante)

    def solicitud(self, cantidad=3, articulo=None, obra=None):
        s = SolicitudDespacho.objects.create(obra=obra or self.obra, solicitante=self.supervisor)
        DetalleSolicitud.objects.create(solicitud=s, articulo=articulo or self.art, cantidad=cantidad)
        return s

    def stock(self, art=None):
        a = art or self.art
        a.refresh_from_db()
        return a.stock_actual


class PermisosTests(BaseBodega):
    def test_sin_login_redirige_al_login(self):
        r = self.client.get(reverse('registro_documento'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('login', r.url)

    def test_roles_sin_permiso_de_escritura_reciben_403(self):
        urls = ['registro_documento', 'lista_solicitudes', 'salida_tipificada', 'lista_sesiones_inventario']
        for usuario in (self.gerente, self.finanzas, self.supervisor, self.tecnico, self.sin_rol):
            self.client.force_login(usuario)
            for nombre in urls:
                self.assertEqual(self.client.get(reverse(nombre)).status_code, 403, f'{usuario} {nombre}')

    def test_bodega_accede_a_sus_pantallas(self):
        self.client.force_login(self.bodeguero)
        for nombre in ('registro_documento', 'lista_solicitudes', 'salida_tipificada',
                       'lista_sesiones_inventario', 'inventario_stock', 'historial_movimientos',
                       'lista_documentos', 'lista_articulos', 'lista_entidades', 'core:dashboard'):
            self.assertEqual(self.client.get(reverse(nombre)).status_code, 200, nombre)

    def test_tecnico_no_puede_ver_cardex_ni_stock(self):
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(reverse('historial_movimientos')).status_code, 403)
        self.assertEqual(self.client.get(reverse('inventario_stock')).status_code, 403)

    def test_gerencia_y_supervisor_solo_leen(self):
        self.client.force_login(self.gerente)
        self.assertEqual(self.client.get(reverse('historial_movimientos')).status_code, 200)
        self.client.force_login(self.supervisor)
        self.assertEqual(self.client.get(reverse('inventario_stock')).status_code, 200)
        self.assertEqual(self.client.get(reverse('historial_movimientos')).status_code, 403)

    def test_bodega_no_crea_ni_edita_proveedores(self):
        self.client.force_login(self.bodeguero)
        self.assertEqual(self.client.get(reverse('crear_entidad')).status_code, 403)
        self.assertEqual(self.client.get(reverse('editar_entidad', args=[self.proveedor.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse('cambiar_estado_entidad', args=[self.proveedor.pk])).status_code, 403)
        self.client.force_login(self.finanzas)
        self.assertEqual(self.client.get(reverse('crear_entidad')).status_code, 200)

    def test_catalogo_lo_escriben_bodega_y_finanzas(self):
        # crear_articulo lleva @bloquear_escrituras_finanzas: Finanzas solo consulta el catálogo
        for u, esperado in ((self.bodeguero, 200), (self.finanzas, 403), (self.supervisor, 403), (self.gerente, 403)):
            self.client.force_login(u)
            self.assertEqual(self.client.get(reverse('crear_articulo')).status_code, esperado, u)

    def test_vistas_modificadoras_exigen_csrf_y_post(self):
        self.client.force_login(self.bodeguero)
        self.assertEqual(self.client.get(reverse('cambiar_estado_articulo', args=[self.art.pk])).status_code, 405)


class CardexInalterableTests(BaseBodega):
    def _mov(self):
        return registrar_movimiento(self.art.pk, M.TIPO_USO_INTERNO, 1, self.bodeguero, 'x', justificacion='uso de prueba en taller')

    def test_no_se_puede_editar_un_movimiento(self):
        m = self._mov()
        m.cantidad = 99
        with self.assertRaises(CardexInalterableError):
            m.save()

    def test_no_se_puede_eliminar_un_movimiento(self):
        m = self._mov()
        with self.assertRaises(CardexInalterableError):
            m.delete()
        with self.assertRaises(CardexInalterableError):
            M.objects.all().delete()
        with self.assertRaises(CardexInalterableError):
            M.objects.all().update(cantidad=0)
        self.assertEqual(M.objects.count(), 1)

    def test_el_admin_no_permite_editar_stock_ni_costos(self):
        from django.contrib import admin
        ro = admin.site._registry[Articulo].readonly_fields
        for campo in ('stock_actual', 'pmp_costo_actual', 'ultimo_costo_compra'):
            self.assertIn(campo, ro)


class IngresoDocumentoTests(BaseBodega):
    def datos(self, numero='F-1', tipo=DocumentoEntrada.TIPO_FACTURA, proveedor=None):
        return {'proveedor': proveedor or self.proveedor, 'tipo_documento': tipo,
                'numero_documento': numero, 'fecha_emision': '2026-11-01'}

    def linea(self, art=None, cant=10, precio=1200):
        return {'articulo_id': (art or self.art).pk, 'cantidad': cant, 'precio_unitario_base': precio}

    def test_factura_suma_stock_recalcula_pmp_y_deja_cardex(self):
        registrar_documento_entrada(self.datos(), [self.linea()], usuario=self.bodeguero)
        self.art.refresh_from_db()
        self.assertEqual(self.art.stock_actual, Decimal('20'))
        self.assertEqual(self.art.ultimo_costo_compra, 1200)
        self.assertEqual(self.art.pmp_costo_actual, 1100)  # (10*1000 + 10*1200) / 20
        mov = M.objects.get()
        self.assertEqual((mov.usuario, mov.stock_anterior, mov.stock_posterior), (self.bodeguero, 10, 20))

    def test_pmp_ejemplo_del_informe(self):
        art = Articulo.objects.create(codigo_interno='C-1', nombre='Compresor', categoria=self.art.categoria,
                                      ubicacion_bodega='B')
        registrar_documento_entrada(self.datos('F-A'), [self.linea(art, 20, 95000)], usuario=self.bodeguero)
        registrar_documento_entrada(self.datos('F-B'), [self.linea(art, 15, 102000)], usuario=self.bodeguero)
        art.refresh_from_db()
        self.assertEqual(art.pmp_costo_actual, 98000)

    def test_boleta_y_guia_tambien_actualizan_pmp(self):
        for i, tipo in enumerate((DocumentoEntrada.TIPO_BOLETA, DocumentoEntrada.TIPO_GUIA)):
            registrar_documento_entrada(self.datos(f'X-{i}', tipo), [self.linea(precio=2000)], usuario=self.bodeguero)
        self.art.refresh_from_db()
        self.assertGreater(self.art.pmp_costo_actual, 1000)

    def test_nota_credito_resta_stock_y_mantiene_pmp(self):
        registrar_documento_entrada(self.datos('NC-1', DocumentoEntrada.TIPO_NOTA_CREDITO),
                                    [self.linea(cant=4, precio=3000)], usuario=self.bodeguero)
        self.art.refresh_from_db()
        self.assertEqual((self.art.stock_actual, self.art.pmp_costo_actual), (Decimal('6'), 1000))

    def test_folio_duplicado_se_rechaza(self):
        registrar_documento_entrada(self.datos('F-9'), [self.linea()], usuario=self.bodeguero)
        with self.assertRaises(ValidationError):
            registrar_documento_entrada(self.datos('f-9'), [self.linea()], usuario=self.bodeguero)

    def test_no_se_puede_usar_un_mandante_como_proveedor(self):
        with self.assertRaises(ValidationError):
            registrar_documento_entrada(self.datos(proveedor=self.mandante), [self.linea()], usuario=self.bodeguero)

    def test_sin_usuario_se_rechaza(self):
        with self.assertRaises(ValidationError):
            registrar_documento_entrada(self.datos(), [self.linea()])

    def test_precios_no_cambian_sin_documento(self):
        with self.assertRaises(ValidationError):
            registrar_movimiento(self.art.pk, M.TIPO_ENTRADA, 1, self.bodeguero, 'x', costo=5000, actualizar_costos=True)
        self.art.refresh_from_db()
        self.assertEqual(self.art.pmp_costo_actual, 1000)

    def test_articulo_desactivado_no_recibe_ingresos(self):
        self.art.activo = False
        self.art.save()
        with self.assertRaises(ValidationError):
            registrar_documento_entrada(self.datos(), [self.linea()], usuario=self.bodeguero)

    def test_post_ajax_por_bodega_funciona(self):
        self.client.force_login(self.bodeguero)
        r = self.client.post(reverse('registro_documento'), data={
            'proveedor': self.proveedor.pk, 'tipo_documento': 'FACTURA', 'numero_documento': 'F-77',
            'fecha_emision': '2026-11-01',
            'lineas': [{'articulo_id': self.art.pk, 'cantidad': 2, 'precio_unitario_base': 1000}],
        }, content_type='application/json')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.stock(), Decimal('12'))


class DespachoTests(BaseBodega):
    def test_despacho_ok_rebaja_stock_emite_vale_y_firma(self):
        s = self.solicitud(3)
        d = despachar(s.pk, self.bodeguero, self.tecnico.pk, PNG)
        s.refresh_from_db()
        self.assertEqual(self.stock(), Decimal('7'))
        self.assertEqual(s.estado, SolicitudDespacho.Estado.DESPACHADA)
        mov = d.movimientos.get()
        self.assertEqual((mov.tipo_movimiento, mov.costo_unitario, mov.obra, mov.tecnico),
                         (M.TIPO_EGRESO_OBRA, 1000, self.obra, self.tecnico))
        self.assertEqual(d.mandante, self.mandante)

    def test_no_despacha_sin_stock_y_no_cambia_nada(self):
        s = self.solicitud(50)
        with self.assertRaisesMessage(ValidationError, 'Stock insuficiente'):
            despachar(s.pk, self.bodeguero, self.tecnico.pk, PNG)
        s.refresh_from_db()
        self.assertEqual((self.stock(), s.estado), (Decimal('10'), SolicitudDespacho.Estado.PENDIENTE))
        self.assertEqual(M.objects.count(), 0)

    def test_si_falla_una_linea_se_revierte_todo(self):
        s = self.solicitud(3)
        DetalleSolicitud.objects.create(solicitud=s, articulo=self.art2, cantidad=99)
        with self.assertRaises(ValidationError):
            despachar(s.pk, self.bodeguero, self.tecnico.pk, PNG)
        self.assertEqual(self.stock(), Decimal('10'))

    def test_exige_firma_y_tecnico_valido(self):
        s = self.solicitud()
        for firma in ('', 'data:image/png;base64,AAAA', 'cualquier cosa'):
            with self.assertRaises(ValidationError):
                despachar(s.pk, self.bodeguero, self.tecnico.pk, firma)
        with self.assertRaises(ValidationError):  # un supervisor no es técnico receptor
            despachar(s.pk, self.bodeguero, self.supervisor.pk, PNG)
        with self.assertRaises(ValidationError):
            despachar(s.pk, self.bodeguero, '', PNG)

    def test_solo_obras_activas_y_solicitudes_pendientes(self):
        s = self.solicitud()
        self.obra.estado = Obra.Estado.CERRADA
        self.obra.save()
        with self.assertRaises(ValidationError):
            despachar(s.pk, self.bodeguero, self.tecnico.pk, PNG)
        self.obra.estado = Obra.Estado.ACTIVA
        self.obra.save()
        despachar(s.pk, self.bodeguero, self.tecnico.pk, PNG)
        with self.assertRaises(ValidationError):  # no se despacha dos veces
            despachar(s.pk, self.bodeguero, self.tecnico.pk, PNG)
        self.assertEqual(self.stock(), Decimal('7'))

    def test_flujo_por_pantalla_y_comprobante(self):
        s = self.solicitud(2)
        self.client.force_login(self.bodeguero)
        r = self.client.post(reverse('despachar_solicitud', args=[s.pk]), {'tecnico': self.tecnico.pk, 'firma': PNG})
        self.assertEqual(r.status_code, 302, r.content[:300])
        r = self.client.get(r.url)
        self.assertContains(r, 'Vale de Salida')
        self.assertContains(r, 'Cliente SpA')

    def test_rechazar_solicitud_exige_motivo(self):
        s = self.solicitud()
        self.client.force_login(self.bodeguero)
        self.client.post(reverse('rechazar_solicitud', args=[s.pk]), {'motivo': 'corto'})
        s.refresh_from_db()
        self.assertEqual(s.estado, SolicitudDespacho.Estado.PENDIENTE)
        self.client.post(reverse('rechazar_solicitud', args=[s.pk]), {'motivo': 'Stock insuficiente de cañería'})
        s.refresh_from_db()
        self.assertEqual(s.estado, SolicitudDespacho.Estado.RECHAZADA)
        self.assertEqual(self.stock(), Decimal('10'))


class SalidasTipificadasTests(BaseBodega):
    def test_merma_sin_justificacion_falla(self):
        for texto in ('', '   ', 'corta'):
            with self.assertRaises(ValidationError):
                registrar_salida_tipificada(M.TIPO_MERMA, self.art.pk, 1, self.bodeguero, texto)
        self.assertEqual(self.stock(), Decimal('10'))
        self.assertEqual(M.objects.count(), 0)

    def test_merma_con_justificacion_resta_y_registra(self):
        m = registrar_salida_tipificada(M.TIPO_MERMA, self.art.pk, 2, self.bodeguero, 'Dañada por agua en patio')
        self.assertEqual(self.stock(), Decimal('8'))
        self.assertEqual((m.tipo_movimiento, m.justificacion), (M.TIPO_MERMA, 'Dañada por agua en patio'))

    def test_stock_nunca_negativo(self):
        with self.assertRaises(ValidationError):
            registrar_salida_tipificada(M.TIPO_USO_INTERNO, self.art.pk, 99, self.bodeguero, 'uso en taller central')
        self.assertEqual(self.stock(), Decimal('10'))

    def test_cantidad_con_mas_de_dos_decimales_o_invalida(self):
        for c in ('0', '-1', '1.234', 'abc', 'NaN', 'Infinity'):
            with self.assertRaises(ValidationError):
                registrar_salida_tipificada(M.TIPO_MERMA, self.art.pk, c, self.bodeguero, 'justificación válida')

    def test_devolucion_a_proveedor_resta_y_exige_proveedor(self):
        with self.assertRaises(ValidationError):
            registrar_salida_tipificada(M.TIPO_DEVOLUCION_PROVEEDOR, self.art.pk, 1, self.bodeguero, 'Producto defectuoso')
        with self.assertRaises(ValidationError):  # un mandante no es proveedor
            registrar_salida_tipificada(M.TIPO_DEVOLUCION_PROVEEDOR, self.art.pk, 1, self.bodeguero,
                                        'Producto defectuoso', proveedor=self.mandante)
        registrar_salida_tipificada(M.TIPO_DEVOLUCION_PROVEEDOR, self.art.pk, 1, self.bodeguero,
                                    'Producto defectuoso', proveedor=self.proveedor)
        self.assertEqual(self.stock(), Decimal('9'))

    def test_devolucion_desde_obra_suma_y_no_excede_lo_despachado(self):
        despachar(self.solicitud(4).pk, self.bodeguero, self.tecnico.pk, PNG)   # stock 6
        with self.assertRaises(ValidationError):
            registrar_salida_tipificada(M.TIPO_DEVOLUCION_OBRA, self.art.pk, 5, self.bodeguero,
                                        'Sobrante de la faena', obra=self.obra)
        m = registrar_salida_tipificada(M.TIPO_DEVOLUCION_OBRA, self.art.pk, 3, self.bodeguero,
                                        'Sobrante de la faena', obra=self.obra)
        self.assertEqual(self.stock(), Decimal('9'))
        self.assertEqual(m.costo_unitario, 1000)  # al costo con que salió
        with self.assertRaises(ValidationError):  # solo queda 1 por devolver
            registrar_salida_tipificada(M.TIPO_DEVOLUCION_OBRA, self.art.pk, 2, self.bodeguero,
                                        'Sobrante de la faena', obra=self.obra)

    def test_formulario_por_pantalla(self):
        self.client.force_login(self.bodeguero)
        r = self.client.post(reverse('salida_tipificada'), {
            'tipo': 'MERMA', 'articulo': self.art.pk, 'cantidad': '1', 'justificacion': 'Pallets dañados por agua'})
        self.assertEqual(r.status_code, 302)
        r = self.client.post(reverse('salida_tipificada'), {
            'tipo': 'MERMA', 'articulo': self.art.pk, 'cantidad': '1', 'justificacion': ''})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(M.objects.count(), 1)


class InventarioFisicoTests(BaseBodega):
    def conteo_todo(self, sesion, valores):
        guardar_conteo(sesion.pk, {d.pk: valores[d.articulo_id] for d in sesion.detalles.all()})

    def test_sesion_por_sector_ajusta_valoriza_y_no_se_reabre(self):
        s = abrir_sesion_inventario('Pasillo A', self.bodeguero)
        self.assertEqual(s.detalles.count(), 2)
        self.conteo_todo(s, {self.art.pk: '8', self.art2.pk: '6'})   # -2 y +1
        cerrar_sesion_inventario(s.pk, self.bodeguero, 'Conteo cíclico del pasillo A')
        s.refresh_from_db()
        self.assertEqual((self.stock(), self.stock(self.art2)), (Decimal('8'), Decimal('6')))
        self.assertEqual(s.estado, SesionInventario.Estado.CERRADA)
        self.assertEqual(s.valor_diferencia_total, -2 * 1000 + 1 * 2000)
        self.assertEqual({m.tipo_movimiento for m in s.movimientos.all()}, {M.TIPO_AJUSTE_NEG, M.TIPO_AJUSTE_POS})
        with self.assertRaises(ValidationError):
            cerrar_sesion_inventario(s.pk, self.bodeguero, 'otra vez, no debería')
        with self.assertRaises(ValidationError):
            guardar_conteo(s.pk, {})
        s.estado = SesionInventario.Estado.ABIERTA
        with self.assertRaises(CardexInalterableError):
            s.save()

    def test_no_cierra_con_articulos_sin_contar_ni_diferencias_sin_observacion(self):
        s = abrir_sesion_inventario('Pasillo A', self.bodeguero)
        det = s.detalles.get(articulo=self.art)
        guardar_conteo(s.pk, {det.pk: '9'})
        with self.assertRaisesMessage(ValidationError, 'por contar'):
            cerrar_sesion_inventario(s.pk, self.bodeguero, 'observación suficiente')
        self.conteo_todo(s, {self.art.pk: '9', self.art2.pk: '5'})
        with self.assertRaisesMessage(ValidationError, 'observación'):
            cerrar_sesion_inventario(s.pk, self.bodeguero, '')
        self.assertEqual(self.stock(), Decimal('10'))
        self.assertEqual(M.objects.count(), 0)

    def test_sin_diferencias_no_genera_movimientos(self):
        s = abrir_sesion_inventario('Pasillo A', self.bodeguero)
        self.conteo_todo(s, {self.art.pk: '10', self.art2.pk: '5'})
        cerrar_sesion_inventario(s.pk, self.bodeguero, '')
        self.assertEqual(M.objects.count(), 0)

    def test_una_sola_sesion_abierta_por_sector(self):
        abrir_sesion_inventario('Pasillo A', self.bodeguero)
        with self.assertRaises(ValidationError):
            abrir_sesion_inventario('Pasillo A', self.bodeguero)
        with self.assertRaises(ValidationError):
            abrir_sesion_inventario('Sector inexistente', self.bodeguero)

    def test_conteo_negativo_rechazado(self):
        s = abrir_sesion_inventario('Pasillo A', self.bodeguero)
        with self.assertRaises(ValidationError):
            guardar_conteo(s.pk, {s.detalles.first().pk: '-3'})

    def test_exportar_y_pantallas(self):
        self.client.force_login(self.bodeguero)
        r = self.client.post(reverse('lista_sesiones_inventario'), {'sector': 'Pasillo A'})
        self.assertEqual(r.status_code, 302)
        s = SesionInventario.objects.get()
        self.assertEqual(self.client.get(r.url).status_code, 200)
        exp = self.client.get(reverse('exportar_sesion_inventario', args=[s.pk]))
        self.assertEqual(exp.status_code, 200)
        self.assertIn('Cañería de cobre', exp.content.decode('utf-8-sig'))


class CatalogoTests(BaseBodega):
    def datos(self, **extra):
        d = {'codigo_interno': 'N-1', 'nombre': 'Nuevo', 'categoria': self.art.categoria.pk, 'unidad_medida': 'UND',
             'ubicacion_bodega': 'P9', 'stock_minimo': '5', 'stock_critico': '2'}
        d.update(extra)
        return d

    def test_crear_editar_y_desactivar_sin_tocar_stock_ni_precios(self):
        self.client.force_login(self.bodeguero)
        # Aunque se intente enviar stock/costos en el POST, el formulario los ignora
        r = self.client.post(reverse('crear_articulo'), self.datos(stock_actual='999', pmp_costo_actual='9999'))
        self.assertEqual(r.status_code, 302)
        art = Articulo.objects.get(codigo_interno='N-1')
        self.assertEqual((art.stock_actual, art.pmp_costo_actual), (0, 0))
        self.client.post(reverse('editar_articulo', args=[art.pk]), self.datos(nombre='Renombrado', stock_actual='50'))
        art.refresh_from_db()
        self.assertEqual((art.nombre, art.stock_actual), ('Renombrado', 0))
        self.client.post(reverse('cambiar_estado_articulo', args=[art.pk]))
        art.refresh_from_db()
        self.assertFalse(art.activo)

    def test_codigo_duplicado_se_rechaza(self):
        self.client.force_login(self.bodeguero)
        r = self.client.post(reverse('crear_articulo'), self.datos(codigo_interno='A-1'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Articulo.objects.filter(codigo_interno__iexact='A-1').count(), 1)


class DashboardTests(BaseBodega):
    def test_dashboard_muestra_datos_reales(self):
        registrar_salida_tipificada(M.TIPO_MERMA, self.art.pk, 1, self.bodeguero, 'Dañada por agua en patio')
        self.client.force_login(self.bodeguero)
        r = self.client.get(reverse('core:dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.context['total_articulos'], 2)
        self.assertEqual(r.context['movimientos_hoy'], 1)
        self.assertContains(r, 'Cañería de cobre')
        self.assertContains(r, 'Despachos a Obras')

    def test_el_menu_depende_del_rol(self):
        self.client.force_login(self.supervisor)
        r = self.client.get(reverse('core:dashboard'))
        self.assertNotContains(r, 'Mermas y Devoluciones')
        self.assertNotContains(r, 'Kardex (solo lectura)')
        self.client.force_login(self.bodeguero)
        self.assertContains(self.client.get(reverse('core:dashboard')), 'Mermas y Devoluciones')


class RestockFlujoTests(BaseBodega):
    """Bodega solicita -> Finanzas aprueba -> Técnico recibe, con segregación de funciones."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        User = get_user_model()
        # Usuario con doble rol: sirve para probar que nadie aprueba ni recibe lo propio
        cls.mixto = User.objects.create_user('bodega_finanzas', password='x')
        cls.mixto.groups.add(cls.grupos['bodega'], cls.grupos['finanzas'])
        cls.tecnico2 = User.objects.create_user('tecnico2', password='x')
        cls.tecnico2.groups.add(cls.grupos['tecnico'])

    def orden(self, usuario=None, cantidad='5', costo=1200):
        return crear_orden_restock(self.art.pk, cantidad, costo, usuario or self.bodeguero)

    def checks(self, **extra):
        return {'check_cantidad': 'on', 'check_estado': 'on', 'check_especificacion': 'on', **extra}

    def test_bodega_solicita_y_queda_pendiente_de_finanzas(self):
        orden = self.orden()
        self.assertEqual(orden.estado, OrdenRestock.ESTADO_PENDIENTE_FINANZAS)
        self.assertEqual(orden.solicitado_por, self.bodeguero)
        self.assertEqual(self.stock(), Decimal('10'))

    def test_bodega_solicita_desde_la_vista(self):
        self.client.force_login(self.bodeguero)
        self.client.post(reverse('lista_restock'), {'articulo': self.art.pk, 'cantidad': '4', 'costo_unitario': '900'})
        orden = OrdenRestock.objects.get()
        self.assertEqual(orden.estado, OrdenRestock.ESTADO_PENDIENTE_FINANZAS)
        self.assertEqual(orden.cantidad, Decimal('4'))

    def test_quien_solicita_no_aprueba_su_propia_orden(self):
        orden = self.orden(usuario=self.mixto)
        with self.assertRaises(ValidationError):
            resolver_orden_restock(orden.pk, self.mixto, aprobar=True)
        orden.refresh_from_db()
        self.assertEqual(orden.estado, OrdenRestock.ESTADO_PENDIENTE_FINANZAS)
        self.assertIsNone(orden.aprobado_por)

        # Por la vista tampoco cambia de estado
        self.client.force_login(self.mixto)
        self.client.post(reverse('aprobar_restock_finanzas', args=[orden.pk]), {'decision': 'aprobar'})
        orden.refresh_from_db()
        self.assertEqual(orden.estado, OrdenRestock.ESTADO_PENDIENTE_FINANZAS)

    def test_finanzas_distinto_aprueba_y_rechazo_exige_motivo(self):
        orden = self.orden()
        resolver_orden_restock(orden.pk, self.finanzas, aprobar=True)
        orden.refresh_from_db()
        self.assertEqual(orden.estado, OrdenRestock.ESTADO_APROBADA_FINANZAS)
        self.assertEqual(orden.aprobado_por, self.finanzas)

        otra = self.orden()
        with self.assertRaises(ValidationError):
            resolver_orden_restock(otra.pk, self.finanzas, aprobar=False, observacion='caro')
        otra.refresh_from_db()
        self.assertEqual(otra.estado, OrdenRestock.ESTADO_PENDIENTE_FINANZAS)
        resolver_orden_restock(otra.pk, self.finanzas, aprobar=False, observacion='Presupuesto sobre el valor de mercado')
        otra.refresh_from_db()
        self.assertEqual(otra.estado, OrdenRestock.ESTADO_RECHAZADA)

    def test_gerencia_sin_rol_finanzas_no_aprueba(self):
        orden = self.orden()
        self.client.force_login(self.gerente)
        r = self.client.post(reverse('aprobar_restock_finanzas', args=[orden.pk]), {'decision': 'aprobar'})
        self.assertEqual(r.status_code, 403)
        orden.refresh_from_db()
        self.assertEqual(orden.estado, OrdenRestock.ESTADO_PENDIENTE_FINANZAS)

    def test_recibir_sin_los_tres_checks_no_ingresa_stock(self):
        orden = self.orden()
        resolver_orden_restock(orden.pk, self.finanzas, aprobar=True)
        self.client.force_login(self.tecnico)
        self.client.post(reverse('confirmar_recepcion_restock', args=[orden.pk]),
                         {'check_cantidad': 'on', 'check_estado': 'on'})
        orden.refresh_from_db()
        self.assertEqual(orden.estado, OrdenRestock.ESTADO_APROBADA_FINANZAS)
        self.assertEqual(self.stock(), Decimal('10'))
        self.assertFalse(M.objects.filter(orden_restock=orden).exists())

    def test_quien_aprobo_no_confirma_la_recepcion(self):
        orden = self.orden()
        resolver_orden_restock(orden.pk, self.mixto, aprobar=True)
        with self.assertRaises(ValidationError):
            recibir_orden_restock(orden.pk, self.mixto)

        self.client.force_login(self.mixto)
        self.client.post(reverse('confirmar_recepcion_restock', args=[orden.pk]), self.checks())
        orden.refresh_from_db()
        self.assertEqual(orden.estado, OrdenRestock.ESTADO_APROBADA_FINANZAS)
        self.assertEqual(self.stock(), Decimal('10'))

    def test_tecnico_distinto_recibe_con_los_tres_checks(self):
        orden = self.orden(cantidad='5')
        resolver_orden_restock(orden.pk, self.finanzas, aprobar=True)
        self.client.force_login(self.tecnico2)
        self.client.post(reverse('confirmar_recepcion_restock', args=[orden.pk]), self.checks())

        orden.refresh_from_db()
        self.assertEqual(orden.estado, OrdenRestock.ESTADO_INSERTADA)
        self.assertEqual(orden.revisado_por, self.tecnico2)
        self.assertEqual(self.stock(), Decimal('15'))
        mov = M.objects.get(orden_restock=orden)
        self.assertEqual(mov.tipo_movimiento, M.TIPO_ENTRADA)
        self.assertEqual(mov.cantidad, Decimal('5'))
        self.assertEqual(mov.usuario, self.tecnico2)


class ChecklistGeneralTests(BaseBodega):
    def test_diferencia_genera_ajuste_y_valoriza(self):
        for contado, tipo, valor in (('12', M.TIPO_AJUSTE_POS, 2000), ('7', M.TIPO_AJUSTE_NEG, -5000)):
            with self.subTest(contado=contado):
                antes = self.stock()
                sesion = registrar_checklist_general({self.art.pk: contado}, self.bodeguero,
                                                     'Diferencia detectada en el conteo físico')
                mov = M.objects.get(sesion_inventario=sesion)
                self.assertEqual(mov.tipo_movimiento, tipo)
                self.assertEqual(mov.cantidad, abs(Decimal(contado) - antes))
                self.assertEqual(self.stock(), Decimal(contado))
                # PMP del artículo: $1.000 -> (contado - stock) x 1.000
                self.assertEqual(sesion.valor_diferencia_total, (Decimal(contado) - antes) * 1000)
                self.assertEqual(sesion.valor_diferencia_total, valor)

    def test_conteo_igual_al_stock_no_genera_movimiento(self):
        sesion = registrar_checklist_general({self.art.pk: '10', self.art2.pk: '5'}, self.bodeguero)
        self.assertFalse(M.objects.filter(sesion_inventario=sesion).exists())
        self.assertEqual(sesion.valor_diferencia_total, 0)
        self.assertEqual(sesion.detalles.count(), 2)
        self.assertEqual(self.stock(), Decimal('10'))

    def test_vista_bodega_registra_y_crea_asientos_en_cardex(self):
        self.client.force_login(self.bodeguero)
        r = self.client.post(reverse('checklist_inventario_bodega'), {
            'revisado': [str(self.art.pk), str(self.art2.pk)],
            f'contado_{self.art.pk}': '9',
            f'contado_{self.art2.pk}': '5',
            'observaciones': 'Falta una unidad en el pasillo A',
        })
        self.assertRedirects(r, reverse('checklist_inventario_bodega'))
        self.assertEqual(self.stock(), Decimal('9'))
        sesion = SesionInventario.objects.get(sector=SECTOR_CHECKLIST_GENERAL)
        self.assertEqual(M.objects.filter(sesion_inventario=sesion, tipo_movimiento=M.TIPO_AJUSTE_NEG).count(), 1)
        # El Cardex de Auditoría lee el Kardex: el ajuste aparece ahí sin copias
        ajuste = M.objects.get(sesion_inventario=sesion)
        self.client.force_login(self.gerente)
        html = self.client.get(reverse('auditoria:lista_cardex')).content.decode()
        self.assertIn(f'#{ajuste.pk}', html)
        self.assertIn('-1', html)

    def test_permisos_de_la_vista(self):
        url = reverse('checklist_inventario_bodega')
        self.client.force_login(self.tecnico)
        self.assertEqual(self.client.get(url).status_code, 200)
        self.assertEqual(self.client.post(url, {'revisado': [str(self.art.pk)], f'contado_{self.art.pk}': '1',
                                                'observaciones': 'Intento sin permiso'}).status_code, 403)
        self.assertEqual(self.stock(), Decimal('10'))
        self.client.force_login(self.finanzas)
        self.assertEqual(self.client.get(url).status_code, 403)
