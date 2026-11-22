from django.urls import path
from . import views

app_name = 'obras'

urlpatterns = [
    path('', views.lista_obras, name='lista_obras'),
    path('<int:obra_id>/', views.detalle_obra, name='detalle_obra'),
    path('solicitudes/', views.lista_solicitudes, name='lista_solicitudes'),
    path('hojas-servicio/', views.lista_hojas_servicio, name='lista_hojas_servicio'),
    path('inventario-lectura/', views.kardex_lectura, name='kardex_lectura'),
    path('crear/', views.crear_obra, name='crear_obra'),
    path('<int:pk>/', views.detalle_obra, name='detalle_obra'),
    path('<int:pk>/editar/', views.editar_obra, name='editar_obra'),
]