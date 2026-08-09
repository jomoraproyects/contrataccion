from django.db import migrations, models


def convertir_admin_en_gerente(apps, schema_editor):
    Perfil = apps.get_model("procesos", "Perfil")
    Perfil.objects.filter(rol="ADMIN").update(rol="GERENTE")


def restaurar_admin(apps, schema_editor):
    Perfil = apps.get_model("procesos", "Perfil")
    Perfil.objects.filter(rol="GERENTE").update(rol="ADMIN")


class Migration(migrations.Migration):
    dependencies = [("procesos", "0001_initial")]

    operations = [
        migrations.RunPython(convertir_admin_en_gerente, restaurar_admin),
        migrations.AlterField(
            model_name="perfil",
            name="rol",
            field=models.CharField(
                choices=[
                    ("SIN_ASIGNAR", "Sin acceso asignado"),
                    ("CONTRATACION", "Contratación"),
                    ("RRHH", "Recursos Humanos"),
                    ("PSICOLOGIA", "Psicología"),
                    ("SEGURIDAD", "Seguridad ocupacional"),
                    ("GERENTE", "Gerente"),
                ],
                default="SIN_ASIGNAR",
                max_length=20,
            ),
        ),
    ]
