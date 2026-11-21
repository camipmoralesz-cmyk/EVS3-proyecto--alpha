from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('apps.core.urls')),
    path('catalogo/', include('apps.catalogo.urls')),
    path('entidades/', include('apps.entidades.urls')),
    path('inventario/', include('apps.inventario.urls')),
    path('cuentas/', include('apps.usuarios.urls')),
]
