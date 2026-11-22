from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('obras', '0006_obra_numero_presupuesto_obra_tecnico_responsable_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='solicitudmaterialobra',
            name='observaciones',
            field=models.TextField(blank=True, default='', verbose_name='Observaciones / Motivo'),
        ),
    ]
    