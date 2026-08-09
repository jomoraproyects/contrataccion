from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("procesos", "0002_rol_gerente")]

    operations = [
        migrations.AddField(
            model_name="perfil",
            name="intentos_fallidos",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="perfil",
            name="bloqueado_hasta",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
