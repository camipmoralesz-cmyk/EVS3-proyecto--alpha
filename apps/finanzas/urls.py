from django.urls import path
from . import views

app_name = 'finanzas'

urlpatterns = [
    path('', views.panel_finanzas, name='panel'),
    path('facturas/', views.lista_facturas_finanzas, name='facturas_lista'),
    path('facturas/nueva/', views.crear_factura_borrador_finanzas, name='factura_crear'),
    path('facturas/<int:pk>/', views.detalle_factura_finanzas, name='factura_detalle'),
    path('facturas/<int:pk>/editar/', views.editar_factura_borrador_finanzas, name='factura_editar'),
    path('facturas/<int:pk>/eliminar/', views.eliminar_factura_borrador_finanzas, name='factura_eliminar'),
    path('pagos/', views.lista_pagos_finanzas, name='pagos_lista'),
    path('pagos/nuevo/', views.crear_pago_finanzas, name='pago_crear'),
    path('pagos/<int:pk>/editar/', views.editar_pago_finanzas, name='pago_editar'),
    path('pagos/<int:pk>/eliminar/', views.eliminar_pago_finanzas, name='pago_eliminar'),
    path('entidades/', views.lista_entidades_finanzas, name='entidades_lista'),
    path('entidades/nueva/', views.crear_entidad_finanzas, name='entidad_crear'),
    path('entidades/<int:pk>/editar/', views.editar_entidad_finanzas, name='entidad_editar'),
    path('entidades/<int:pk>/estado/', views.cambiar_estado_entidad_finanzas, name='entidad_cambiar_estado'),
    path('entidades/<int:pk>/eliminar/', views.eliminar_entidad_finanzas, name='entidad_eliminar'),
    path('presupuestos/', views.lista_presupuestos_finanzas, name='presupuestos_lista'),
    path('presupuestos/nueva-obra/', views.crear_obra_finanzas, name='obra_crear'),
    path('presupuestos/<int:pk>/editar/', views.editar_presupuesto_finanzas, name='presupuesto_editar'),
    path('presupuestos/<int:pk>/eliminar/', views.eliminar_presupuesto_finanzas, name='presupuesto_eliminar'),
]
