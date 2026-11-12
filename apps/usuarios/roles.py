"""Matriz de roles (RBAC) de FYAG SpA, basada en Grupos de Django.

El id del rol es el nombre del Grupo. Un usuario tiene un rol si pertenece
a ese grupo. Los superusuarios pasan siempre.
"""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

ROLES = [
    {
        'id': 'bodega',
        'name': 'Encargado de Bodega / Logística',
        'badge': 'CRUD Inventario',
        'description': 'Ingreso de documentos, egresos a obra, mermas e inventario físico.',
    },
    {
        'id': 'finanzas',
        'name': 'Administrador / Finanzas',
        'badge': 'CRUD Entidades & PMP',
        'description': 'Gestión de catálogo maestro, proveedores y valorización PMP.',
    },
    {
        'id': 'supervisor',
        'name': 'Supervisor de Obras',
        'badge': 'Solo Lectura Obra',
        'description': 'Consulta de existencias, presupuestos y seguimiento por faena.',
    },
    {
        'id': 'gerencia',
        'name': 'Administrador General / Gerencia',
        'badge': 'Global & Auditoría',
        'description': 'Lectura global, reportes KPI, contra-asientos y bitácora SHA-256.',
    },
    {
        'id': 'tecnico',
        'name': 'Técnico (App Móvil)',
        'badge': 'Acceso Terreno',
        'description': 'Recepción de materiales, firma digital y checklists.',
    },
]

ROLES_POR_ID = {r['id']: r for r in ROLES}


def tiene_rol(user, *ids):
    """True si el usuario pertenece a alguno de los roles indicados."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name__in=ids).exists()


def roles_de(user):
    """Lista de roles (dicts de ROLES) que tiene el usuario."""
    if not user.is_authenticated:
        return []
    if user.is_superuser:
        return list(ROLES)
    grupos = set(user.groups.values_list('name', flat=True))
    return [r for r in ROLES if r['id'] in grupos]


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
