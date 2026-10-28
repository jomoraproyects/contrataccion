from copy import copy
from getpass import getpass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import (
    MinimumLengthValidator, get_default_password_validators, validate_password,
)
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from procesos.models import Perfil


class Command(BaseCommand):
    help = "Crea la cuenta final contratacion sin modificar Vinculación ni cuentas existentes."

    def add_arguments(self, parser):
        parser.add_argument(
            "--permitir-clave-inicial-11", action="store_true",
            help="Permite 11 caracteres solo para esta cuenta inicial; no cambia la política general.",
        )
        parser.add_argument(
            "--exigir-mysql", action="store_true",
            help="Aborta si la base configurada no es el MySQL seleccion del servidor.",
        )

    def handle(self, *args, **options):
        if options["exigir_mysql"] and (
            connection.vendor != "mysql" or settings.DATABASES["default"]["NAME"] != "seleccion"
        ):
            raise CommandError("No está configurado el MySQL seleccion; no se creó ninguna cuenta.")
        Usuario = get_user_model()
        existente = Usuario.objects.filter(username__iexact="contratacion").first()
        if existente:
            if existente.perfil.rol != Perfil.Rol.CONTRATACION:
                raise CommandError("El usuario contratacion ya existe con otro rol; no se modificó.")
            self.stdout.write("La cuenta contratacion ya existe. No se cambió su contraseña ni estado.")
            return
        clave = getpass("Contraseña de la nueva cuenta contratacion: ")
        if clave != getpass("Confirme la contraseña: "):
            raise CommandError("Las contraseñas no coinciden; no se creó ninguna cuenta.")
        usuario = Usuario(username="contratacion", first_name="Contratación")
        validadores = [copy(validador) for validador in get_default_password_validators()]
        if options["permitir_clave_inicial_11"]:
            for validador in validadores:
                if isinstance(validador, MinimumLengthValidator):
                    validador.min_length = 11
        try:
            validate_password(clave, usuario, password_validators=validadores)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages)) from exc
        with transaction.atomic():
            usuario.set_password(clave)
            usuario.save()
            perfil, _ = Perfil.objects.get_or_create(usuario=usuario)
            perfil.rol = Perfil.Rol.CONTRATACION
            perfil.save(update_fields=["rol"])
        self.stdout.write(self.style.SUCCESS(
            "Cuenta contratacion creada. Atiende únicamente la etapa final posterior a SST."
        ))
