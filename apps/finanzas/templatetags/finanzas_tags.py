from django import template

from apps.usuarios.roles import tiene_rol
from apps.finanzas.utils import enmascarar_numero_cuenta, puede_ver_cuentas_bancarias

register = template.Library()


@register.filter
def es_finanzas(user):
    """Devuelve True si el usuario pertenece al grupo 'finanzas' o es superusuario."""
    return tiene_rol(user, 'finanzas')


@register.filter
def cuenta_visible(numero_cuenta, user):
    if puede_ver_cuentas_bancarias(user):
        return numero_cuenta
    return enmascarar_numero_cuenta(numero_cuenta)
