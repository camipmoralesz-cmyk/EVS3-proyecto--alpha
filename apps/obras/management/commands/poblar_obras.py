from django.core.management.base import BaseCommand
from django.contrib.auth.models import User, Group
from apps.catalogo.models import Articulo, Categoria  # <--- Importamos Categoria
from apps.entidades.models import Proveedor
from apps.obras.models import Obra, SolicitudMaterialObra

class Command(BaseCommand):
    help = 'Pobla la base de datos de PostgreSQL con datos corporativos de prueba para Obras y Supervisor'

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('--- INICIANDO CARGA DE DATOS DE PRUEBA (OBRAS) ---'))

        # 1. Crear Grupos y Roles
        admin_group, _ = Group.objects.get_or_create(name='Administrador General')
        supervisor_group, _ = Group.objects.get_or_create(name='Supervisor de Obra')

        # 2. Crear usuarios de prueba
        admin_user, _ = User.objects.get_or_create(
            username='camila_admin', 
            defaults={'first_name': 'Camila', 'last_name': 'Morales', 'is_staff': True, 'is_superuser': True}
        )
        admin_user.set_password('admin123')
        admin_user.save()
        admin_user.groups.add(admin_group)

        sup_user, _ = User.objects.get_or_create(
            username='supervisor1', 
            defaults={'first_name': 'Carlos', 'last_name': 'Terreno', 'is_staff': False}
        )
        sup_user.set_password('sup123')
        sup_user.save()
        sup_user.groups.add(supervisor_group)

        # 3. Crear Proveedor / Mandante
        mandante_prueba, _ = Proveedor.objects.get_or_create(
            rut='76.543.210-K',
            defaults={
                'razon_social': 'Agroindustrial del Ñuble SpA',
                'tipo': 'MANDANTE',
                'activo': True,
                'email': 'contacto@agroindustrialnuble.cl'
            }
        )

        # 4. Crear Categoría obligatoria para el catálogo
        categoria_ref, _ = Categoria.objects.get_or_create(
            nombre='Refrigeración Industrial'
        )

        # 5. Crear Artículos de prueba vinculados a la categoría
        art1, _ = Articulo.objects.get_or_create(
            codigo_interno='REF-001', 
            defaults={
                'nombre': 'Compresor Semihermético Bitzer', 
                'categoria': categoria_ref,
                'stock_actual': 1, 
                'stock_minimo': 3
            }
        )
        art2, _ = Articulo.objects.get_or_create(
            codigo_interno='TUB-042', 
            defaults={
                'nombre': 'Cañería Cobre 3/8 Pulgada', 
                'categoria': categoria_ref,
                'stock_actual': 25, 
                'stock_minimo': 10
            }
        )
        art3, _ = Articulo.objects.get_or_create(
            codigo_interno='GAS-R404', 
            defaults={
                'nombre': 'Gas Refrigerante R-404A (Cilindro 10kg)', 
                'categoria': categoria_ref,
                'stock_actual': 0, 
                'stock_minimo': 2
            }
        )

        # 6. Crear Obra usando el modelo de tus compañeros
        obra_prueba, _ = Obra.objects.get_or_create(
            nombre='Instalación Cámara de Frío Planta Chillán Viejo',
            defaults={
                'mandante': mandante_prueba,
                'presupuesto_total': 15500000.00,
                'estado': Obra.Estado.ACTIVA
            }
        )

        # 7. Crear Solicitud de Material pendiente
        SolicitudMaterialObra.objects.get_or_create(
            obra=obra_prueba,
            articulo=art3,
            defaults={
                'cantidad': 2,
                'estado': SolicitudMaterialObra.EstadoSolicitud.PENDIENTE,
                'solicitado_por': sup_user
            }
        )

        self.stdout.write(self.style.SUCCESS('--- ¡DATOS DE PRUEBA CARGADOS EXITOSAMENTE DESDE LA APP OBRAS! ---'))