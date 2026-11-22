from django.urls import path
from .views import (
    CardexListView,
    AnularMovimientoView,
    BitacoraAuditoriaListView,
    LogsAccesoListView,
    exportar_cardex_excel,
    exportar_cardex_pdf,
)

app_name = 'auditoria'

urlpatterns = [
    path('cardex/', CardexListView.as_view(), name='lista_cardex'),
    path('cardex/anular/', AnularMovimientoView.as_view(), name='anular_movimiento'),
    path('cardex/exportar/excel/', exportar_cardex_excel, name='exportar_cardex_excel'),
    path('cardex/exportar/pdf/', exportar_cardex_pdf, name='exportar_cardex_pdf'),
    path('bitacora/', BitacoraAuditoriaListView.as_view(), name='lista_bitacora'),
    path('accesos/', LogsAccesoListView.as_view(), name='logs_acceso'),
]