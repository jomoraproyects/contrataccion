from django.conf import settings
from django.db import migrations, models


def conservar_cuentas_creadoras_como_vinculacion(apps, schema_editor):
    """Cambia el rol y el usuario de acceso original sin tocar la contraseña."""
    Perfil = apps.get_model("procesos", "Perfil")
    User = apps.get_model(settings.AUTH_USER_MODEL)
    alias = schema_editor.connection.alias
    creadores = Perfil.objects.using(alias).filter(rol="CONTRATACION")
    ids_creadores = list(creadores.values_list("usuario_id", flat=True))
    cuenta_original = User.objects.using(alias).filter(
        pk__in=ids_creadores, username__iexact="contratacion",
    ).first()

    if cuenta_original and User.objects.using(alias).filter(
        username__iexact="vinculacion",
    ).exclude(pk=cuenta_original.pk).exists():
        raise RuntimeError(
            "Ya existe el usuario vinculacion. Resuelva esa cuenta antes de aplicar la migración."
        )

    creadores.update(rol="VINCULACION")
    if cuenta_original:
        User.objects.using(alias).filter(pk=cuenta_original.pk).update(username="vinculacion")


class Migration(migrations.Migration):
    dependencies = [("procesos", "0014_limitar_observacion_decision")]

    operations = [
        migrations.AlterField(
            model_name="perfil",
            name="rol",
            field=models.CharField(
                choices=[
                    ("SIN_ASIGNAR", "Sin acceso asignado"),
                    ("VINCULACION", "Vinculación"),
                    ("CONTRATACION", "Contratación"),
                    ("RRHH", "Talento Humano"),
                    ("PSICOLOGIA", "Psicología"),
                    ("SEGURIDAD", "Seguridad y Salud en el Trabajo"),
                    ("GERENTE", "Gerente"),
                ],
                db_index=True,
                default="SIN_ASIGNAR",
                max_length=20,
            ),
        ),
        # No se revierte automáticamente: después pueden existir cuentas finales
        # de Contratación que no deben confundirse con las creadoras originales.
        migrations.RunPython(conservar_cuentas_creadoras_como_vinculacion),
    ]
