from datetime import date, datetime, timezone as dt_timezone
from io import BytesIO

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from .models import CambioGerencia, Decision, Perfil, ProcesoSeleccion


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class HistoricoProcesosTests(TestCase):
    def setUp(self):
        self.gerente = User.objects.create_user("gerente-historico")
        self.gerente.perfil.rol = Perfil.Rol.GERENTE
        self.gerente.perfil.save()
        self.creador = User.objects.create_user("creador-historico")
        self.creador.perfil.rol = Perfil.Rol.VINCULACION
        self.creador.perfil.save()
        self.client.force_login(self.gerente)

    def proceso(self, numero, llegada=date(2026, 9, 1)):
        return ProcesoSeleccion.objects.create(nombre=f"Histórico {numero}", apellidos="Ejemplo", cedula=f"76850{numero:04d}", celular="3001234567", vacante="Ventas", fecha_llegada=llegada, creado_por=self.creador)

    def decision(self, proceso, fecha, resultado="APROBADO", etapa="CONTRATACION", vigente=True):
        decision = Decision.objects.create(proceso=proceso, fecha=fecha, etapa=etapa, resultado=resultado, decidido_por=self.gerente, observacion="Observación de prueba", vigente=vigente)
        Decision.objects.filter(pk=decision.pk).update(fecha=fecha)
        return decision

    def consulta(self, **filtros):
        return self.client.get(reverse("procesos:indicadores"), {"periodo": "anual", "anio": "2026", **filtros})

    def test_cierre_en_octubre_de_candidato_recibido_en_septiembre(self):
        p = self.proceso(1)
        self.decision(p, timezone.make_aware(datetime(2026, 10, 2, 10)))
        respuesta = self.consulta(periodo="mensual", mes="2026-10")
        resumen = respuesta.context["indicadores"]
        self.assertEqual(resumen["total"], 0)  # La foto por llegada no cambia.
        self.assertEqual(resumen["historico"]["filas"][0]["contratados"], 1)
        self.assertEqual(resumen["historico"]["filas"][0]["recibidos"], 0)

    def test_semanas_iso_cruzan_anio_y_meses_sin_movimiento_son_cero(self):
        self.proceso(1, date(2026, 12, 31))
        semanal = self.consulta(periodo="personalizado", fecha_desde="2026-12-28", fecha_hasta="2027-01-03", agrupacion="semanal")
        filas = semanal.context["indicadores"]["historico"]["filas"]
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["etiqueta"], "S53 · 2026")
        self.assertEqual(filas[0]["recibidos"], 1)
        mensual = self.consulta()
        self.assertEqual(len(mensual.context["indicadores"]["historico"]["filas"]), 12)
        self.assertEqual(mensual.context["indicadores"]["historico"]["filas"][0]["recibidos"], 0)

    def test_rechazos_fecha_local_y_no_cuenta_aprobaciones_intermedias_ni_anuladas(self):
        p = self.proceso(1)
        self.decision(p, datetime(2026, 11, 1, 2, tzinfo=dt_timezone.utc), "RECHAZADO", "PSICOLOGIA")
        self.decision(self.proceso(2), timezone.make_aware(datetime(2026, 10, 2, 10)), etapa="RRHH")
        self.decision(self.proceso(3), timezone.make_aware(datetime(2026, 10, 2, 10)), vigente=False)
        hist = self.consulta().context["indicadores"]["historico"]["filas"]
        self.assertEqual(hist[9]["rechazados"], 1)
        self.assertEqual(hist[10]["rechazados"], 0)
        self.assertEqual(sum(f["contratados"] for f in hist), 0)

    def test_no_inventa_fecha_de_cierre_y_no_duplica_decision_y_gerencia(self):
        p = self.proceso(1)
        self.decision(p, timezone.make_aware(datetime(2026, 10, 2, 10)))
        CambioGerencia.objects.create(proceso=p, candidato_nombre=p.nombre_completo, cedula=p.cedula, tipo="ACTUALIZACION", descripcion="Cambio", estado_anterior="EN_CURSO", estado_nuevo="CONTRATADO", realizado_por=self.gerente)
        sin_fecha = self.proceso(2)
        ProcesoSeleccion.objects.filter(pk=sin_fecha.pk).update(estado="CONTRATADO", etapa_actual="CONTRATACION")
        hist = self.consulta().context["indicadores"]["historico"]
        self.assertEqual(sum(f["contratados"] for f in hist["filas"]), 1)
        self.assertEqual(hist["sin_fecha"], 1)

    def test_estado_y_ambito_del_rol_se_conservan(self):
        p = self.proceso(1)
        otro = self.proceso(2)
        ProcesoSeleccion.objects.filter(pk=otro.pk).update(creado_por=self.gerente)
        for proceso in (p, otro):
            self.decision(proceso, timezone.make_aware(datetime(2026, 10, 2, 10)))
        self.client.force_login(self.creador)
        hist = self.consulta().context["indicadores"]["historico"]["filas"]
        self.assertEqual(sum(f["contratados"] for f in hist), 1)
        self.assertEqual(sum(f["recibidos"] for f in hist), 1)

    def test_agrupacion_y_exportacion_respeta_anios_y_no_expone_todos_los_datos(self):
        self.proceso(1, date(2025, 12, 31))
        self.proceso(2, date(2026, 1, 1))
        filtros = dict(periodo="personalizado", fecha_desde="2025-01-01", fecha_hasta="2026-12-31", agrupacion="anual", informe="estadistico")
        panel = self.consulta(**filtros)
        filas = panel.context["indicadores"]["historico"]["filas"]
        self.assertEqual([f["recibidos"] for f in filas], [1, 1])
        excel = self.client.get(reverse("procesos:exportar_indicadores", args=["xlsx"]), filtros)
        hoja = load_workbook(BytesIO(excel.content))["Histórico"]
        self.assertEqual(hoja["B2"].value, "anual")
        self.assertEqual([hoja["B7"].value, hoja["B8"].value], [1, 1])
        invalido = self.consulta(agrupacion="diario")
        self.assertEqual(invalido.context["indicadores"]["historico"]["filas"], [])
        excesivo = self.consulta(periodo="personalizado", fecha_desde="2000-01-01", fecha_hasta="2100-12-31", agrupacion="semanal")
        self.assertIn("200 intervalos", excesivo.context["indicadores"]["historico"]["error"])
