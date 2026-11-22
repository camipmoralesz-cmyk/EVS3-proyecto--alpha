def roles_processor(request):
    if not request.user.is_authenticated:
        return {'es_admin_general': False, 'rol_usuario': 'Invitado'}
    
    grupos = list(request.user.groups.values_list('name', flat=True))
    
    # Si es superusuario o pertenece al grupo Administrador General / gerencia
    es_admin_general = (
        request.user.is_superuser or
        'Administrador General' in grupos or
        'gerencia' in grupos
    )

    if 'gerencia' in grupos and 'Administrador General' not in grupos:
        rol_actual = 'Administrador General'
    else:
        rol_actual = grupos[0] if grupos else ('Administrador General' if request.user.is_superuser else 'Operador')
    
    return {
        'es_admin_general': es_admin_general,
        'rol_usuario': rol_actual,
    }
from apps.usuarios.roles import ROLES

# url_name -> sección resaltada en el menú lateral
SECCIONES = {
    'dashboard': 'dashboard',
    'lista_articulos': 'catalogo', 'crear_articulo': 'catalogo', 'editar_articulo': 'catalogo',
    'registro_documento': 'compras', 'lista_documentos': 'compras', 'detalle_documento': 'compras',
    'lista_solicitudes': 'despachos', 'despachar_solicitud': 'despachos', 'comprobante_despacho': 'despachos',
    'salida_tipificada': 'salidas',
    'lista_sesiones_inventario': 'fisico', 'detalle_sesion_inventario': 'fisico',
    'inventario_stock': 'stock',
    'historial_movimientos': 'kardex',
    'lista_entidades': 'entidades', 'crear_entidad': 'entidades', 'editar_entidad': 'entidades',
}


def navegacion(request):
    """Roles del usuario (para mostrar solo el menú que le corresponde) y sección activa."""
    user = request.user
    if not user.is_authenticated:
        return {'mis_roles': set(), 'seccion_activa': ''}
    if user.is_superuser:
        roles = {r['id'] for r in ROLES}
    else:
        roles = set(user.groups.values_list('name', flat=True))
    match = getattr(request, 'resolver_match', None)
    return {'mis_roles': roles, 'seccion_activa': SECCIONES.get(match.url_name, '') if match else ''}
