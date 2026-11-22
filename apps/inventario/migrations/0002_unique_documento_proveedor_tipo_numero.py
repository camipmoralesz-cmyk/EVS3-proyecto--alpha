from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('inventario', '0001_initial'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='documentoentrada',
            constraint=models.UniqueConstraint(
                fields=('proveedor', 'tipo_documento', 'numero_documento'),
                name='uniq_documento_proveedor_tipo_numero',
            ),
        ),
    ]
