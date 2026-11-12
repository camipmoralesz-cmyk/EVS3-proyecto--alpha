from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [

    path('', include('apps.core.urls')),
    path('admin/', admin.site.urls),
    path('', lambda request: redirect('inventario_stock'), name='home'),
    path('catalogo/', include('apps.catalogo.urls')),
    path('inventario/', include('apps.inventario.urls')),
]
