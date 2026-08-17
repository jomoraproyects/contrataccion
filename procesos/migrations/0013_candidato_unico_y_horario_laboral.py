from django.db import migrations, models
import django.db.models.deletion


def crear_identidades_y_recalcular(apps, schema_editor):
    from procesos.calendario import sumar_dias_habiles, sumar_segundos_habiles

    Candidato = apps.get_model("procesos", "Candidato")
    ProcesoSeleccion = apps.get_model("procesos", "ProcesoSeleccion")
    SeguimientoEtapa = apps.get_model("procesos", "SeguimientoEtapa")
    plazos = {"RRHH": 2, "PSICOLOGIA": 3, "SEGURIDAD": 6, "CONTRATACION": 2}

    for proceso in ProcesoSeleccion.objects.order_by("creado_en", "pk").iterator():
        candidato, creado = Candidato.objects.get_or_create(
            cedula=proceso.cedula,
            defaults={
                "nombre": proceso.nombre,
                "apellidos": proceso.apellidos,
                "celular": proceso.celular,
            },
        )
        if not creado:
            candidato.nombre = proceso.nombre
            candidato.apellidos = proceso.apellidos
            candidato.celular = proceso.celular
            candidato.save(update_fields=["nombre", "apellidos", "celular", "actualizado_en"])
        proceso.candidato_id = candidato.pk
        proceso.save(update_fields=["candidato"])

    for seguimiento in SeguimientoEtapa.objects.all().iterator():
        limite = sumar_dias_habiles(seguimiento.inicio, plazos[seguimiento.etapa])
        if seguimiento.segundos_pausados:
            limite = sumar_segundos_habiles(limite, seguimiento.segundos_pausados)
        seguimiento.fecha_limite = limite
        seguimiento.save(update_fields=["fecha_limite"])


def desvincular_identidades(apps, schema_editor):
    apps.get_model("procesos", "ProcesoSeleccion").objects.update(candidato=None)
    apps.get_model("procesos", "Candidato").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("procesos", "0012_reforzar_restricciones_mysql"),
    ]

    operations = [
        migrations.CreateModel(
            name="Candidato",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nombre", models.CharField(max_length=100)),
                ("apellidos", models.CharField(max_length=120)),
                ("cedula", models.CharField(max_length=30, unique=True, verbose_name="número de cédula")),
                ("celular", models.CharField(max_length=30, verbose_name="número de celular")),
                ("creado_en", models.DateTimeField(auto_now_add=True)),
                ("actualizado_en", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["nombre", "apellidos"]},
        ),
        migrations.AddField(
            model_name="procesoseleccion",
            name="candidato",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="procesos",
                to="procesos.candidato",
            ),
        ),
        migrations.RunPython(crear_identidades_y_recalcular, desvincular_identidades),
        migrations.AlterField(
            model_name="procesoseleccion",
            name="candidato",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="procesos",
                to="procesos.candidato",
            ),
        ),
    ]
