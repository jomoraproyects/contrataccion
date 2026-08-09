from getpass import getpass

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from procesos.models import Perfil


class Command(BaseCommand):
    help = "Crea o actualiza la cuenta principal de Gerente solicitando la contraseña de forma segura"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="gerencia")
        parser.add_argument("--nombre", default="Gerencia")
        parser.add_argument("--apellidos", default="")

    def handle(self, *args, **options):
        username = options["username"].strip().lower()
        if not username:
            raise CommandError("El nombre de usuario es obligatorio.")
        password = getpass("Nueva contraseña del Gerente: ")
        confirmacion = getpass("Confirme la contraseña: ")
        if password != confirmacion:
            raise CommandError("Las contraseñas no coinciden.")

        usuario, creado = User.objects.get_or_create(username=username)
        try:
            validate_password(password, usuario)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc

        usuario.first_name = options["nombre"].strip()
        usuario.last_name = options["apellidos"].strip()
        usuario.is_active = True
        usuario.is_staff = False
        usuario.is_superuser = False
        usuario.set_password(password)
        usuario.save()
        usuario.perfil.rol = Perfil.Rol.GERENTE
        usuario.perfil.save(update_fields=["rol"])
        accion = "creada" if creado else "actualizada"
        self.stdout.write(self.style.SUCCESS(f"Cuenta de Gerente {accion}: {username}"))
