"""Aplica únicamente las migraciones previstas al MySQL local del servidor.

Uso, después de respaldar MySQL y actualizar el código:
    sudo -u seleccion /var/www/seleccion/.venv/bin/python \
      /var/www/seleccion/app/deploy/aplicar_migraciones_servidor.py

La clave de seleccion_migracion se solicita sin mostrarla ni ponerla en el historial.
"""

import getpass
import os
import sys
from pathlib import Path
from urllib.parse import quote


PROYECTO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROYECTO))
os.chdir(PROYECTO)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "seleccion_personal.settings")

clave = getpass.getpass("Clave MySQL de seleccion_migracion: ")
if not clave:
    raise SystemExit("No se recibió la clave de migración; no se modificó la base de datos.")
os.environ["DATABASE_URL"] = (
    "mysql://seleccion_migracion:"
    + quote(clave, safe="")
    + "@127.0.0.1:3306/seleccion?charset=utf8mb4"
)
del clave

import django  # noqa: E402

django.setup()

from django.conf import settings  # noqa: E402
from django.contrib.auth import get_user_model  # noqa: E402
from django.core.management import call_command  # noqa: E402
from django.db import connection  # noqa: E402
from django.db.migrations.executor import MigrationExecutor  # noqa: E402


config = settings.DATABASES["default"]
if (
    config["ENGINE"] != "django.db.backends.mysql"
    or config["NAME"] != "seleccion"
    or config["USER"] != "seleccion_migracion"
    or config["HOST"] != "127.0.0.1"
):
    raise SystemExit("Destino MySQL inesperado; no se modificó la base de datos.")

with connection.cursor() as cursor:
    cursor.execute("SELECT DATABASE(), CURRENT_USER()")
    nombre_bd, cuenta_mysql = cursor.fetchone()
if nombre_bd != "seleccion" or not cuenta_mysql.startswith("seleccion_migracion@"):
    raise SystemExit("La conexión MySQL no corresponde a la cuenta de migración esperada.")

ejecutor = MigrationExecutor(connection)
pendientes = [
    (migracion.app_label, migracion.name)
    for migracion, retroceso in ejecutor.migration_plan(ejecutor.loader.graph.leaf_nodes())
    if not retroceso
]
permitidos = (
    [],
    [("procesos", "0016_decision_verificaciones")],
    [
        ("procesos", "0015_separar_vinculacion_contratacion"),
        ("procesos", "0016_decision_verificaciones"),
    ],
)
print("Migraciones pendientes:", pendientes)
if pendientes not in permitidos:
    raise SystemExit("Hay migraciones distintas de las esperadas; no se aplicó ninguna.")
if not pendientes:
    print("Las migraciones ya estaban aplicadas.")
    raise SystemExit(0)

if ("procesos", "0015_separar_vinculacion_contratacion") in pendientes:
    Usuario = get_user_model()
    creador_original = Usuario.objects.filter(
        username__iexact="contratacion", perfil__rol="CONTRATACION"
    ).exists()
    cuenta_vinculacion = Usuario.objects.filter(username__iexact="vinculacion").exists()
    if creador_original and cuenta_vinculacion:
        raise SystemExit(
            "Ya existe otro usuario vinculacion; no se aplicó ninguna migración. "
            "Resuelva esa cuenta antes de continuar."
        )

call_command("migrate", interactive=False, verbosity=1)
print("Migraciones aplicadas en la base de datos seleccion.")
