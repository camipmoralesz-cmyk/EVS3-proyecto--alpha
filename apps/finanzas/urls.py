from django.urls import path
from . import views

app_name = 'finanzas'

urlpatterns = [
    path('', views.panel_finanzas, name='panel'),
    path('entidades/', views.lista_entidades_finanzas, name='entidades_lista'),
    path('entidades/nueva/', views.crear_entidad_finanzas, name='entidad_crear'),
    path('entidades/<int:pk>/editar/', views.editar_entidad_finanzas, name='entidad_editar'),
    path('entidades/<int:pk>/estado/', views.cambiar_estado_entidad_finanzas, name='entidad_cambiar_estado'),
    path('entidades/<int:pk>/eliminar/', views.eliminar_entidad_finanzas, name='entidad_eliminar'),
    path('presupuestos/', views.lista_presupuestos_finanzas, name='presupuestos_lista'),
    path('presupuestos/<int:pk>/editar/', views.editar_presupuesto_finanzas, name='presupuesto_editar'),
    path('presupuestos/<int:pk>/eliminar/', views.eliminar_presupuesto_finanzas, name='presupuesto_eliminar'),
]
