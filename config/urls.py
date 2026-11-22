from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('', include('apps.core.urls')),
    path('admin/', admin.site.urls),
    path('catalogo/', include('apps.catalogo.urls')),
    path('entidades/', include('apps.entidades.urls')),
    path('inventario/', include('apps.inventario.urls')),
    path('obras/', include('apps.obras.urls')),
    path('cuentas/', include('apps.usuarios.urls')),
    path('finanzas/', include('apps.finanzas.urls')),
    path('auditoria/', include('apps.auditoria.urls')),
]