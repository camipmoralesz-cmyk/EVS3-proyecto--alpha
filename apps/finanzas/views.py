from django.shortcuts import render
from apps.usuarios.roles import rol_requerido


@rol_requerido('finanzas')
def panel_finanzas(request):
    """Vista de inicio del módulo de Finanzas (protegida por rol finanzas)."""
    return render(request, 'finanzas/panel.html', {
        'titulo': 'Panel de Finanzas',
    })
