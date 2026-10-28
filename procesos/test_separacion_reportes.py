from datetime import date
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.test import TestCase, SimpleTestCase
from django.urls import reverse

from .models import Perfil, ProcesoSeleccion
from .pdf_reportes import _estilos, _tabla, candidatos_pdf, trazabilidad_pdf


class SeparacionPanelesTests(TestCase):
    def setUp(self):
        self.gerente = User.objects.create_user("visor-paneles")
        self.gerente.perfil.rol = Perfil.Rol.GERENTE
        self.gerente.perfil.save()
        self.client.force_login(self.gerente)
        self.proceso = ProcesoSeleccion.objects.create(
            nombre="Persona", apellidos="Filtro", cedula="452001", celular="3001234567",
            vacante="Operaciones", fecha_llegada=date(2026, 10, 8), creado_por=self.gerente,
        )

    def test_trazabilidad_solo_muestra_resumen_y_candidatos(self):
        respuesta = self.client.get(reverse("procesos:trazabilidad"))
        self.assertContains(respuesta, "Trazabilidad por candidato")
        self.assertContains(respuesta, "Procesos con retrasos")
        self.assertNotContains(respuesta, "Comportamiento por etapa")
        self.assertNotContains(respuesta, "Mayor demora promedio del periodo")
        self.assertNotContains(respuesta, "titulo-indicadores-etapa")

    def test_indicadores_agrega_sin_listado_y_enlaza_mismos_filtros(self):
        respuesta = self.client.get(reverse("procesos:indicadores"), {
            "periodo": "mensual", "mes": "2026-10", "vacante": "OPERA", "estado": "EN_CURSO",
        })
        self.assertContains(respuesta, "Comportamiento por etapa")
        self.assertNotContains(respuesta, "Candidatos filtrados")
        self.assertNotContains(respuesta, 'class="pagination')
        filtros = parse_qs(urlsplit(respuesta.context["url_trazabilidad"]).query)
        self.assertEqual(filtros["fecha_desde"], ["2026-10-01"])
        self.assertEqual(filtros["fecha_hasta"], ["2026-10-31"])
        traza = self.client.get(respuesta.context["url_trazabilidad"])
        self.assertEqual(traza.context["total_procesos"], 1)
        self.assertEqual(traza.context["procesos"][0].pk, self.proceso.pk)

    def test_rol_operativo_no_recibe_enlace_sin_permiso(self):
        self.gerente.perfil.rol = Perfil.Rol.VINCULACION
        self.gerente.perfil.save()
        respuesta = self.client.get(reverse("procesos:indicadores"))
        self.assertNotContains(respuesta, "Ver candidatos de este periodo en Trazabilidad")


class DisenoPDFTests(SimpleTestCase):
    def test_tabla_ajusta_ancho_y_repite_encabezados_con_textos_largos(self):
        texto = "Vacante muy extensa con acentos: recolección y operación " * 12
        tabla = _tabla(["Candidato", "Vacante"], [["Persona de ejemplo", texto]], [1, 2], 740, _estilos())
        self.assertAlmostEqual(sum(tabla._colWidths), 740)
        self.assertEqual(tabla.repeatRows, 1)
        self.assertEqual(tabla._cellvalues[1][1].getPlainText(), texto.strip())
        self.assertEqual(tabla._cellvalues[1][1].style.fontSize, 9)

    def test_pdf_sin_resultados_se_genera_en_ambos_formatos(self):
        resumen = dict(total=0, finalizados=0, con_retrasos=0, abiertos=0)
        for contenido in (candidatos_pdf([], "Sin resultados"), trazabilidad_pdf([], resumen, "Sin resultados")):
            self.assertTrue(contenido.startswith(b"%PDF"))
            self.assertIn(b"/Author (Serviciudad)", contenido)
