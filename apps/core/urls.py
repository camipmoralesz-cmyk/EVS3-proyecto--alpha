from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('usuarios/', views.gestion_usuarios, name='gestion_usuarios'),
    path('alertas-stock/', views.panel_alertas_stock, name='alertas_stock'),
    path('auditoria/', views.auditoria_kardex, name='auditoria_kardex'),
    path('auditoria/anular/<int:mov_id>/', views.anular_movimiento_kardex, name='anular_movimiento'),
    path('aprobaciones/', views.aprobacion_inventarios, name='aprobacion_inventarios'),
    path('consulta/<str:seccion>/', views.consulta_lectura, name='consulta_lectura'),
]