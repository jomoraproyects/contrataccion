from datetime import date

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import Perfil, ProcesoSeleccion


class AvanceVisualTests(TestCase):
    def test_registro_y_cuatro_etapas_en_orden_sin_alterar_el_proceso(self):
        gerente = User.objects.create_user("visor")
        gerente.perfil.rol = Perfil.Rol.GERENTE
        gerente.perfil.save()
        proceso = ProcesoSeleccion.objects.create(
            nombre="Caso", apellidos="Avance", cedula="482001",
            celular="3001234567", fecha_llegada=date.today(),
            vacante="Pruebas", creado_por=gerente,
        )
        self.client.force_login(gerente)
        casos = (
            ("RRHH", "EN_CURSO", ["current", "", "", ""]),
            ("SEGURIDAD", "RECHAZADO", ["done", "done", "rejected", ""]),
            ("CONTRATACION", "LISTO_CONTRATACION", ["done", "done", "done", "current"]),
            ("CONTRATACION", "CONTRATADO", ["done", "done", "done", "done"]),
        )
        for etapa, estado, visuales in casos:
            with self.subTest(estado=estado):
                ProcesoSeleccion.objects.filter(pk=proceso.pk).update(etapa_actual=etapa, estado=estado)
                respuesta = self.client.get(reverse("procesos:detalle", args=[proceso.pk]))
                self.assertEqual(respuesta.status_code, 200)
                html = respuesta.content.decode().split('<div class="process-flow">', 1)[1].split('</section>', 1)[0]
                etiquetas = ["Vinculación", "Talento Humano", "Psicología", "Seguridad y Salud en el Trabajo", "Contratación"]
                posiciones = [html.index(f'flow-label">{etiqueta}<') for etiqueta in etiquetas]
                self.assertEqual(posiciones, sorted(posiciones))
                self.assertEqual(html.count('class="flow-step '), 5)
                self.assertIn("Registro del candidato", html)
                self.assertEqual([e["estado_visual"] for e in respuesta.context["etapas"]], visuales)
                proceso.refresh_from_db()
                self.assertEqual((proceso.etapa_actual, proceso.estado), (etapa, estado))
