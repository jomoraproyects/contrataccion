from django.core.exceptions import PermissionDenied
from django.utils.cache import patch_cache_control

from .models import EventoSeguridad
from .security import registrar_evento


class AccesoPorRolMiddleware:
    """Impide que una cuenta autenticada sin rol operativo vea datos internos."""

    rutas_permitidas = ("/salir/",)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.path not in self.rutas_permitidas:
            rol = getattr(getattr(request.user, "perfil", None), "rol", None)
            if not rol or rol == "SIN_ASIGNAR":
                registrar_evento(
                    request, EventoSeguridad.Tipo.ACCESO_DENEGADO, usuario=request.user,
                    identificador=request.user.username, detalle=f"Cuenta sin rol; ruta {request.path}",
                )
                raise PermissionDenied("Esta cuenta no tiene un rol autorizado.")
        return self.get_response(request)


class RespuestaSeguraMiddleware:
    """Evita cachear datos laborales y añade encabezados defensivos."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if request.user.is_authenticated or request.path == "/ingresar/":
            patch_cache_control(response, no_store=True, no_cache=True, must_revalidate=True, private=True)
            response["Pragma"] = "no-cache"
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        response["Cross-Origin-Resource-Policy"] = "same-origin"
        response["X-Permitted-Cross-Domain-Policies"] = "none"
        return response
