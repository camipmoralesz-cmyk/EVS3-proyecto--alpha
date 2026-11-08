#a ruta para acceder al módulo de anulación
from django.urls import path
from .views import AnularMovimientoView, ListaCardexView

app_name = 'auditoria'

urlpatterns = [
    path('cardex/', ListaCardexView.as_view(), name='lista_cardex'),
    path('anular/', AnularMovimientoView.as_view(), name='anular_movimiento'),
]