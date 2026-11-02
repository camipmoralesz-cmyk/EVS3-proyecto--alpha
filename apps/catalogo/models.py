from django.db import models

class Categoria(models.Model):
    nombre = models.CharField(max_length=50, unique=True)

    def __str__(self):
        return self.nombre

class Articulo(models.Model):
    UNIDADES_CHOICES = [
        ('UND', 'Unidad'),
        ('MTS', 'Metros'),
        ('CIL', 'Cilindro'),
        ('KG', 'Kilogramo'),
    ]

    codigo_interno = models.CharField(max_length=30, unique=True, verbose_name="Código Interno")
    codigo_barras = models.CharField(max_length=100, unique=True, null=True, blank=True, verbose_name="Código de Barras / QR")
    nombre = models.CharField(max_length=150)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="articulos")
    unidad_medida = models.CharField(max_length=10, choices=UNIDADES_CHOICES, default='UND')
    ubicacion_bodega = models.CharField(max_length=50, help_text="Ej: Pasillo 3 - Estante B")
    
    # Control de Existencias y Umbrales
    stock_actual = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    stock_minimo = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    stock_critico = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    # Costos (ahora como enteros)
    pmp_costo_actual = models.IntegerField(default=0, verbose_name="Precio Medio Ponderado")
    ultimo_costo_compra = models.IntegerField(default=0, verbose_name="Último Costo de Compra")

    def __str__(self):
        return f"[{self.codigo_interno}] {self.nombre}"