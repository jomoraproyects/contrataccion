from datetime import timedelta

from django.urls import reverse
from django.utils import timezone

from .models import Perfil, ProcesoSeleccion, SeguimientoEtapa


def seguimientos_notificables(usuario):
    """Seguimientos abiertos que el usuario puede atender o supervisar."""
    rol = getattr(getattr(usuario, "perfil", None), "rol", None)
    queryset = SeguimientoEtapa.objects.filter(
        proceso__activo=True,
        proceso__estado__in=(
            ProcesoSeleccion.Estado.EN_CURSO,
            ProcesoSeleccion.Estado.LISTO_CONTRATACION,
        ),
        fin__isnull=True,
    ).select_related("proceso")
    if rol == Perfil.Rol.GERENTE:
        return queryset.order_by("fecha_limite")
    if rol in ProcesoSeleccion.Etapa.values:
        return queryset.filter(
            proceso__etapa_actual=rol,
            etapa=rol,
        ).order_by("fecha_limite")
    return queryset.none()


def construir_notificaciones(usuario):
    ahora = timezone.now()
    recientes_desde = ahora - timedelta(hours=24)
    notificaciones = []
    for seguimiento in seguimientos_notificables(usuario)[:50]:
        if seguimiento.esta_vencido:
            tipo = "vencido"
            nivel = "danger"
            titulo = "Proceso vencido"
        elif seguimiento.dias_restantes <= 1:
            tipo = "por_vencer"
            nivel = "warning"
            titulo = "Proceso próximo a vencer"
        elif seguimiento.inicio >= recientes_desde:
            tipo = "nuevo"
            nivel = "info"
            titulo = "Nuevo proceso asignado"
        else:
            tipo = "pendiente"
            nivel = "primary"
            titulo = "Proceso pendiente"
        notificaciones.append({
            "id": seguimiento.pk,
            "tipo": tipo,
            "nivel": nivel,
            "titulo": titulo,
            "candidato": seguimiento.proceso.nombre_completo,
            "vacante": seguimiento.proceso.vacante,
            "etapa": seguimiento.get_etapa_display(),
            "estado_plazo": seguimiento.estado_plazo,
            "fecha_limite": seguimiento.fecha_limite,
            "url": reverse("procesos:detalle", args=[seguimiento.proceso_id]),
        })
    return notificaciones
