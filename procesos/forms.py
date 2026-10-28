import calendar
from datetime import date, timedelta

from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Candidato, Decision, Perfil, ProcesoSeleccion
from .requisitos import RESULTADOS_REQUISITO, obtener_requisitos, validar_verificaciones
from .validacion import normalizar_cedula, normalizar_celular, normalizar_vacante


ROLES_OPERATIVOS = [
    (rol.value, rol.label) for rol in (
        Perfil.Rol.VINCULACION, Perfil.Rol.RRHH, Perfil.Rol.PSICOLOGIA,
        Perfil.Rol.SEGURIDAD, Perfil.Rol.CONTRATACION,
    )
]


class ProcesoForm(forms.ModelForm):
    class Meta:
        model = ProcesoSeleccion
        fields = ["nombre", "apellidos", "cedula", "celular", "fecha_llegada", "vacante"]
        widgets = {
            # Los navegadores solo aceptan ISO en el valor de un input date.
            # Sin format, la localizacion es-co dejaba vacío el campo al editar.
            "fecha_llegada": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "nombre": forms.TextInput(attrs={"autofocus": True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control form-control-lg"

    def clean_cedula(self):
        cedula = normalizar_cedula(self.cleaned_data["cedula"])
        identidad = Candidato.objects.filter(cedula=cedula).first()
        if self.instance.pk and identidad and self.instance.candidato_id != identidad.pk:
            raise forms.ValidationError(
                "Esta cédula pertenece a otra persona registrada y no puede combinarse con este historial."
            )
        abierto = ProcesoSeleccion.objects.filter(
            cedula=cedula,
            activo=True,
            estado__in=[ProcesoSeleccion.Estado.EN_CURSO, ProcesoSeleccion.Estado.LISTO_CONTRATACION],
        ).exclude(pk=self.instance.pk if self.instance else None)
        if abierto.exists():
            proceso = abierto.first()
            raise forms.ValidationError(
                f"Esta cédula ya tiene un proceso abierto para {proceso.vacante}. "
                "Debe finalizarse o desactivarse antes de crear otro."
            )
        return cedula

    def clean_celular(self):
        return normalizar_celular(self.cleaned_data["celular"])

    def clean_vacante(self):
        return normalizar_vacante(self.cleaned_data["vacante"])

    def clean_fecha_llegada(self):
        fecha = self.cleaned_data["fecha_llegada"]
        if fecha > timezone.localdate():
            raise forms.ValidationError("La fecha de llegada no puede estar en el futuro.")
        return fecha


class NuevoProcesoForm(ProcesoForm):
    """Impide registrar de nuevo una cédula al crear un candidato."""

    def clean_cedula(self):
        cedula = normalizar_cedula(self.cleaned_data["cedula"])
        anteriores = ProcesoSeleccion.objects.filter(cedula=cedula).order_by("-creado_en", "-pk")
        rechazo = anteriores.filter(estado=ProcesoSeleccion.Estado.RECHAZADO).first()
        if rechazo:
            requisitos = ", ".join(rechazo.requisitos_rechazo)
            raise forms.ValidationError(
                f"Esta persona ya estuvo en el proceso para {rechazo.vacante} y fue rechazada "
                f"en {rechazo.etapa_rechazo}. "
                + (f"No cumplió: {requisitos}. " if requisitos else "")
                + f"Motivo: {rechazo.motivo_rechazo}. "
                "No se puede crear otro proceso con esta cédula."
            )
        cedula = super().clean_cedula()
        ultimo = anteriores.first()
        if ultimo:
            raise forms.ValidationError(
                f"Esta cédula ya tiene un proceso registrado para {ultimo.vacante} "
                f"({ultimo.get_estado_display()}). No se puede crear otro proceso con esta cédula."
            )
        return cedula


class EditarProcesoGerenciaForm(ProcesoForm):
    motivo_cambio = forms.CharField(
        label="Motivo de la actualización",
        min_length=5,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Explique brevemente por qué realiza el cambio"}),
    )

    class Meta(ProcesoForm.Meta):
        fields = ProcesoForm.Meta.fields

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["motivo_cambio"].widget.attrs["class"] = "form-control form-control-lg"


class AccionProcesoForm(forms.Form):
    motivo = forms.CharField(
        label="Motivo obligatorio",
        min_length=5,
        max_length=2000,
        widget=forms.Textarea(attrs={"class": "form-control form-control-lg", "rows": 3}),
    )


class EliminarProcesoForm(forms.Form):
    confirmar = forms.BooleanField(
        label="Entiendo que el candidato y todo su historial de selección se eliminarán definitivamente",
        required=True,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class DecisionForm(forms.Form):
    resultado = forms.ChoiceField(
        choices=Decision.Resultado.choices,
        widget=forms.RadioSelect,
        label="Decisión",
    )
    observacion = forms.CharField(
        label="Observación obligatoria",
        min_length=3,
        max_length=2000,
        widget=forms.Textarea(attrs={
            "class": "form-control form-control-lg",
            "rows": 4,
            "placeholder": "Escriba claramente el motivo de la decisión",
        }),
    )

    def __init__(self, *args, etapa=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.etapa = etapa
        self.requisitos = obtener_requisitos(etapa)
        for requisito in self.requisitos:
            self.fields[f"requisito_{requisito['codigo']}"] = forms.ChoiceField(
                label=requisito["nombre"],
                choices=RESULTADOS_REQUISITO,
                widget=forms.RadioSelect(attrs={"class": "form-check-input", "data-requisito": "true"}),
                error_messages={"required": "Seleccione Cumple o No cumple para este requisito."},
            )

    @property
    def campos_requisitos(self):
        return [self[f"requisito_{requisito['codigo']}"] for requisito in self.requisitos]

    @property
    def tiene_requisitos(self):
        return bool(self.requisitos)

    def clean(self):
        cleaned_data = super().clean()
        verificaciones = {
            requisito["codigo"]: cleaned_data.get(f"requisito_{requisito['codigo']}")
            for requisito in self.requisitos
        }
        cleaned_data["verificaciones"] = verificaciones
        if cleaned_data.get("resultado") and all(
            f"requisito_{requisito['codigo']}" in cleaned_data for requisito in self.requisitos
        ):
            try:
                validar_verificaciones(self.etapa, cleaned_data["resultado"], verificaciones)
            except forms.ValidationError as exc:
                self.add_error("resultado", exc)
        return cleaned_data

    def clean_observacion(self):
        observacion = self.cleaned_data["observacion"].strip()
        if not observacion:
            raise forms.ValidationError("La observación es obligatoria.")
        return observacion


class TrazabilidadFiltroForm(forms.Form):
    SITUACIONES = [
        ("", "Todas"),
        ("vencidos", "Vencidos actualmente"),
        ("por_vencer", "Próximos a vencer"),
        ("con_retrasos", "Con alguna etapa fuera de tiempo"),
        ("sin_retrasos", "Sin etapas fuera de tiempo"),
    ]
    ORDENES = [
        ("recientes", "Llegada más reciente"),
        ("demora", "Mayor tiempo acumulado"),
        ("vencimiento", "Fecha límite más próxima"),
        ("nombre", "Nombre del candidato"),
    ]

    q = forms.CharField(label="Nombre o cédula", required=False)
    fecha_desde = forms.DateField(
        label="Llegada desde", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    fecha_hasta = forms.DateField(
        label="Llegada hasta", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    estado = forms.ChoiceField(
        label="Estado", required=False,
        choices=[("", "Todos")] + list(ProcesoSeleccion.Estado.choices),
    )
    etapa = forms.ChoiceField(
        label="Etapa actual", required=False,
        choices=[("", "Todas")] + list(ProcesoSeleccion.Etapa.choices),
    )
    vacante = forms.CharField(label="Vacante o área", required=False)
    situacion = forms.ChoiceField(label="Cumplimiento", required=False, choices=SITUACIONES)
    orden = forms.ChoiceField(label="Ordenar por", required=False, choices=ORDENES, initial="recientes")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select form-select-lg"
                if isinstance(field.widget, forms.Select)
                else "form-control form-control-lg"
            )

    def clean(self):
        datos = super().clean()
        desde, hasta = datos.get("fecha_desde"), datos.get("fecha_hasta")
        if desde and hasta and desde > hasta:
            raise forms.ValidationError("La fecha inicial no puede ser posterior a la fecha final.")
        return datos


class IndicadoresFiltroForm(forms.Form):
    periodo = forms.ChoiceField(label="Periodo del informe", required=False, choices=[
        ("mensual", "Mensual"), ("semanal", "Semanal"), ("anual", "Anual"),
    ])
    semana = forms.CharField(label="Semana", required=False, widget=forms.TextInput(attrs={"type": "week"}))
    mes = forms.CharField(label="Mes", required=False, widget=forms.TextInput(attrs={"type": "month"}))
    anio = forms.IntegerField(label="Año", required=False, min_value=2000, max_value=2100)
    q = forms.CharField(label="Nombre o cédula", required=False)
    fecha_desde = forms.DateField(
        label="Procesos recibidos desde",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    fecha_hasta = forms.DateField(
        label="Procesos recibidos hasta",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    estado = forms.ChoiceField(
        label="Estado del proceso",
        required=False,
        choices=[("", "Todos")] + list(ProcesoSeleccion.Estado.choices),
    )
    etapa = forms.ChoiceField(
        label="Área o etapa actual",
        required=False,
        choices=[("", "Todas")] + list(ProcesoSeleccion.Etapa.choices),
    )
    vacante = forms.CharField(label="Vacante", required=False)

    def __init__(self, *args, **kwargs):
        hoy = timezone.localdate()
        iso = hoy.isocalendar()
        valores = {"periodo": "mensual", "semana": f"{iso.year}-W{iso.week:02d}", "mes": hoy.strftime("%Y-%m"), "anio": hoy.year}
        entrada = args[0] if args else kwargs.get("data")
        # Mantiene enlaces históricos de reportes; el formulario solo ofrece periodos.
        self.rango_anterior = bool(entrada and "periodo" not in entrada and (entrada.get("fecha_desde") or entrada.get("fecha_hasta")))
        if entrada is not None:
            entrada = entrada.copy()
            for nombre, valor in valores.items():
                entrada.setdefault(nombre, valor)
            if args:
                args = (entrada, *args[1:])
            else:
                kwargs["data"] = entrada
        super().__init__(*args, **kwargs)
        for nombre, valor in valores.items():
            self.fields[nombre].initial = valor
        self.fields["q"].widget.attrs["placeholder"] = "Ejemplo: Ana o 123456"
        self.fields["vacante"].widget.attrs["placeholder"] = "Ejemplo: Recolección"
        self.order_fields(["periodo", "semana", "mes", "anio", "estado", "etapa", "vacante", "q", "fecha_desde", "fecha_hasta"])
        for field in self.fields.values():
            field.widget.attrs["class"] = (
                "form-select form-select-lg"
                if isinstance(field.widget, forms.Select)
                else "form-control form-control-lg"
            )

    def clean(self):
        datos = super().clean()
        if not self.rango_anterior:
            periodo = datos.get("periodo") or "mensual"
            try:
                if periodo == "semanal":
                    anio_semana, numero = datos.get("semana", "").split("-W")
                    inicio = date.fromisocalendar(int(anio_semana), int(numero), 1)
                    fin = inicio + timedelta(days=6)
                elif periodo == "mensual":
                    anio_mes, numero = datos.get("mes", "").split("-")
                    inicio = date(int(anio_mes), int(numero), 1)
                    fin = inicio.replace(day=calendar.monthrange(inicio.year, inicio.month)[1])
                else:
                    inicio = date(datos.get("anio") or 0, 1, 1)
                    fin = inicio.replace(month=12, day=31)
                if not 2000 <= inicio.year <= 2100:
                    raise ValueError
                datos.update(periodo=periodo, fecha_desde=inicio, fecha_hasta=fin)
            except (TypeError, ValueError, OverflowError):
                self.add_error({"semanal": "semana", "mensual": "mes", "anual": "anio"}.get(periodo, "periodo"), "Seleccione un periodo válido entre los años 2000 y 2100.")
        else:
            datos["periodo"] = "personalizado"
        desde, hasta = datos.get("fecha_desde"), datos.get("fecha_hasta")
        if desde and hasta and desde > hasta:
            raise forms.ValidationError("La fecha inicial no puede ser posterior a la fecha final.")
        return datos


class UsuarioOperativoForm(UserCreationForm):
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    rol = forms.ChoiceField(
        label="Rol",
        choices=ROLES_OPERATIVOS,
        help_text="Vinculación registra candidatos. Contratación atiende únicamente la última etapa.",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "rol", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Usuario para ingresar"
        self.fields["username"].help_text = "Use letras y números, sin espacios. Ejemplo: maria.rrhh"
        self.fields["password1"].label = "Contraseña inicial"
        self.fields["password2"].label = "Confirmar contraseña"
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control form-control-lg"
        self.fields["rol"].widget.attrs["class"] = "form-select form-select-lg"

    def save(self, commit=True):
        usuario = super().save(commit=commit)
        if commit:
            usuario.perfil.rol = self.cleaned_data["rol"]
            usuario.perfil.save(update_fields=["rol"])
        return usuario

    def clean_username(self):
        username = self.cleaned_data["username"].strip().casefold()
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("Ya existe una cuenta con este usuario.")
        return username


class CambiarPasswordUsuarioForm(SetPasswordForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(user, *args, **kwargs)
        self.fields["new_password1"].label = "Nueva contraseña"
        self.fields["new_password2"].label = "Confirmar nueva contraseña"
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control form-control-lg", "autocomplete": "new-password"})


class EditarUsuarioOperativoForm(forms.ModelForm):
    rol = forms.ChoiceField(
        label="Rol", choices=ROLES_OPERATIVOS,
        help_text="Vinculación registra candidatos. Contratación atiende únicamente la última etapa.",
    )
    is_active = forms.BooleanField(
        label="Permitir que este usuario ingrese",
        required=False,
        help_text="Desmarque esta opción para bloquear temporalmente la cuenta.",
    )

    class Meta:
        model = User
        fields = ("first_name", "last_name", "username", "rol", "is_active")
        labels = {
            "first_name": "Nombre",
            "last_name": "Apellidos",
            "username": "Usuario para ingresar",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rol"].initial = self.instance.perfil.rol
        if self.instance.perfil.rol in (Perfil.Rol.VINCULACION, Perfil.Rol.CONTRATACION):
            self.fields["is_active"].disabled = True
            self.fields["is_active"].initial = True
            self.fields["is_active"].help_text = (
                f"El acceso de {self.instance.perfil.get_rol_display()} es esencial "
                "y no puede bloquearse manualmente."
            )
        for nombre, field in self.fields.items():
            if nombre == "is_active":
                field.widget.attrs["class"] = "form-check-input"
            elif nombre == "rol":
                field.widget.attrs["class"] = "form-select form-select-lg"
            else:
                field.widget.attrs["class"] = "form-control form-control-lg"

    def clean(self):
        datos = super().clean()
        if datos.get("rol") in (Perfil.Rol.VINCULACION, Perfil.Rol.CONTRATACION):
            datos["is_active"] = True
        return datos

    def save(self, commit=True):
        usuario = super().save(commit=commit)
        if commit:
            usuario.perfil.rol = self.cleaned_data["rol"]
            usuario.perfil.save(update_fields=["rol"])
        return usuario

    def clean_username(self):
        username = self.cleaned_data["username"].strip().casefold()
        if User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Ya existe una cuenta con este usuario.")
        return username
