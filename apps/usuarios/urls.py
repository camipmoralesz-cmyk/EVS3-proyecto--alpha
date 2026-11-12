from django.contrib.auth.views import LogoutView
from django.urls import path

from . import views

app_name = 'usuarios'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),  # solo acepta POST
    path('inicio/', views.inicio, name='inicio'),
]
