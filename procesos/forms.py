import re

from django import forms
from django.contrib.auth.forms import SetPasswordForm, UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone

from .models import Decision, Perfil, ProcesoSeleccion


ROLES_OPERATIVOS = [
    choice for choice in Perfil.Rol.choices
    if choice[0] not in (Perfil.Rol.GERENTE, Perfil.Rol.SIN_ASIGNAR)
]


class ProcesoForm(forms.ModelForm):
    class Meta:
        model = ProcesoSeleccion
        fields = ["nombre", "apellidos", "cedula", "celular", "fecha_llegada", "vacante"]
        widgets = {
            "fecha_llegada": forms.DateInput(attrs={"type": "date"}),
            "nombre": forms.TextInput(attrs={"autofocus": True}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs["class"] = "form-control form-control-lg"

    def clean_cedula(self):
        cedula = re.sub(r"[.\s-]", "", self.cleaned_data["cedula"])
        if not cedula.isdigit() or not 5 <= len(cedula) <= 15:
            raise forms.ValidationError("Escriba una cédula válida de 5 a 15 números.")
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
        celular = re.sub(r"[\s-]", "", self.cleaned_data["celular"])
        numero = celular[1:] if celular.startswith("+") else celular
        if not numero.isdigit() or not 7 <= len(numero) <= 15:
            raise forms.ValidationError("Escriba un celular válido de 7 a 15 números.")
        return celular

    def clean_fecha_llegada(self):
        fecha = self.cleaned_data["fecha_llegada"]
        if fecha > timezone.localdate():
            raise forms.ValidationError("La fecha de llegada no puede estar en el futuro.")
        return fecha


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
        widget=forms.Textarea(attrs={"class": "form-control form-control-lg", "rows": 3}),
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
        widget=forms.Textarea(attrs={
            "class": "form-control form-control-lg",
            "rows": 4,
            "placeholder": "Escriba claramente el motivo de la decisión",
        }),
    )

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


class UsuarioOperativoForm(UserCreationForm):
    first_name = forms.CharField(label="Nombre", max_length=150)
    last_name = forms.CharField(label="Apellidos", max_length=150)
    rol = forms.ChoiceField(
        label="Rol",
        choices=ROLES_OPERATIVOS,
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
    rol = forms.ChoiceField(label="Rol", choices=ROLES_OPERATIVOS)
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
        for nombre, field in self.fields.items():
            field.widget.attrs["class"] = "form-check-input" if nombre == "is_active" else "form-control form-control-lg"

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
