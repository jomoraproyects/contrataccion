from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from procesos.models import Perfil


class Command(BaseCommand):
    help = "Crea usuarios de demostración para cada rol"

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="Contraseña temporal para los usuarios demo")

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Este comando de demostración está deshabilitado en producción.")
        try:
            validate_password(options["password"])
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
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
