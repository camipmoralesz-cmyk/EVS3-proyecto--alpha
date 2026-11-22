import django.db.models.deletion
from decimal import Decimal
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0002_alter_articulo_pmp_costo_actual_and_more'),
        ('inventario', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='movimientoinventario',
            name='articulo',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='movimientos_inventario',
                to='catalogo.articulo',
                verbose_name='Artículo',
            ),
        ),
        migrations.AlterField(
            model_name='movimientoinventario',
            name='cantidad',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=10,
                verbose_name='Cantidad',
            ),
        ),
        migrations.AlterField(
            model_name='movimientoinventario',
            name='costo_unitario',
            field=models.IntegerField(
                default=0,
                verbose_name='Costo Unitario Aplicado',
            ),
        ),
        migrations.AlterField(
            model_name='movimientoinventario',
            name='referencia',
            field=models.CharField(
                blank=True,
                max_length=255,
                verbose_name='Referencia / Motivo',
            ),
        ),
        migrations.AlterField(
            model_name='movimientoinventario',
            name='stock_anterior',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=10,
                verbose_name='Stock Anterior',
            ),
        ),
        migrations.AlterField(
            model_name='movimientoinventario',
            name='stock_posterior',
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal('0.00'),
                max_digits=10,
                verbose_name='Stock Posterior',
            ),
        ),
        migrations.AlterField(
            model_name='movimientoinventario',
            name='tipo_movimiento',
            field=models.CharField(
                choices=[
                    ('ENTRADA', 'Ingreso de Materiales'),
                    ('SALIDA', 'Salida de Materiales'),
                    ('AJUSTE', 'Ajuste de Inventario'),
                    ('ANULACION', 'Contra-Asiento / Anulación'),
                    ('INGRESO_SISTEMA', 'Ingreso de Personal al Sistema'),
                    ('SALIDA_SISTEMA', 'Salida de Personal del Sistema'),
                ],
                max_length=25,
                verbose_name='Tipo de Movimiento',
            ),
        ),
    ]
