from django.urls import path
from . import views

urlpatterns = [
    path('documentos/', views.lista_documentos, name='lista_documentos'),
    path('documentos/nuevo/', views.registro_documento, name='registro_documento'),
    path('documentos/<int:pk>/', views.detalle_documento, name='detalle_documento'),
    path('stock/', views.inventario_stock, name='inventario_stock'),
    path('movimientos/', views.historial_movimientos, name='historial_movimientos'),
    path('api/articulo/<int:pk>/', views.api_articulo_info, name='api_articulo_info'),
]

