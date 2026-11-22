"""Matriz de roles (RBAC) de FYAG SpA según Anexo C, basada en Grupos de Django.

El id del rol es el identificador canónico del perfil. Un usuario tiene un rol
si pertenece al grupo con ese id o a cualquiera de sus equivalencias registradas.
Los superusuarios pasan siempre.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

ROLES = [
    {
        'id': 'gerencia',
        'group_name': 'Administrador General',
        'name': 'Administrador General',
        'badge': 'Acceso Total & Auditoría',
        'description': 'Acceso total al sistema, gestión de usuarios/permisos, auditoría Kardex, contra-asientos e indicadores.',
    },
    {
        'id': 'finanzas',
        'group_name': 'Administración',
        'name': 'Administración / Finanzas',
        'badge': 'Presupuestos, Facturas & Pagos',
        'description': 'Acceso a presupuestos, facturación, pagos a proveedores, clientes/mandantes y valorización PMP.',
    },
    {
        'id': 'bodega',
        'group_name': 'Bodega / Logística',
        'name': 'Bodega / Logística',
        'badge': 'CRUD Inventario & Despachos',
        'description': 'Acceso a inventario, ingresos de documentos, despachos a obra, mermas e inventario físico.',
    },
    {
        'id': 'supervisor',
        'group_name': 'Supervisor de Obras',
        'name': 'Supervisor de Obras',
        'badge': 'Obras, Materiales & Terreno',
        'description': 'Gestión de obras asignadas, solicitudes de materiales, hojas de servicio y consulta de stock.',
    },
    {
        'id': 'tecnico',
        'group_name': 'Técnico',
        'name': 'Técnico',
        'badge': 'Hojas de Servicio & Terreno',
        'description': 'Registro de hojas de servicio, check list y consulta de stock en terreno.',
    },
    {
        'id': 'consulta',
        'group_name': 'Consulta',
        'name': 'Consulta / Auditoría Lectura',
        'badge': 'Solo Lectura',
        'description': 'Acceso únicamente de lectura a la información autorizada del sistema.',
    },
]

ROLES_POR_ID = {r['id']: r for r in ROLES}

# Equivalencias entre IDs cortos (LoginForm / permisos) y nombres de Grupos en Django
ALIAS_ROLES = {
    'gerencia': ('gerencia', 'Administrador General', 'Administrador General / Gerencia'),
    'finanzas': ('finanzas', 'Administración', 'Administrativo Finanzas', 'Administrador / Finanzas'),
    'bodega': ('bodega', 'Bodega / Logística', 'Bodega Logistica', 'Encargado de Bodega / Logística'),
    'supervisor': ('supervisor', 'Supervisor de Obras', 'Supervisor de Obra'),
    'tecnico': ('tecnico', 'Técnico', 'Tecnico'),
    'consulta': ('consulta', 'Consulta', 'Auditor', 'auditor'),
}

_GRUPO_A_ROL_ID = {}
for _rol_id, _aliases in ALIAS_ROLES.items():
    for _alias in _aliases:
        _GRUPO_A_ROL_ID[_alias.strip().lower()] = _rol_id


def normalizar_rol_id(nombre_o_id):
    """Convierte un nombre de grupo o id de rol en su id canónico ('gerencia', 'bodega', etc.)."""
    if not nombre_o_id:
        return None
    return _GRUPO_A_ROL_ID.get(str(nombre_o_id).strip().lower())


def _nombres_grupo_para(ids):
    nombres = set()
    for rol_id in ids:
        nombres.add(rol_id)
        canon = normalizar_rol_id(rol_id)
        if canon:
            nombres.update(ALIAS_ROLES.get(canon, ()))
        nombres.update(ALIAS_ROLES.get(rol_id, ()))
    return nombres


def tiene_rol(user, *ids):
    """True si el usuario pertenece a alguno de los roles indicados."""
    if not user or not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=_nombres_grupo_para(ids)).exists()


def roles_de(user):
    """Lista de roles (dicts de ROLES) que tiene el usuario."""
    if not user or not user.is_authenticated:
        return []
    if user.is_superuser:
        return list(ROLES)
    grupos = set(user.groups.values_list('name', flat=True))
    return [r for r in ROLES if grupos.intersection(_nombres_grupo_para([r['id']]))]


def rol_requerido(*ids):
    """Decorador de vistas: exige login y pertenecer a alguno de los roles.

    Sin sesión -> redirige al login. Con sesión pero sin rol -> HTTP 403
    (se muestra templates/403.html).
    """
    def decorador(vista):
        @wraps(vista)
        def envoltura(request, *args, **kwargs):
            if not tiene_rol(request.user, *ids):
                raise PermissionDenied
            return vista(request, *args, **kwargs)
        return login_required(envoltura)
    return decorador
