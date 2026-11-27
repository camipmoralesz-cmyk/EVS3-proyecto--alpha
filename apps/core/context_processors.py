from apps.usuarios.forms import rol_activo
from apps.usuarios.roles import ROLES, normalizar_rol_id, roles_de, tiene_rol

# (app_name, url_name) -> sección resaltada en el menú lateral unificado
SECCIONES_POR_APP = {
    ('core', 'dashboard'): 'dashboard',
    ('core', 'auditoria_kardex'): 'auditoria',
    ('core', 'aprobacion_inventarios'): 'aprobaciones',
    ('core', 'alertas_stock'): 'alertas',
    ('core', 'gestion_usuarios'): 'usuarios',
    ('core', 'consulta_lectura'): 'consulta',
    ('obras', 'lista_obras'): 'obras_lista',
    ('obras', 'detalle_obra'): 'obras_lista',
    ('obras', 'crear_obra'): 'obras_lista',
    ('obras', 'editar_obra'): 'obras_lista',
    ('obras', 'lista_solicitudes'): 'obras_solicitudes',
    ('obras', 'lista_hojas_servicio'): 'obras_hojas',
    ('obras', 'kardex_lectura'): 'obras_kardex',
    ('finanzas', 'panel'): 'finanzas_panel',
    ('finanzas', 'facturas_lista'): 'finanzas_facturas',
    ('finanzas', 'factura_crear'): 'finanzas_facturas',
    ('finanzas', 'factura_detalle'): 'finanzas_facturas',
    ('finanzas', 'factura_editar'): 'finanzas_facturas',
    ('finanzas', 'factura_eliminar'): 'finanzas_facturas',
    ('finanzas', 'pagos_lista'): 'finanzas_pagos',
    ('finanzas', 'pago_crear'): 'finanzas_pagos',
    ('finanzas', 'pago_editar'): 'finanzas_pagos',
    ('finanzas', 'pago_eliminar'): 'finanzas_pagos',
    ('finanzas', 'entidades_lista'): 'finanzas_entidades',
    ('finanzas', 'entidad_crear'): 'finanzas_entidades',
    ('finanzas', 'entidad_editar'): 'finanzas_entidades',
    ('finanzas', 'entidad_eliminar'): 'finanzas_entidades',
    ('finanzas', 'presupuestos_lista'): 'finanzas_presupuestos',
    ('finanzas', 'obra_crear'): 'finanzas_presupuestos',
    ('finanzas', 'presupuesto_editar'): 'finanzas_presupuestos',
    ('finanzas', 'presupuesto_eliminar'): 'finanzas_presupuestos',
    ('auditoria', 'lista_cardex'): 'cardex_auditoria',
    ('auditoria', 'lista_bitacora'): 'bitacora',
    ('auditoria', 'logs_acceso'): 'accesos',
}

SECCIONES = {
    'dashboard': 'dashboard',
    'lista_articulos': 'catalogo',
    'crear_articulo': 'catalogo',
    'editar_articulo': 'catalogo',
    'registro_documento': 'compras',
    'lista_documentos': 'compras',
    'detalle_documento': 'compras',
    'lista_solicitudes': 'despachos',
    'despachar_solicitud': 'despachos',
    'comprobante_despacho': 'despachos',
    'salida_tipificada': 'salidas',
    'lista_sesiones_inventario': 'fisico',
    'detalle_sesion_inventario': 'fisico',
    'inventario_stock': 'stock',
    'historial_movimientos': 'kardex',
    'lista_entidades': 'entidades',
    'crear_entidad': 'entidades',
    'editar_entidad': 'entidades',
}


def roles_processor(request):
    if not request.user.is_authenticated:
        return {
            'es_admin_general': False,
            'es_supervisor_obras': False,
            'rol_usuario': 'Invitado',
        }

    es_admin_general = tiene_rol(request.user, 'gerencia')
    es_supervisor_obras = tiene_rol(request.user, 'supervisor')

    roles = roles_de(request.user)
    if request.user.is_superuser and not request.user.groups.exists():
        rol_actual = 'Administrador General'
    elif roles:
        rol_actual = roles[0]['name']
    else:
        grupos = list(request.user.groups.values_list('name', flat=True))
        rol_actual = grupos[0] if grupos else 'Operador'

    return {
        'es_admin_general': es_admin_general,
        'es_supervisor_obras': es_supervisor_obras,
        'rol_usuario': rol_actual,
    }


def navegacion(request):
    """Roles normalizados del usuario, rol del panel lateral y sección activa.

    'mis_roles' se mantiene para los permisos finos de cada plantilla; el sidebar
    usa solo 'rol_panel' para mostrar un único panel por usuario.
    """
    user = request.user
    if not user.is_authenticated:
        return {'mis_roles': set(), 'rol_panel': '', 'seccion_activa': ''}

    if user.is_superuser:
        roles = {r['id'] for r in ROLES}
    else:
        roles = set()
        for nombre_grupo in user.groups.values_list('name', flat=True):
            canon = normalizar_rol_id(nombre_grupo)
            roles.add(canon if canon else nombre_grupo)

    match = getattr(request, 'resolver_match', None)
    seccion = ''
    if match:
        seccion = SECCIONES_POR_APP.get(
            (match.app_name, match.url_name),
            SECCIONES.get(match.url_name, ''),
        )

    rol_panel = rol_activo(user, request.session.get('rol_activo')) or ''

    return {'mis_roles': roles, 'rol_panel': rol_panel, 'seccion_activa': seccion}
