"""Histórico de eventos por fecha real, sin modificar registros ni su estructura."""
from datetime import date, timedelta

from django.db.models import F, Q
from django.utils import timezone

from .models import CambioGerencia, Decision, ProcesoSeleccion

MAX_INTERVALOS = 200


def _inicio_intervalo(fecha, agrupacion):
    if agrupacion == "semanal":
        return fecha - timedelta(days=fecha.weekday())
    if agrupacion == "anual":
        return fecha.replace(month=1, day=1)
    return fecha.replace(day=1)


def _siguiente(fecha, agrupacion):
    if agrupacion == "semanal":
        return fecha + timedelta(days=7)
    if agrupacion == "anual":
        return date(fecha.year + 1, 1, 1)
    return date(fecha.year + (fecha.month == 12), fecha.month % 12 + 1, 1)


def _fecha_local(valor):
    return timezone.localtime(valor).date() if timezone.is_aware(valor) else valor.date()


def calcular_historico(procesos, datos):
    agrupacion = datos.get("agrupacion") or "mensual"
    salida = {"agrupacion": agrupacion, "filas": [], "sin_fecha": 0, "error": ""}
    if not datos:
        return salida
    # Nunca se filtra por llegada antes de consultar los cierres: una persona
    # recibida en septiembre puede haber sido contratada en octubre.
    candidatos = list(procesos.values_list("pk", "fecha_llegada", "estado"))
    ids = [p[0] for p in candidatos]
    eventos = [(p[1], "recibidos") for p in candidatos]
    finales = Decision.objects.filter(proceso_id__in=ids, vigente=True).filter(
        Q(resultado=Decision.Resultado.RECHAZADO)
        | Q(etapa=ProcesoSeleccion.Etapa.CONTRATACION, resultado=Decision.Resultado.APROBADO)
    ).values_list("proceso_id", "fecha", "resultado")
    cierres = {}
    for proceso_id, fecha, resultado in finales:
        serie = "rechazados" if resultado == Decision.Resultado.RECHAZADO else "contratados"
        cierres[(proceso_id, serie)] = _fecha_local(fecha)
    # Los cambios manuales también tienen fecha propia. No se toma actualizado_en,
    # pues una edición posterior de un teléfono no es la fecha de contratación.
    cambios = CambioGerencia.objects.filter(
        proceso_id__in=ids, tipo=CambioGerencia.Tipo.ACTUALIZACION,
        estado_nuevo__in=[ProcesoSeleccion.Estado.CONTRATADO, ProcesoSeleccion.Estado.RECHAZADO],
    ).exclude(estado_anterior=F("estado_nuevo")).order_by("fecha", "pk")
    manuales = {}
    for cambio in cambios.values_list("proceso_id", "fecha", "estado_nuevo"):
        proceso_id, fecha, estado = cambio
        serie = "contratados" if estado == ProcesoSeleccion.Estado.CONTRATADO else "rechazados"
        manuales[(proceso_id, serie)] = _fecha_local(fecha)
    for clave, fecha in manuales.items():
        cierres.setdefault(clave, fecha)
    eventos.extend((fecha, serie) for (_, serie), fecha in cierres.items())
    desde = datos.get("fecha_desde") or min((f for f, _ in eventos), default=timezone.localdate())
    hasta = datos.get("fecha_hasta") or max((f for f, _ in eventos), default=desde)
    salida.update(desde=desde.isoformat(), hasta=hasta.isoformat())
    conocidos = {proceso_id for proceso_id, _ in cierres}
    salida["sin_fecha"] = sum(estado in (ProcesoSeleccion.Estado.CONTRATADO, ProcesoSeleccion.Estado.RECHAZADO) and proceso_id not in conocidos and llegada <= hasta for proceso_id, llegada, estado in candidatos)
    cursor = _inicio_intervalo(desde, agrupacion)
    intervalos = {}
    while cursor <= hasta:
        if len(intervalos) >= MAX_INTERVALOS:
            salida["error"] = "El rango supera 200 intervalos. Agrupe por mes o año, o reduzca las fechas."
            return salida
        iso = cursor.isocalendar()
        etiqueta = f"S{iso.week:02d} · {iso.year}" if agrupacion == "semanal" else str(cursor.year) if agrupacion == "anual" else cursor.strftime("%m/%Y")
        intervalos[cursor] = {"etiqueta": etiqueta, "inicio": cursor.isoformat(), "recibidos": 0, "contratados": 0, "rechazados": 0}
        try:
            cursor = _siguiente(cursor, agrupacion)
        except (ValueError, OverflowError):
            break
    for fecha, serie in eventos:
        if desde <= fecha <= hasta:
            intervalos[_inicio_intervalo(fecha, agrupacion)][serie] += 1
    salida["filas"] = list(intervalos.values())
    return salida
