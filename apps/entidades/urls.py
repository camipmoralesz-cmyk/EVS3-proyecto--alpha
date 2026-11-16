from django.urls import path

from . import views

urlpatterns = [
    path('', views.lista_entidades, name='lista_entidades'),
    path('nueva/', views.crear_entidad, name='crear_entidad'),
    path('<int:pk>/editar/', views.editar_entidad, name='editar_entidad'),
    path('<int:pk>/estado/', views.cambiar_estado_entidad, name='cambiar_estado_entidad'),
]

