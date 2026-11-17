from django.urls import path
from . import views

app_name = 'finanzas'

urlpatterns = [
    path('', views.panel_finanzas, name='panel'),
]
