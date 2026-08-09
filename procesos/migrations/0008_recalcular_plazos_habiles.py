from django.db import migrations


def recalcular_plazos(apps, schema_editor):
    from procesos.calendario import sumar_dias_habiles

    SeguimientoEtapa = apps.get_model("procesos", "SeguimientoEtapa")
    plazos = {"RRHH": 2, "PSICOLOGIA": 3, "SEGURIDAD": 6, "CONTRATACION": 2}
    for seguimiento in SeguimientoEtapa.objects.all().iterator():
        seguimiento.fecha_limite = sumar_dias_habiles(
            seguimiento.inicio,
            plazos[seguimiento.etapa],
        )
        seguimiento.save(update_fields=["fecha_limite"])


class Migration(migrations.Migration):
    dependencies = [("procesos", "0007_seguimientoetapa_segundos_pausados")]

    operations = [migrations.RunPython(recalcular_plazos, migrations.RunPython.noop)]
