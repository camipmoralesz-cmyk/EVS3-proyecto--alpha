import time

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.decorators.cache import never_cache

from .forms import LoginForm
from .roles import roles_de

MAX_INTENTOS = 3          # fallos seguidos antes de bloquear
BLOQUEO_SEGUNDOS = 30     # duración del bloqueo (súbelo en producción)
VENTANA_FALLOS = 15 * 60  # los fallos se olvidan tras 15 min sin intentos

GRUPOS_SUPERVISOR = ('supervisor', 'Supervisor de Obra', 'Supervisor de Obras')
GRUPOS_BODEGA = ('bodega', 'Bodega Logistica', 'Encargado de Bodega / Logística')
GRUPOS_FINANZAS = ('finanzas', 'Administrativo Finanzas', 'Administrador / Finanzas')
GRUPOS_GERENCIA = ('gerencia', 'Administrador General', 'Administrador General / Gerencia')
GRUPOS_AUDITOR = ('auditor', 'Auditor')

RUTA_POR_ROL_ID = {
    'supervisor': 'obras:lista_obras',
    'bodega': 'inventario_stock',
    'finanzas': 'lista_articulos',
    'gerencia': 'core:dashboard',
    'auditor': 'core:auditoria_kardex',
}


def obtener_ruta_por_rol(user, rol_seleccionado=None):
    """Determina la ruta del panel correspondiente según el grupo/rol del usuario."""
    grupos = set(user.groups.values_list('name', flat=True))

    # 1. Si el usuario pertenece a un grupo específico, se filtra y va directo a su panel
    if grupos.intersection(GRUPOS_SUPERVISOR):
        return 'obras:lista_obras'
    if grupos.intersection(GRUPOS_BODEGA):
        return 'inventario_stock'
    if grupos.intersection(GRUPOS_FINANZAS):
        return 'lista_articulos'
    if grupos.intersection(GRUPOS_AUDITOR):
        return 'core:auditoria_kardex'
    if grupos.intersection(GRUPOS_GERENCIA):
        return 'core:dashboard'

    # 2. Si es superusuario sin grupo específico, respeta el rol elegido en login o va a Gerencia
    if user.is_superuser:
        if rol_seleccionado in RUTA_POR_ROL_ID:
            return RUTA_POR_ROL_ID[rol_seleccionado]
        return 'core:dashboard'

    # 3. Respaldo si la cuenta aún no tiene grupo asignado
    return 'usuarios:inicio'


class LoginPorRolView(LoginRequiredMixin, View):
    """Redirige al usuario autenticado directamente al panel de su rol/grupo."""

    def get(self, request, *args, **kwargs):
        rol_activo = request.session.get('rol_activo')
        destino = obtener_ruta_por_rol(request.user, rol_seleccionado=rol_activo)
        return redirect(destino)


def _claves(request, ident):
    base = f"{ident.strip().lower()}:{request.META.get('REMOTE_ADDR', '')}"
    return f'login_fallos:{base}', f'login_bloqueo:{base}'


def _segundos_bloqueo(clave_bloqueo):
    hasta = cache.get(clave_bloqueo)
    if not hasta:
        return 0
    return max(0, int(hasta - time.time()) + 1)


def _destino(request):
    siguiente = (request.POST.get('next') or request.GET.get('next') or '').strip()
    # Si 'next' viene vacío o apunta a la raíz '/', delegamos a LoginPorRolView
    # para que el usuario vaya al panel correspondiente a su rol/grupo.
    if siguiente and siguiente != '/' and url_has_allowed_host_and_scheme(
        siguiente, allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return siguiente
    return settings.LOGIN_REDIRECT_URL


@never_cache
def login_view(request):
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    form = LoginForm(request.POST or None, request=request)
    bloqueado = 0
    modal_clave = False

    if request.method == 'POST':
        ident = request.POST.get('username', '')
        k_fallos, k_bloqueo = _claves(request, ident)
        bloqueado = _segundos_bloqueo(k_bloqueo)

        if not bloqueado:
            if form.is_valid():
                cache.delete_many([k_fallos, k_bloqueo])
                login(request, form.user)
                request.session['rol_activo'] = form.cleaned_data.get('rol')
                if not form.cleaned_data['recordarme']:
                    request.session.set_expiry(0)  # expira al cerrar el navegador
                return redirect(_destino(request))

            if form.error_tipo == 'credenciales':
                fallos = cache.get(k_fallos, 0) + 1
                cache.set(k_fallos, fallos, VENTANA_FALLOS)
                if fallos >= MAX_INTENTOS:
                    cache.set(k_bloqueo, time.time() + BLOQUEO_SEGUNDOS, BLOQUEO_SEGUNDOS)
                    cache.delete(k_fallos)
                    bloqueado = BLOQUEO_SEGUNDOS
                else:
                    modal_clave = True

    return render(request, 'usuarios/login.html', {
        'form': form,
        'next': request.GET.get('next', ''),
        'bloqueado': bloqueado,
        'modal_clave': modal_clave,
    })


@login_required
def inicio(request):
    return render(request, 'usuarios/inicio.html', {'roles_usuario': roles_de(request.user)})
