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
            and usuario.groups.filter(name='finanzas').exists()
        )
        if es_personal_finanzas:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def puede_ver_cuentas_bancarias(user):
    return bool(user and tiene_rol(user, 'finanzas'))


def enmascarar_numero_cuenta(numero_cuenta):
    return f'****{str(numero_cuenta)[-4:]}'
