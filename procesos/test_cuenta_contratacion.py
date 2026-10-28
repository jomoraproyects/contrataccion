from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import UsuarioOperativoForm
from .models import Perfil


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CuentaContratacionTests(TestCase):
    def setUp(self):
        self.gerente = User.objects.create_user("gerencia")
        self.gerente.perfil.rol = Perfil.Rol.GERENTE
        self.gerente.perfil.save()
        self.vinculacion = User.objects.create_user("vinculacion", password="OriginalNoCambiar2026!")
        self.vinculacion.perfil.rol = Perfil.Rol.VINCULACION
        self.vinculacion.perfil.save()

    def test_ambos_roles_estan_disponibles_en_orden_del_flujo(self):
        self.assertEqual(list(UsuarioOperativoForm().fields["rol"].choices), [
            ("VINCULACION", "Vinculación"), ("RRHH", "Talento Humano"),
            ("PSICOLOGIA", "Psicología"), ("SEGURIDAD", "Seguridad y Salud en el Trabajo"),
            ("CONTRATACION", "Contratación"),
        ])

    def test_acceso_directo_fija_contratacion_y_no_acepta_otro_rol(self):
        self.client.force_login(self.gerente)
        url = reverse("procesos:usuario_crear_contratacion")
        respuesta = self.client.get(url)
        self.assertContains(respuesta, "Etapa final después de SST")
        self.assertTrue(respuesta.context["form"].fields["rol"].disabled)
        respuesta = self.client.post(url, {
            "username": "contratacion", "first_name": "Cuenta", "last_name": "Final",
            "rol": "VINCULACION", "password1": "ClaveFinalSegura2026!",
            "password2": "ClaveFinalSegura2026!",
        })
        self.assertRedirects(respuesta, reverse("procesos:usuarios"))
        self.assertEqual(User.objects.get(username="contratacion").perfil.rol, "CONTRATACION")
        self.vinculacion.refresh_from_db()
        self.assertTrue(self.vinculacion.check_password("OriginalNoCambiar2026!"))

    def test_otra_area_no_puede_usar_el_acceso_directo(self):
        self.client.force_login(self.vinculacion)
        self.assertEqual(self.client.get(reverse("procesos:usuario_crear_contratacion")).status_code, 403)

    def test_comando_crea_una_sola_cuenta_y_no_restablece_claves(self):
        with patch("procesos.management.commands.crear_contratacion.getpass", return_value="ClaveFinalSegura2026!"):
            call_command("crear_contratacion", stdout=StringIO())
        usuario = User.objects.get(username="contratacion")
        self.assertEqual(usuario.perfil.rol, Perfil.Rol.CONTRATACION)
        self.assertTrue(usuario.check_password("ClaveFinalSegura2026!"))
        with patch("procesos.management.commands.crear_contratacion.getpass") as entrada:
            call_command("crear_contratacion", stdout=StringIO())
            entrada.assert_not_called()
        self.assertEqual(User.objects.filter(username="contratacion").count(), 1)

    def test_clave_corta_no_crea_cuentas_incompletas(self):
        with patch("procesos.management.commands.crear_contratacion.getpass", return_value="corta"):
            with self.assertRaises(CommandError):
                call_command("crear_contratacion", stdout=StringIO())
        self.assertFalse(User.objects.filter(username="contratacion").exists())

    def test_excepcion_inicial_11_no_cambia_politica_general(self):
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        clave_prueba = "SolRio2026!"
        with patch("procesos.management.commands.crear_contratacion.getpass", return_value=clave_prueba):
            call_command("crear_contratacion", permitir_clave_inicial_11=True, stdout=StringIO())
        self.assertTrue(User.objects.get(username="contratacion").check_password(clave_prueba))
        with self.assertRaises(ValidationError):
            validate_password(clave_prueba)

    def test_equipo_sigue_el_orden_del_flujo(self):
        for rol in (Perfil.Rol.CONTRATACION, Perfil.Rol.SEGURIDAD, Perfil.Rol.PSICOLOGIA, Perfil.Rol.RRHH):
            usuario = User.objects.create_user(rol.lower())
            usuario.perfil.rol = rol
            usuario.perfil.save()
        self.client.force_login(self.gerente)
        primera = self.client.get(reverse("procesos:usuarios")).context["usuarios"]
        self.assertEqual([u.perfil.rol for u in primera], ["GERENTE", "VINCULACION", "RRHH", "PSICOLOGIA", "SEGURIDAD"])
        segunda = self.client.get(reverse("procesos:usuarios") + "?page=2").context["usuarios"]
        self.assertEqual([u.perfil.rol for u in segunda], ["CONTRATACION"])

    def test_modo_servidor_no_crea_cuentas_en_sqlite(self):
        with patch("procesos.management.commands.crear_contratacion.connection") as conexion:
            conexion.vendor = "sqlite"
            with self.assertRaises(CommandError):
                call_command("crear_contratacion", exigir_mysql=True, stdout=StringIO())
        self.assertFalse(User.objects.filter(username="contratacion").exists())
