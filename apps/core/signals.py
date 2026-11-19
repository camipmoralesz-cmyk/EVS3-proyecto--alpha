from decimal import Decimal
import logging

from django.contrib.auth.signals import user_logged_in, user_logged_out
from django.dispatch import receiver

logger = logging.getLogger(__name__)


def _obtener_ip(request):
    if not request:
        return 'desconocida'
    xff = request.META.get('HTTP_X_FORWARDED_FOR')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'desconocida')


def _obtener_rol_usuario(user):
    if not user:
        return 'Sin rol'
    grupos = list(user.groups.values_list('name', flat=True))
    if grupos:
        return ', '.join(grupos)
    return 'Administrador General' if user.is_superuser else 'Operador'


def _registrar_evento_acceso(user, request, tipo_movimiento, descripcion):
    if not user or not getattr(user, 'pk', None):
        return
    try:
        from apps.inventario.models import MovimientoInventario

        rol = _obtener_rol_usuario(user)
        ip = _obtener_ip(request)
        nombre = user.get_full_name() or user.username
        referencia = f"{descripcion} | Personal: {nombre} (@{user.username}) | Rol: {rol} | IP: {ip}"

        MovimientoInventario.objects.create(
            articulo=None,
            documento=None,
            tipo_movimiento=tipo_movimiento,
            cantidad=Decimal('0.00'),
            stock_anterior=Decimal('0.00'),
            stock_posterior=Decimal('0.00'),
            costo_unitario=0,
            usuario=user,
            referencia=referencia[:255],
        )
    except Exception as exc:
        logger.warning("No se pudo registrar acceso en Kardex (%s): %s", tipo_movimiento, exc)


@receiver(user_logged_in)
def registrar_ingreso_sistema(sender, request, user, **kwargs):
    from apps.inventario.models import MovimientoInventario

    _registrar_evento_acceso(
        user=user,
        request=request,
        tipo_movimiento=MovimientoInventario.TIPO_INGRESO_SISTEMA,
        descripcion="Ingreso de personal al sistema",
    )


@receiver(user_logged_out)
def registrar_salida_sistema(sender, request, user, **kwargs):
    from apps.inventario.models import MovimientoInventario

    _registrar_evento_acceso(
        user=user,
        request=request,
        tipo_movimiento=MovimientoInventario.TIPO_SALIDA_SISTEMA,
        descripcion="Salida de personal del sistema",
    )
