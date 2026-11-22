from django.urls import path
from . import views, views_bodega

urlpatterns = [
    path('documentos/', views.lista_documentos, name='lista_documentos'),
    path('documentos/nuevo/', views.registro_documento, name='registro_documento'),
    path('documentos/<int:pk>/', views.detalle_documento, name='detalle_documento'),
    path('stock/', views.inventario_stock, name='inventario_stock'),
    path('movimientos/', views.historial_movimientos, name='historial_movimientos'),
    path('api/articulo/<int:pk>/', views.api_articulo_info, name='api_articulo_info'),

    # Despachos a obra (HU-02)
    path('despachos/', views_bodega.lista_solicitudes, name='lista_solicitudes'),
    path('despachos/<int:pk>/despachar/', views_bodega.despachar_solicitud, name='despachar_solicitud'),
    path('despachos/<int:pk>/rechazar/', views_bodega.rechazar_solicitud_view, name='rechazar_solicitud'),
    path('despachos/vale/<int:pk>/', views_bodega.comprobante_despacho, name='comprobante_despacho'),

    # Merma, devoluciones y uso interno (HU-04)
    path('salidas/', views_bodega.salida_tipificada, name='salida_tipificada'),

    # Inventario físico por sector (HU-05)
    path('inventario-fisico/', views_bodega.lista_sesiones_inventario, name='lista_sesiones_inventario'),
    path('inventario-fisico/<int:pk>/', views_bodega.detalle_sesion_inventario, name='detalle_sesion_inventario'),
    path('inventario-fisico/<int:pk>/exportar/', views_bodega.exportar_sesion_inventario, name='exportar_sesion_inventario'),
]
