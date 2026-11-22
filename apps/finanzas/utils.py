from functools import wraps

from django.core.exceptions import PermissionDenied

from apps.usuarios.roles import tiene_rol


def bloquear_escrituras_finanzas(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        usuario = request.user
        es_personal_finanzas = (
            usuario.is_authenticated
            and not usuario.is_superuser
            and tiene_rol(usuario, 'finanzas')
            and not tiene_rol(usuario, 'bodega', 'gerencia')
        )
        if es_personal_finanzas:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def puede_ver_cuentas_bancarias(user):
    return bool(user and tiene_rol(user, 'finanzas'))


def enmascarar_numero_cuenta(numero_cuenta):
    return f'****{str(numero_cuenta)[-4:]}'
