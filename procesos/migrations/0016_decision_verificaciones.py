from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("procesos", "0015_separar_vinculacion_contratacion")]

    operations = [
        migrations.AddField(
            model_name="decision",
            name="verificaciones",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
