from django.urls import path
from . import views

app_name = 'obras'

urlpatterns = [
    path('', views.lista_obras, name='lista_obras'),
    path('<int:obra_id>/', views.detalle_obra, name='detalle_obra'),
]