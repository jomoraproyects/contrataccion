from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

from .calendario import dias_habiles_restantes, segundos_habiles_entre, sumar_dias_habiles


PLAZOS_ETAPA_DIAS = {
    "RRHH": 2,
    "PSICOLOGIA": 3,
    "SEGURIDAD": 6,
    "CONTRATACION": 2,
}


class Perfil(models.Model):
    class Rol(models.TextChoices):
        SIN_ASIGNAR = "SIN_ASIGNAR", "Sin acceso asignado"
        CONTRATACION = "CONTRATACION", "Contratación"
        RRHH = "RRHH", "Talento Humano"
        PSICOLOGIA = "PSICOLOGIA", "Psicología"
        SEGURIDAD = "SEGURIDAD", "Seguridad y Salud en el Trabajo"
        GERENTE = "GERENTE", "Gerente"

    usuario = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    rol = models.CharField(max_length=20, choices=Rol.choices, default=Rol.SIN_ASIGNAR, db_index=True)
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueado_hasta = models.DateTimeField(null=True, blank=True)

    @property
    def bloqueo_seguridad_activo(self):
        return bool(self.bloqueado_hasta and self.bloqueado_hasta > timezone.now())

    def limpiar_bloqueo(self):
        self.intentos_fallidos = 0
        self.bloqueado_hasta = None
        self.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])

    def __str__(self):
        return f"{self.usuario.get_full_name() or self.usuario.username} - {self.get_rol_display()}"


class ProcesoSeleccion(models.Model):
    class Etapa(models.TextChoices):
        RRHH = "RRHH", "Talento Humano"
        PSICOLOGIA = "PSICOLOGIA", "Psicología"
        SEGURIDAD = "SEGURIDAD", "Seguridad y Salud en el Trabajo"
        CONTRATACION = "CONTRATACION", "Contratación"

    class Estado(models.TextChoices):
        EN_CURSO = "EN_CURSO", "En curso"
        LISTO_CONTRATACION = "LISTO_CONTRATACION", "Listo para contratación"
        CONTRATADO = "CONTRATADO", "Contratado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    nombre = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=120)
    cedula = models.CharField("número de cédula", max_length=30, db_index=True)
    cedula_proceso_abierto = models.CharField(max_length=30, unique=True, null=True, blank=True, editable=False)
    celular = models.CharField("número de celular", max_length=30)
    fecha_llegada = models.DateField("fecha de llegada de la hoja de vida")
    vacante = models.CharField("vacante o área", max_length=150)
    etapa_actual = models.CharField(max_length=20, choices=Etapa.choices, default=Etapa.RRHH)
    estado = models.CharField(max_length=25, choices=Estado.choices, default=Estado.EN_CURSO)
    activo = models.BooleanField(default=True)
    archivado_en = models.DateTimeField(null=True, blank=True)
    archivado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="procesos_archivados",
        null=True,
        blank=True,
    )
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="procesos_creados")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-creado_en"]
        verbose_name = "proceso de selección"
        verbose_name_plural = "procesos de selección"
        indexes = [
            models.Index(fields=["activo", "estado", "etapa_actual"], name="proceso_flujo_idx"),
            models.Index(fields=["fecha_llegada"], name="proceso_fecha_idx"),
        ]
        constraints = [models.CheckConstraint(
            condition=(
                Q(estado="RECHAZADO")
                | Q(etapa_actual="CONTRATACION", estado__in=["LISTO_CONTRATACION", "CONTRATADO"])
                | Q(etapa_actual__in=["RRHH", "PSICOLOGIA", "SEGURIDAD"], estado="EN_CURSO")
            ),
            name="estado_coherente_con_etapa",
        )]

    def __str__(self):
        return f"{self.nombre} {self.apellidos} - {self.vacante}"

    @property
    def proceso_abierto(self):
        return self.activo and self.estado in (self.Estado.EN_CURSO, self.Estado.LISTO_CONTRATACION)

    def save(self, *args, **kwargs):
        """Mantiene una cédula única para procesos abiertos en MySQL y SQLite."""
        self.cedula_proceso_abierto = self.cedula if self.proceso_abierto else None
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"cedula_proceso_abierto"}
        return super().save(*args, **kwargs)

    @property
    def nombre_completo(self):
        return f"{self.nombre} {self.apellidos}"

    @property
    def esta_finalizado(self):
        return self.estado in (self.Estado.RECHAZADO, self.Estado.CONTRATADO)

    @property
    def etapa_rechazo(self):
        decision = self.decisiones.filter(resultado=Decision.Resultado.RECHAZADO, vigente=True).first()
        return decision.get_etapa_display() if decision else self.get_etapa_actual_display()

    @property
    def motivo_rechazo(self):
        decision = self.decisiones.filter(resultado=Decision.Resultado.RECHAZADO, vigente=True).first()
        if decision:
            return decision.observacion
        cambio = self.cambios_gerencia.filter(estado_nuevo=self.Estado.RECHAZADO).first()
        return cambio.descripcion if cambio else "Sin motivo registrado"

    @property
    def duracion_total_horas(self):
        return round(sum(item.duracion_horas for item in self.seguimientos.all()), 1)

    @property
    def duracion_total_legible(self):
        horas = self.duracion_total_horas
        if horas < 24:
            return f"{horas:g} horas"
        dias = int(horas // 24)
        horas_restantes = round(horas - dias * 24, 1)
        return f"{dias} día(s) y {horas_restantes:g} horas"

    @property
    def cumplimiento_etapas(self):
        medidos = [
            item for item in self.seguimientos.all()
            if item.fin and item.resultado != SeguimientoEtapa.Resultado.AJUSTADO
        ]
        a_tiempo = sum(not item.esta_vencido for item in medidos)
        return f"{a_tiempo} de {len(medidos)} a tiempo" if medidos else "Sin etapas finalizadas"

    def puede_decidir(self, usuario):
        if not usuario.is_authenticated or self.esta_finalizado or not self.activo:
            return False
        rol = getattr(getattr(usuario, "perfil", None), "rol", None)
        return rol == self.etapa_actual

    def abrir_seguimiento(self, etapa=None, inicio=None):
        if self.esta_finalizado or not self.activo:
            return None
        etapa = etapa or self.etapa_actual
        existente = self.seguimientos.filter(etapa=etapa, fin__isnull=True).first()
        if existente:
            return existente
        inicio = inicio or timezone.now()
        ciclo = (self.seguimientos.filter(etapa=etapa).aggregate(models.Max("ciclo"))["ciclo__max"] or 0) + 1
        return SeguimientoEtapa.objects.create(
            proceso=self,
            etapa=etapa,
            ciclo=ciclo,
            inicio=inicio,
            fecha_limite=sumar_dias_habiles(inicio, PLAZOS_ETAPA_DIAS[etapa]),
        )

    @transaction.atomic
    def registrar_decision(self, usuario, resultado, observacion):
        proceso = ProcesoSeleccion.objects.select_for_update().get(pk=self.pk)
        if not proceso.puede_decidir(usuario):
            raise ValidationError("No tiene permiso para decidir en la etapa actual.")
        observacion = (observacion or "").strip()
        if not observacion:
            raise ValidationError("La observación es obligatoria.")
        if resultado not in Decision.Resultado.values:
            raise ValidationError("La decisión no es válida.")

        decision = Decision.objects.create(
            proceso=proceso,
            etapa=proceso.etapa_actual,
            resultado=resultado,
            observacion=observacion,
            decidido_por=usuario,
        )
        seguimiento = proceso.seguimientos.select_for_update().filter(
            etapa=proceso.etapa_actual, fin__isnull=True
        ).first() or proceso.abrir_seguimiento(proceso.etapa_actual, proceso.creado_en)
        seguimiento.fin = decision.fecha
        seguimiento.resultado = resultado
        seguimiento.cerrado_por = usuario
        seguimiento.save(update_fields=["fin", "resultado", "cerrado_por"])
        if resultado == Decision.Resultado.RECHAZADO:
            proceso.estado = self.Estado.RECHAZADO
        else:
            siguiente = {
                self.Etapa.RRHH: self.Etapa.PSICOLOGIA,
                self.Etapa.PSICOLOGIA: self.Etapa.SEGURIDAD,
                self.Etapa.SEGURIDAD: self.Etapa.CONTRATACION,
            }
            if proceso.etapa_actual == self.Etapa.CONTRATACION:
                proceso.estado = self.Estado.CONTRATADO
            else:
                proceso.etapa_actual = siguiente[proceso.etapa_actual]
                proceso.estado = (
                    self.Estado.LISTO_CONTRATACION
                    if proceso.etapa_actual == self.Etapa.CONTRATACION
                    else self.Estado.EN_CURSO
                )
        proceso.save(update_fields=["etapa_actual", "estado", "actualizado_en"])
        if not proceso.esta_finalizado:
            proceso.abrir_seguimiento(proceso.etapa_actual, decision.fecha)
        self.refresh_from_db()
        return decision


class Decision(models.Model):
    class Resultado(models.TextChoices):
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"

    proceso = models.ForeignKey(ProcesoSeleccion, on_delete=models.CASCADE, related_name="decisiones")
    etapa = models.CharField(max_length=20, choices=ProcesoSeleccion.Etapa.choices)
    resultado = models.CharField(max_length=12, choices=Resultado.choices)
    observacion = models.TextField()
    decidido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="decisiones")
    fecha = models.DateTimeField(auto_now_add=True)
    vigente = models.BooleanField(default=True)
    etapa_vigente = models.CharField(max_length=50, unique=True, null=True, blank=True, editable=False)
    anulada_en = models.DateTimeField(null=True, blank=True)
    anulada_por_gerencia = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="decisiones_anuladas",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["fecha"]
        constraints = [
            models.CheckConstraint(condition=~Q(observacion=""), name="decision_observacion_no_vacia"),
        ]

    def save(self, *args, **kwargs):
        """Garantiza una decisión vigente por etapa en MySQL y SQLite."""
        self.etapa_vigente = f"{self.proceso_id}:{self.etapa}" if self.vigente else None
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"etapa_vigente"}
        return super().save(*args, **kwargs)

    def clean(self):
        if not self.observacion or not self.observacion.strip():
            raise ValidationError({"observacion": "La observación es obligatoria."})

    def __str__(self):
        return f"{self.proceso.nombre_completo} - {self.get_etapa_display()} - {self.get_resultado_display()}"


class CambioGerencia(models.Model):
    class Tipo(models.TextChoices):
        ACTUALIZACION = "ACTUALIZACION", "Actualización"
        ARCHIVADO = "ARCHIVADO", "Desactivación"
        RESTAURADO = "RESTAURADO", "Restauración"
        ELIMINADO = "ELIMINADO", "Eliminación definitiva"

    proceso = models.ForeignKey(
        ProcesoSeleccion,
        on_delete=models.SET_NULL,
        related_name="cambios_gerencia",
        null=True,
        blank=True,
    )
    candidato_nombre = models.CharField(max_length=221)
    cedula = models.CharField(max_length=30)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.TextField()
    etapa_anterior = models.CharField(max_length=20, choices=ProcesoSeleccion.Etapa.choices, blank=True)
    etapa_nueva = models.CharField(max_length=20, choices=ProcesoSeleccion.Etapa.choices, blank=True)
    estado_anterior = models.CharField(max_length=25, choices=ProcesoSeleccion.Estado.choices, blank=True)
    estado_nuevo = models.CharField(max_length=25, choices=ProcesoSeleccion.Estado.choices, blank=True)
    realizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cambios_gerencia")
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.candidato_nombre}"


class SeguimientoEtapa(models.Model):
    class Resultado(models.TextChoices):
        APROBADO = "APROBADO", "Aprobado"
        RECHAZADO = "RECHAZADO", "Rechazado"
        AJUSTADO = "AJUSTADO", "Ajustado por Gerencia"

    proceso = models.ForeignKey(ProcesoSeleccion, on_delete=models.CASCADE, related_name="seguimientos")
    etapa = models.CharField(max_length=20, choices=ProcesoSeleccion.Etapa.choices)
    ciclo = models.PositiveSmallIntegerField(default=1)
    inicio = models.DateTimeField()
    fecha_limite = models.DateTimeField()
    segundos_pausados = models.PositiveBigIntegerField(default=0)
    fin = models.DateTimeField(null=True, blank=True)
    proceso_en_curso = models.PositiveBigIntegerField(unique=True, null=True, blank=True, editable=False)
    resultado = models.CharField(max_length=12, choices=Resultado.choices, blank=True)
    cerrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="seguimientos_cerrados",
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["inicio"]
        indexes = [
            models.Index(fields=["fin", "fecha_limite"], name="seguimiento_plazo_idx"),
            models.Index(fields=["etapa", "fin"], name="seguimiento_etapa_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["proceso", "etapa", "ciclo"], name="un_ciclo_por_etapa_proceso"
            ),
        ]

    def save(self, *args, **kwargs):
        """Impide dos seguimientos abiertos del mismo proceso en MySQL y SQLite."""
        self.proceso_en_curso = self.proceso_id if self.fin is None else None
        if kwargs.get("update_fields") is not None:
            kwargs["update_fields"] = set(kwargs["update_fields"]) | {"proceso_en_curso"}
        return super().save(*args, **kwargs)

    @property
    def plazo_dias(self):
        return PLAZOS_ETAPA_DIAS[self.etapa]

    @property
    def referencia_tiempo(self):
        return self.fin or timezone.now()

    @property
    def esta_vencido(self):
        return self.referencia_tiempo > self.fecha_limite

    @property
    def dias_restantes(self):
        return dias_habiles_restantes(timezone.now(), self.fecha_limite)

    @property
    def estado_plazo(self):
        if self.fin:
            return "Fuera de tiempo" if self.esta_vencido else "A tiempo"
        if self.dias_restantes < 0:
            return f"Vencido hace {abs(self.dias_restantes)} día(s) hábil(es)"
        if self.dias_restantes == 0:
            return "Vence hoy"
        return f"Quedan {self.dias_restantes} día(s) hábil(es)"

    @property
    def clase_plazo(self):
        if self.esta_vencido:
            return "danger"
        if not self.fin and self.dias_restantes <= 1:
            return "warning"
        return "success"

    @property
    def duracion_horas(self):
        segundos = max(0, segundos_habiles_entre(self.inicio, self.referencia_tiempo) - self.segundos_pausados)
        return round(segundos / 3600, 1)

    def __str__(self):
        return f"{self.proceso.nombre_completo} - {self.get_etapa_display()} - ciclo {self.ciclo}"


class EventoSeguridad(models.Model):
    class Tipo(models.TextChoices):
        LOGIN_CORRECTO = "LOGIN_OK", "Inicio de sesión correcto"
        LOGIN_FALLIDO = "LOGIN_FAIL", "Inicio de sesión fallido"
        CUENTA_BLOQUEADA = "ACCOUNT_LOCK", "Cuenta bloqueada"
        ACCESO_DENEGADO = "ACCESS_DENIED", "Acceso denegado"
        USUARIO_CREADO = "USER_CREATED", "Usuario creado"
        USUARIO_EDITADO = "USER_UPDATED", "Usuario editado"
        PASSWORD_CAMBIADA = "PASSWORD_CHANGED", "Contraseña cambiada"

    tipo = models.CharField(max_length=24, choices=Tipo.choices)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="eventos_seguridad",
        null=True,
        blank=True,
    )
    ip = models.GenericIPAddressField(null=True, blank=True)
    identificador_hash = models.CharField(max_length=64, blank=True)
    detalle = models.CharField(max_length=250, blank=True)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-fecha"]
        indexes = [
            models.Index(fields=["tipo", "fecha"], name="evento_tipo_fecha_idx"),
            models.Index(fields=["ip", "fecha"], name="evento_ip_fecha_idx"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.fecha:%Y-%m-%d %H:%M}"
