from django.urls import path
from . import views

urlpatterns = [
    path('', views.lista_articulos, name='lista_articulos'),
    path('nuevo/', views.crear_articulo, name='crear_articulo'),
    path('categorias/nueva/', views.crear_categoria, name='crear_categoria'),
    path('<int:pk>/editar/', views.editar_articulo, name='editar_articulo'),
    path('<int:pk>/estado/', views.cambiar_estado_articulo, name='cambiar_estado_articulo'),
]
