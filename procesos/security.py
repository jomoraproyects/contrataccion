import ipaddress

from django.conf import settings
from django.utils.crypto import salted_hmac


def obtener_ip_cliente(request):
    candidato = request.META.get("REMOTE_ADDR", "")
    if getattr(settings, "TRUST_PROXY_HEADERS", False):
        candidato = request.META.get("HTTP_X_REAL_IP", candidato)
    try:
        return str(ipaddress.ip_address(candidato))
    except ValueError:
        return None


def hash_identificador(valor):
    valor = (valor or "").strip().casefold()
    return salted_hmac("procesos.identificador", valor).hexdigest() if valor else ""


def registrar_evento(request, tipo, usuario=None, identificador="", detalle=""):
    from .models import EventoSeguridad

    return EventoSeguridad.objects.create(
        tipo=tipo,
        usuario=usuario if getattr(usuario, "pk", None) else None,
        ip=obtener_ip_cliente(request),
        identificador_hash=hash_identificador(identificador),
        detalle=(detalle or "")[:250],
    )
