from apps.usuarios.roles import tiene_rol


def puede_ver_cuentas_bancarias(user):
    return bool(user and tiene_rol(user, 'finanzas'))


def enmascarar_numero_cuenta(numero_cuenta):
    return f'****{str(numero_cuenta)[-4:]}'
