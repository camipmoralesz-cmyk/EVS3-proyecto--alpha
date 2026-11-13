from django.urls import path
from . import views

app_name = 'obras'

urlpatterns = [
    path('', views.despachos, name='despachos'),
]