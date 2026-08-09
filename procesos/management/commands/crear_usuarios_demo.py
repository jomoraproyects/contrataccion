from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from procesos.models import Perfil


class Command(BaseCommand):
    help = "Crea usuarios de demostración para cada rol"

    def add_arguments(self, parser):
        parser.add_argument("--password", default="DemoSeguro2026!", help="Contraseña para los usuarios demo")

    def handle(self, *args, **options):
        usuarios = {
            "contratacion": Perfil.Rol.CONTRATACION,
            "rrhh": Perfil.Rol.RRHH,
            "psicologia": Perfil.Rol.PSICOLOGIA,
            "seguridad": Perfil.Rol.SEGURIDAD,
            "gerencia": Perfil.Rol.GERENTE,
        }
        for username, rol in usuarios.items():
            usuario, created = User.objects.get_or_create(username=username)
            usuario.set_password(options["password"])
            usuario.first_name = username.title()
            usuario.save()
            usuario.perfil.rol = rol
            usuario.perfil.save()
            estado = "creado" if created else "actualizado"
            self.stdout.write(self.style.SUCCESS(f"{username}: {estado}"))
