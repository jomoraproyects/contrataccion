import math
from datetime import timedelta

from django.contrib.auth import logout
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView
from django.db import transaction
from django.utils import timezone

from .models import EventoSeguridad, Perfil
from .security import obtener_ip_cliente, registrar_evento


class LoginSeguroView(LoginView):
    """Inicio de sesión con mensajes no enumerables y límites por cuenta e IP."""

    template_name = "registration/login.html"
    redirect_authenticated_user = True
    max_intentos = 5
    max_intentos_ip = 20
    bloqueo_segundos = 15 * 60
    roles_sin_bloqueo = (Perfil.Rol.GERENTE, Perfil.Rol.CONTRATACION)

    def _usuario_escrito(self):
        return self.request.POST.get("username", "").strip().casefold()

    def _usuario_registrado(self):
        return User.objects.select_related("perfil").filter(username__iexact=self._usuario_escrito()).first()

    def _es_acceso_esencial(self, usuario):
        """Gerencia y Contratacion nunca quedan sin acceso por intentos fallidos."""
        return bool(usuario and usuario.is_active and usuario.perfil.rol in self.roles_sin_bloqueo)

    def _limpiar_bloqueo_esencial(self, usuario):
        if usuario and (usuario.perfil.intentos_fallidos or usuario.perfil.bloqueado_hasta):
            usuario.perfil.limpiar_bloqueo()

    def _ip_bloqueada(self):
        ip = obtener_ip_cliente(self.request)
        if not ip:
            return False
        desde = timezone.now() - timedelta(seconds=self.bloqueo_segundos)
        return EventoSeguridad.objects.filter(
            tipo=EventoSeguridad.Tipo.LOGIN_FALLIDO, ip=ip, fecha__gte=desde
        ).count() >= self.max_intentos_ip

    def _respuesta_bloqueada(self, form, segundos=None):
        segundos = segundos or self.bloqueo_segundos
        contexto = self.get_context_data(
            form=form, acceso_bloqueado=True,
            minutos_bloqueo=max(1, math.ceil(segundos / 60)),
        )
        respuesta = self.render_to_response(contexto, status=429)
        respuesta["Retry-After"] = str(max(1, int(segundos)))
        return respuesta

    def _respuesta_incorrecta(self, form, intentos_restantes=None):
        return self.render_to_response(self.get_context_data(
            form=form, credenciales_invalidas=True,
            intentos_restantes=intentos_restantes,
        ))

    def dispatch(self, request, *args, **kwargs):
        if request.method == "POST":
            usuario = self._usuario_registrado()
            acceso_esencial = self._es_acceso_esencial(usuario)
            if acceso_esencial:
                self._limpiar_bloqueo_esencial(usuario)
            elif self._ip_bloqueada():
                return self._respuesta_bloqueada(self.get_form())
            if not acceso_esencial and usuario and usuario.perfil.bloqueo_seguridad_activo:
                segundos = (usuario.perfil.bloqueado_hasta - timezone.now()).total_seconds()
                return self._respuesta_bloqueada(self.get_form(), segundos)
            if not acceso_esencial and usuario and usuario.perfil.bloqueado_hasta:
                usuario.perfil.limpiar_bloqueo()
        return super().dispatch(request, *args, **kwargs)

    def form_invalid(self, form):
        identificador = self._usuario_escrito()
        usuario = self._usuario_registrado()
        registrar_evento(
            self.request, EventoSeguridad.Tipo.LOGIN_FALLIDO,
            usuario=usuario, identificador=identificador, detalle="Credenciales no válidas",
        )
        if not identificador or not self.request.POST.get("password") or not usuario or not usuario.is_active:
            return self._respuesta_incorrecta(form)

        if self._es_acceso_esencial(usuario):
            self._limpiar_bloqueo_esencial(usuario)
            return self._respuesta_incorrecta(form)

        with transaction.atomic():
            perfil = Perfil.objects.select_for_update().get(usuario=usuario)
            perfil.intentos_fallidos += 1
            if perfil.intentos_fallidos >= self.max_intentos:
                perfil.bloqueado_hasta = timezone.now() + timedelta(seconds=self.bloqueo_segundos)
            perfil.save(update_fields=["intentos_fallidos", "bloqueado_hasta"])
            if perfil.bloqueo_seguridad_activo:
                registrar_evento(
                    self.request, EventoSeguridad.Tipo.CUENTA_BLOQUEADA,
                    usuario=usuario, identificador=identificador, detalle="Cinco intentos fallidos",
                )
                return self._respuesta_bloqueada(form)
            return self._respuesta_incorrecta(form, self.max_intentos - perfil.intentos_fallidos)

    def form_valid(self, form):
        usuario = form.get_user()
        if usuario.perfil.rol == Perfil.Rol.SIN_ASIGNAR:
            registrar_evento(
                self.request, EventoSeguridad.Tipo.ACCESO_DENEGADO,
                usuario=usuario, identificador=usuario.username, detalle="Cuenta sin rol autorizado",
            )
            logout(self.request)
            return self._respuesta_incorrecta(form)
        usuario.perfil.limpiar_bloqueo()
        registrar_evento(
            self.request, EventoSeguridad.Tipo.LOGIN_CORRECTO,
            usuario=usuario, identificador=usuario.username,
        )
        return super().form_valid(form)
