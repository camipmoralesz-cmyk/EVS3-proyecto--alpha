from django.urls import path
from . import views

app_name = 'entidades'

urlpatterns = [
    path('', views.lista_entidades, name='lista_entidades'),
]