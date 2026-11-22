from django import template
from apps.usuarios.roles import tiene_rol

register = template.Library()


@register.filter
def es_finanzas(user):
    """Devuelve True si el usuario pertenece al grupo 'finanzas' o es superusuario."""
    return tiene_rol(user, 'finanzas')
