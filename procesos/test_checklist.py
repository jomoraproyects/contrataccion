from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import DecisionForm
from .models import Decision, Perfil, ProcesoSeleccion
from .requisitos import CUMPLE, NO_CUMPLE, obtener_requisitos


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ChecklistEtapasTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = {}
        for rol in (Perfil.Rol.VINCULACION, *ProcesoSeleccion.Etapa.values, Perfil.Rol.GERENTE):
            usuario = User.objects.create_user(username=f"lista_{rol.lower()}", password="Prueba-checklist")
            usuario.perfil.rol = rol
            usuario.perfil.save(update_fields=["rol"])
            cls.usuarios[rol] = usuario

    def crear_proceso(self, etapa=ProcesoSeleccion.Etapa.RRHH):
        estado = (
            ProcesoSeleccion.Estado.LISTO_CONTRATACION
            if etapa == ProcesoSeleccion.Etapa.CONTRATACION else ProcesoSeleccion.Estado.EN_CURSO
        )
        return ProcesoSeleccion.objects.create(
            nombre="Persona", apellidos="Lista de requisitos", cedula="1001001", celular="3001234567",
            fecha_llegada=timezone.localdate(), vacante="Operaciones", etapa_actual=etapa, estado=estado,
            creado_por=self.usuarios[Perfil.Rol.VINCULACION],
        )

    def respuestas(self, etapa, falla=None):
        return {
            requisito["codigo"]: NO_CUMPLE if requisito["codigo"] == falla else CUMPLE
            for requisito in obtener_requisitos(etapa)
        }

    def decidir(self, proceso, resultado=Decision.Resultado.APROBADO, verificaciones=None):
        return proceso.registrar_decision(
            self.usuarios[proceso.etapa_actual], resultado, "Revisión realizada por el área",
            verificaciones=verificaciones,
        )

    def assert_sin_decision(self, proceso):
        proceso.refresh_from_db()
        self.assertEqual(proceso.estado, ProcesoSeleccion.Estado.EN_CURSO)
        self.assertFalse(proceso.decisiones.exists())
        self.assertEqual(proceso.seguimientos.filter(fin__isnull=True).count(), 1)

    def test_flujo_completo_con_lista_de_cada_area_y_contratacion_sin_lista(self):
        proceso = self.crear_proceso()
        for etapa, cantidad in (("RRHH", 5), ("PSICOLOGIA", 2), ("SEGURIDAD", 4)):
            decision = self.decidir(proceso, verificaciones=self.respuestas(etapa))
            decision.refresh_from_db()
            self.assertEqual(decision.verificaciones["version"], 1)
            self.assertEqual(len(decision.requisitos_verificados), cantidad)
            self.assertTrue(all(item["cumple"] for item in decision.requisitos_verificados))
        final = self.decidir(proceso)
        self.assertEqual(final.verificaciones, {})
        self.assertEqual(proceso.estado, ProcesoSeleccion.Estado.CONTRATADO)
        self.assertEqual(proceso.decisiones.count(), 4)

    def test_servicio_impide_omitir_lista_de_requisitos(self):
        proceso = self.crear_proceso()
        with self.assertRaises(ValidationError):
            self.decidir(proceso)
        self.assert_sin_decision(proceso)

    def test_servicio_impide_saltar_un_requisito(self):
        proceso = self.crear_proceso()
        respuestas = self.respuestas(proceso.etapa_actual)
        respuestas.pop("redam")
        with self.assertRaises(ValidationError):
            self.decidir(proceso, verificaciones=respuestas)
        self.assert_sin_decision(proceso)

    def test_servicio_impide_aprobar_con_un_incumplimiento(self):
        proceso = self.crear_proceso()
        with self.assertRaises(ValidationError):
            self.decidir(proceso, verificaciones=self.respuestas("RRHH", falla="procuraduria"))
        self.assert_sin_decision(proceso)

    def test_servicio_no_interpreta_respuesta_pendiente_como_fallo(self):
        proceso = self.crear_proceso()
        respuestas = self.respuestas("RRHH")
        respuestas["redam"] = ""
        with self.assertRaises(ValidationError):
            self.decidir(proceso, Decision.Resultado.RECHAZADO, respuestas)
        self.assert_sin_decision(proceso)

    def test_servicio_no_permite_rechazar_con_todo_aprobado(self):
        proceso = self.crear_proceso()
        with self.assertRaises(ValidationError):
            self.decidir(proceso, Decision.Resultado.RECHAZADO, self.respuestas("RRHH"))
        self.assert_sin_decision(proceso)

    def test_servicio_no_acepta_claves_extras_o_valores_no_permitidos(self):
        proceso = self.crear_proceso()
        for respuestas in (
            {**self.respuestas("RRHH"), "otro": CUMPLE},
            {**self.respuestas("RRHH"), "redam": True},
            [CUMPLE] * 5,
        ):
            with self.subTest(respuestas=respuestas), self.assertRaises(ValidationError):
                self.decidir(proceso, verificaciones=respuestas)
        self.assert_sin_decision(proceso)

    def test_sst_puede_rechazar_un_examen_y_preserva_motivo(self):
        proceso = self.crear_proceso("SEGURIDAD")
        decision = self.decidir(
            proceso, Decision.Resultado.RECHAZADO,
            self.respuestas("SEGURIDAD", falla="radiografia_columna"),
        )
        self.assertEqual(proceso.estado, ProcesoSeleccion.Estado.RECHAZADO)
        self.assertEqual(proceso.requisitos_rechazo, ["Radiografía de columna"])
        self.assertEqual(proceso.motivo_rechazo, "Revisión realizada por el área")
        self.assertEqual(len(decision.requisitos_verificados), 4)
        self.assertEqual(decision.requisitos_verificados[1]["estado"], "No cumple")
        self.assertFalse(proceso.seguimientos.filter(fin__isnull=True).exists())

    def test_sst_no_aprueba_si_falta_un_examen(self):
        proceso = self.crear_proceso("SEGURIDAD")
        respuestas = self.respuestas("SEGURIDAD")
        respuestas.pop("electromiografia")
        with self.assertRaises(ValidationError):
            self.decidir(proceso, verificaciones=respuestas)
        self.assert_sin_decision(proceso)

    def test_observacion_obligatoria_tambien_con_todo_verificado(self):
        proceso = self.crear_proceso()
        with self.assertRaises(ValidationError):
            proceso.registrar_decision(
                self.usuarios["RRHH"], Decision.Resultado.APROBADO, " ", self.respuestas("RRHH"),
            )
        self.assert_sin_decision(proceso)

    def test_lista_completa_no_permite_decidir_desde_otro_rol(self):
        proceso = self.crear_proceso()
        with self.assertRaises(ValidationError):
            proceso.registrar_decision(
                self.usuarios["PSICOLOGIA"], Decision.Resultado.APROBADO,
                "Revisión sin permiso", self.respuestas("RRHH"),
            )
        self.assert_sin_decision(proceso)

    def test_snapshot_historico_de_examen_anterior_no_cambia_con_el_catalogo_nuevo(self):
        proceso = self.crear_proceso("SEGURIDAD")
        decision = Decision.objects.create(
            proceso=proceso, etapa="SEGURIDAD", resultado=Decision.Resultado.APROBADO,
            observacion="Examen de ingreso verificado anteriormente",
            decidido_por=self.usuarios["SEGURIDAD"],
            verificaciones={"version": 1, "requisitos": [
                {"codigo": "examen_ingreso", "nombre": "Examen de ingreso", "resultado": CUMPLE},
            ]},
        )
        with patch("procesos.requisitos.REQUISITOS_ETAPA", {}):
            decision.refresh_from_db()
            self.assertEqual(decision.requisitos_verificados[0]["nombre"], "Examen de ingreso")
            self.assertTrue(decision.requisitos_verificados[0]["cumple"])

    def test_historicos_sin_lista_no_inventan_respuestas(self):
        proceso = self.crear_proceso()
        decision = Decision.objects.create(
            proceso=proceso, etapa="RRHH", resultado=Decision.Resultado.RECHAZADO,
            observacion="Motivo registrado antes de la lista", decidido_por=self.usuarios["RRHH"],
        )
        self.assertEqual(decision.verificaciones, {})
        self.assertEqual(decision.requisitos_verificados, [])
        self.assertEqual(decision.requisitos_no_cumplidos, [])
        self.assertEqual(proceso.requisitos_rechazo, [])
        self.assertEqual(proceso.motivo_rechazo, "Motivo registrado antes de la lista")

    def test_requisito_fallido_anulado_no_aparece_como_rechazo_vigente(self):
        proceso = self.crear_proceso()
        decision = self.decidir(proceso, Decision.Resultado.RECHAZADO, self.respuestas("RRHH", "redam"))
        self.assertEqual(proceso.requisitos_rechazo, ["REDAM"])
        decision.vigente = False
        decision.save(update_fields=["vigente"])
        self.assertEqual(proceso.requisitos_rechazo, [])

    def test_formulario_exige_respuestas_y_no_preselecciona_resultados(self):
        form = DecisionForm(etapa="RRHH")
        self.assertTrue(form.tiene_requisitos)
        self.assertEqual(len(form.campos_requisitos), 5)
        self.assertTrue(all(campo.value() is None for campo in form.campos_requisitos))
        form = DecisionForm({"resultado": "APROBADO", "observacion": "Todo revisado"}, etapa="RRHH")
        self.assertFalse(form.is_valid())
        self.assertIn("requisito_redam", form.errors)

    def test_formulario_rechazo_exige_fallo_y_observacion(self):
        datos = {
            "resultado": "RECHAZADO", "observacion": "No apto para el cargo",
            **{f"requisito_{codigo}": resultado for codigo, resultado in self.respuestas("SEGURIDAD").items()},
        }
        form = DecisionForm(datos, etapa="SEGURIDAD")
        self.assertFalse(form.is_valid())
        self.assertIn("resultado", form.errors)
        datos["requisito_radiografia_columna"] = NO_CUMPLE
        form = DecisionForm(datos, etapa="SEGURIDAD")
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["verificaciones"], self.respuestas("SEGURIDAD", falla="radiografia_columna"))
        datos["observacion"] = ""
        self.assertFalse(DecisionForm(datos, etapa="SEGURIDAD").is_valid())

    def test_post_sin_javascript_no_permite_saltar_verificaciones(self):
        proceso = self.crear_proceso()
        self.client.force_login(self.usuarios["RRHH"])
        response = self.client.post(reverse("procesos:detalle", args=[proceso.pk]), {
            "resultado": Decision.Resultado.APROBADO, "observacion": "Revisión sin enviar lista",
        })
        self.assertEqual(response.status_code, 200)
        self.assert_sin_decision(proceso)

    def test_post_rechazo_guarda_requisitos_y_observacion(self):
        proceso = self.crear_proceso("PSICOLOGIA")
        self.client.force_login(self.usuarios["PSICOLOGIA"])
        response = self.client.post(reverse("procesos:detalle", args=[proceso.pk]), {
            "resultado": Decision.Resultado.RECHAZADO,
            "observacion": "La prueba no cumple el perfil requerido",
            "requisito_entrevista": CUMPLE,
            "requisito_prueba_psicotecnica": NO_CUMPLE,
        })
        self.assertEqual(response.status_code, 302)
        proceso.refresh_from_db()
        self.assertEqual(proceso.estado, ProcesoSeleccion.Estado.RECHAZADO)
        self.assertEqual(proceso.requisitos_rechazo, ["Prueba psicotécnica"])
        self.assertEqual(proceso.decisiones.get().observacion, "La prueba no cumple el perfil requerido")
