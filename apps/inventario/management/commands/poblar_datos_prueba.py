from django.core.management.base import BaseCommand
from decimal import Decimal
from apps.catalogo.models import Categoria, Articulo
from apps.entidades.models import Proveedor

class Command(BaseCommand):
    help = 'Puebla la base de datos con proveedores, categorías y artículos de prueba para HU-01'

    def handle(self, *args, **options):
        self.stdout.write("Creando proveedores de prueba...")
        prov1, _ = Proveedor.objects.get_or_create(
            rut="76.123.456-7",
            defaults={
                'razon_social': 'Comercializadora Industrial y Eléctrica SpA',
                'nombre_fantasia': 'ElectroIndustrial',
                'giro': 'Venta por mayor de materiales eléctricos y construcción',
                'telefono': '+56 9 8765 4321',
                'email': 'ventas@electroindustrial.cl',
                'direccion': 'Av. Matta 1234, Santiago',
                'activo': True
            }
        )
        prov2, _ = Proveedor.objects.get_or_create(
            rut="77.987.654-3",
            defaults={
                'razon_social': 'Ferretería y Aceros del Sur Ltda.',
                'nombre_fantasia': 'Aceros del Sur',
                'giro': 'Distribuidora de aceros, perfiles y fijaciones',
                'telefono': '+56 2 2345 6789',
                'email': 'contacto@acerosdelsur.cl',
                'direccion': 'Camino Melipilla 9800, Maipú',
                'activo': True
            }
        )

        self.stdout.write("Creando categorías...")
        cat_elec, _ = Categoria.objects.get_or_create(nombre="Electricidad y Canalización")
        cat_ferr, _ = Categoria.objects.get_or_create(nombre="Ferretería y Fijaciones")
        cat_tubo, _ = Categoria.objects.get_or_create(nombre="Tuberías y Cañerías")

        self.stdout.write("Creando artículos de prueba...")
        articulos_datos = [
            {
                'codigo_interno': 'CBL-001',
                'codigo_barras': '7801234567890',
                'nombre': 'Cable de Cobre THHN 2.5 mm² Rojo',
                'categoria': cat_elec,
                'unidad_medida': 'MTS',
                'ubicacion_bodega': 'Pasillo 1 - Estante A',
                'stock_actual': Decimal('120.00'),
                'stock_minimo': Decimal('50.00'),
                'stock_critico': Decimal('20.00'),
                'pmp_costo_actual': 850,
                'ultimo_costo_compra': 850
            },
            {
                'codigo_interno': 'DIS-016',
                'codigo_barras': '7801234567891',
                'nombre': 'Disyuntor Termomagnético 1x16A Curva C',
                'categoria': cat_elec,
                'unidad_medida': 'UND',
                'ubicacion_bodega': 'Pasillo 1 - Estante B',
                'stock_actual': Decimal('35.00'),
                'stock_minimo': Decimal('20.00'),
                'stock_critico': Decimal('10.00'),
                'pmp_costo_actual': 3200,
                'ultimo_costo_compra': 3200
            },
            {
                'codigo_interno': 'PER-008',
                'codigo_barras': '7801234567892',
                'nombre': 'Perno Coche Zincado 3/8 x 3"',
                'categoria': cat_ferr,
                'unidad_medida': 'UND',
                'ubicacion_bodega': 'Pasillo 2 - Estante C',
                'stock_actual': Decimal('300.00'),
                'stock_minimo': Decimal('100.00'),
                'stock_critico': Decimal('50.00'),
                'pmp_costo_actual': 280,
                'ultimo_costo_compra': 280
            },
            {
                'codigo_interno': 'TUB-025',
                'codigo_barras': '7801234567893',
                'nombre': 'Tubo Conduit PVC 25mm x 3m',
                'categoria': cat_tubo,
                'unidad_medida': 'UND',
                'ubicacion_bodega': 'Patio Bodega - Racks Tubos',
                'stock_actual': Decimal('8.00'),
                'stock_minimo': Decimal('25.00'),
                'stock_critico': Decimal('10.00'),
                'pmp_costo_actual': 2100,
                'ultimo_costo_compra': 2100
            },
        ]

        for item in articulos_datos:
            Articulo.objects.get_or_create(
                codigo_interno=item['codigo_interno'],
                defaults=item
            )

        self.stdout.write(self.style.SUCCESS('¡Datos de prueba cargados exitosamente!'))

