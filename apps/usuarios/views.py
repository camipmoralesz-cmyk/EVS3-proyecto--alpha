import time

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache

from .forms import LoginForm
from .roles import roles_de

MAX_INTENTOS = 3          # fallos seguidos antes de bloquear
BLOQUEO_SEGUNDOS = 30     # duración del bloqueo (súbelo en producción)
VENTANA_FALLOS = 15 * 60  # los fallos se olvidan tras 15 min sin intentos


def _claves(request, ident):
    base = f"{ident.strip().lower()}:{request.META.get('REMOTE_ADDR', '')}"
    return f'login_fallos:{base}', f'login_bloqueo:{base}'


def _segundos_bloqueo(clave_bloqueo):
    hasta = cache.get(clave_bloqueo)
    if not hasta:
        return 0
    return max(0, int(hasta - time.time()) + 1)


def _destino(request):
    siguiente = request.POST.get('next') or request.GET.get('next') or ''
    if siguiente and url_has_allowed_host_and_scheme(
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
