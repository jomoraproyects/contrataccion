from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("procesos", "0013_candidato_unico_y_horario_laboral"),
    ]

    operations = [
        migrations.AlterField(
            model_name="decision",
            name="observacion",
            field=models.TextField(max_length=2000),
        ),
    ]
