from datetime import date
from urllib.parse import parse_qs, urlsplit
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import TestCase, SimpleTestCase
from django.urls import reverse

from .models import Perfil, ProcesoSeleccion
from .pdf_reportes import _estilos, _tabla, _tabla_candidatos, candidatos_pdf, trazabilidad_pdf


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

    def test_distribucion_de_graficas_no_deja_una_tarjeta_sola_a_media_fila(self):
        from html.parser import HTMLParser

        class Tarjetas(HTMLParser):
            def __init__(self):
                super().__init__()
                self.actual = None
                self.graficas = []

            def handle_starttag(self, tag, attrs):
                attrs = dict(attrs)
                if tag == "article":
                    self.actual = {"clases": attrs.get("class", "").split(), "grafica": None}
                if self.actual is not None and "data-chart" in attrs:
                    self.actual["grafica"] = attrs["data-chart"]

            def handle_endtag(self, tag):
                if tag == "article" and self.actual is not None:
                    if self.actual["grafica"]:
                        self.graficas.append(self.actual)
                    self.actual = None

        respuesta = self.client.get(reverse("procesos:indicadores"), {"periodo": "anual", "anio": "2026"})
        parser = Tarjetas()
        parser.feed(respuesta.content.decode())
        self.assertEqual([item["grafica"] for item in parser.graficas], ["historico", "rechazos", "estados", "etapas", "cumplimiento", "vacantes"])
        self.assertEqual(["analytics-wide" in item["clases"] for item in parser.graficas], [True, False, False, False, False, True])


class DisenoPDFTests(SimpleTestCase):
    def test_motivo_esta_debajo_de_su_candidato_y_antes_del_siguiente(self):
        rechazado = SimpleNamespace(estado="RECHAZADO", etapa_rechazo="Psicología", motivo_rechazo="Observación <b>literal</b> & texto seguro", requisitos_rechazo=["Prueba psicotécnica"])
        pendiente = SimpleNamespace(estado="EN_CURSO")
        tabla = _tabla_candidatos(
            ["Candidato", "Estado"], [rechazado, pendiente],
            [["Primera persona", "Rechazado"], ["Segunda persona", "En curso"]],
            [2, 1], SimpleNamespace(width=740, height=440), _estilos(),
        )
        self.assertEqual(len(tabla._cellvalues), 4)
        def texto(fila):
            celda = tabla._cellvalues[fila][0]
            return (celda[0] if isinstance(celda, (tuple, list)) else celda).getPlainText()
        self.assertEqual(texto(1), "Primera persona")
        self.assertIn("Motivo de rechazo - Psicología:", texto(2))
        self.assertIn("<b>literal</b> & texto seguro", texto(2))
        self.assertIn("Validaciones no cumplidas: Prueba psicotécnica", texto(2))
        self.assertEqual(texto(3), "Segunda persona")
        self.assertIn(("SPAN", (0, 2), (-1, 2)), tabla._spanCmds)
        self.assertEqual(tabla.splitInRow, 0)
        alto_sin_motivo = tabla._rowHeights[0] + tabla._rowHeights[1] + 1
        self.assertEqual(tabla.split(740, alto_sin_motivo), [])

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
