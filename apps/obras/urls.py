from django.urls import path
from . import views

app_name = 'obras'

urlpatterns = [
    path('', views.lista_obras, name='lista_obras'),
    path('crear/', views.crear_obra, name='crear_obra'),
    path('<int:pk>/', views.detalle_obra, name='detalle_obra'),
    path('<int:pk>/editar/', views.editar_obra, name='editar_obra'),
]