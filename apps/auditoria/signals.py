
from django.apps import apps
from django.db.models.signals import pre_save, post_save, post_delete
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.dispatch import receiver
from django.forms.models import model_to_dict

from .models import BitacoraAuditoria, LogAcceso
from .middleware import get_current_user, get_current_ip


# ==============================================================================
# 1. CARDEX INMUTABLE (RF06 / HU-12)
# ==============================================================================
# El Cardex de Auditoría lee directamente MovimientoInventario (un solo registro
# append-only). Ya no se copia cada movimiento a una tabla aparte.


# ==============================================================================
# 2. REGISTRO AUTOMÁTICO DE LOGS DE ACCESO (Seguridad TI / Anexo C)
# ==============================================================================
@receiver(user_logged_in)
def registrar_login_exitoso(sender, request, user, **kwargs):
    ua = request.META.get('HTTP_USER_AGENT', '')[:255] if request else ''
    LogAcceso.objects.create(
        username_intentado=user.username,
        usuario=user,
        ip_origen=get_current_ip(),
        user_agent=ua,
        exitoso=True
    )


@receiver(user_login_failed)
def registrar_login_fallido(sender, credentials, request, **kwargs):
    username = (credentials.get('username') or 'desconocido')[:150]
    ua = request.META.get('HTTP_USER_AGENT', '')[:255] if request else ''
    LogAcceso.objects.create(
        username_intentado=username,
        usuario=None,
        ip_origen=get_current_ip(),
        user_agent=ua,
        exitoso=False
    )


# ==============================================================================
# 3. BITÁCORA TRANSVERSAL CON VALORES ANTERIORES Y NUEVOS (RNF02)
# ==============================================================================
MODELOS_AUDITADOS = [
    ('catalogo', 'Articulo', 'Catálogo'),
    ('entidades', 'Proveedor', 'Entidades'),
    ('obras', 'Obra', 'Obras'),
    ('inventario', 'DocumentoEntrada', 'Inventario'),
]

# Guardamos referencias para evitar que Python recolecte los receivers dinámicos
_RECEIVERS_ACTIVOS = []


def _serializar_instancia(instancia):
    datos = {}
    for k, v in model_to_dict(instancia).items():
        if k in ('password', 'last_login'):
            continue
        datos[k] = str(v) if v is not None else None
    return datos


def _registrar_hooks_para_modelo(modelo, modulo_nombre):
    def on_pre_save(sender, instance, **kwargs):
        if instance.pk:
            try:
                previo = sender.objects.get(pk=instance.pk)
                instance._estado_anterior_auditoria = _serializar_instancia(previo)
            except sender.DoesNotExist:
                instance._estado_anterior_auditoria = None
        else:
            instance._estado_anterior_auditoria = None

    def on_post_save(sender, instance, created, **kwargs):
        nuevos = _serializar_instancia(instance)
        anteriores = getattr(instance, '_estado_anterior_auditoria', None)

        if created:
            BitacoraAuditoria.objects.create(
                usuario=get_current_user(),
                ip_origen=get_current_ip(),
                modulo=modulo_nombre,
                accion='CREAR',
                modelo_afectado=sender.__name__,
                objeto_id=str(instance.pk),
                descripcion=f"Creación de {sender.__name__}: {instance}",
                valores_anteriores=None,
                valores_nuevos=nuevos
            )
        elif anteriores:
            cambios_antes = {k: anteriores[k] for k in nuevos if anteriores.get(k) != nuevos.get(k)}
            cambios_despues = {k: nuevos[k] for k in nuevos if anteriores.get(k) != nuevos.get(k)}

            if cambios_despues:
                BitacoraAuditoria.objects.create(
                    usuario=get_current_user(),
                    ip_origen=get_current_ip(),
                    modulo=modulo_nombre,
                    accion='EDITAR',
                    modelo_afectado=sender.__name__,
                    objeto_id=str(instance.pk),
                    descripcion=f"Modificación de {sender.__name__}: {instance}",
                    valores_anteriores=cambios_antes,
                    valores_nuevos=cambios_despues
                )

    def on_post_delete(sender, instance, **kwargs):
        BitacoraAuditoria.objects.create(
            usuario=get_current_user(),
            ip_origen=get_current_ip(),
            modulo=modulo_nombre,
            accion='ELIMINAR',
            modelo_afectado=sender.__name__,
            objeto_id=str(instance.pk),
            descripcion=f"Eliminación de {sender.__name__}: {instance}",
            valores_anteriores=_serializar_instancia(instance),
            valores_nuevos=None
        )

    pre_save.connect(on_pre_save, sender=modelo, weak=False)
    post_save.connect(on_post_save, sender=modelo, weak=False)
    post_delete.connect(on_post_delete, sender=modelo, weak=False)
    _RECEIVERS_ACTIVOS.extend([on_pre_save, on_post_save, on_post_delete])


for app_label, model_name, modulo_nombre in MODELOS_AUDITADOS:
    try:
        modelo_obj = apps.get_model(app_label, model_name)
        _registrar_hooks_para_modelo(modelo_obj, modulo_nombre)
    except LookupError:
        # Si un módulo aún no existe o tiene otro nombre de modelo, no rompe el arranque
        continue