def user_role(request):
    perfil = getattr(request.user, "perfil", None) if request.user.is_authenticated else None
    rol = getattr(perfil, "rol", None)
    asignaciones_pendientes = 0
    alerta_asignacion = None
    procesos_vencidos_gerencia = 0
    procesos_por_vencer_gerencia = 0
    if rol in ("RRHH", "PSICOLOGIA", "SEGURIDAD", "CONTRATACION"):
        from .models import ProcesoSeleccion, SeguimientoEtapa
        asignaciones = SeguimientoEtapa.objects.filter(
            proceso__activo=True,
            proceso__etapa_actual=rol,
            proceso__estado__in=[ProcesoSeleccion.Estado.EN_CURSO, ProcesoSeleccion.Estado.LISTO_CONTRATACION],
            etapa=rol,
            fin__isnull=True,
        ).select_related("proceso").order_by("fecha_limite")
        asignaciones_pendientes = asignaciones.count()
        alerta_asignacion = asignaciones.first()
    elif rol == "GERENTE":
        from django.utils import timezone
        from .models import SeguimientoEtapa
        abiertos = SeguimientoEtapa.objects.filter(fin__isnull=True, proceso__activo=True)
        procesos_vencidos_gerencia = abiertos.filter(fecha_limite__lt=timezone.now()).count()
        procesos_por_vencer_gerencia = sum(
            not item.esta_vencido and item.dias_restantes <= 1
            for item in abiertos.select_related("proceso")
        )
    return {
        "rol_usuario": rol,
        "rol_usuario_nombre": perfil.get_rol_display() if perfil else None,
        "asignaciones_pendientes": asignaciones_pendientes,
        "alerta_asignacion": alerta_asignacion,
        "procesos_vencidos_gerencia": procesos_vencidos_gerencia,
        "procesos_por_vencer_gerencia": procesos_por_vencer_gerencia,
    }
