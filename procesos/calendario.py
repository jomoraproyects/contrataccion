from datetime import timedelta
from functools import lru_cache

import holidays
from django.utils import timezone


@lru_cache(maxsize=32)
def festivos_colombia(anio):
    """Devuelve los festivos oficiales de Colombia para un año."""
    return holidays.country_holidays("CO", years=anio, language="es")


def es_dia_habil(fecha):
    """Un día hábil no es sábado, domingo ni festivo oficial colombiano."""
    return fecha.weekday() < 5 and fecha not in festivos_colombia(fecha.year)


def sumar_dias_habiles(inicio, cantidad):
    """Suma días hábiles conservando la hora local de asignación."""
    if cantidad < 0:
        raise ValueError("La cantidad de días hábiles no puede ser negativa.")
    actual = timezone.localtime(inicio) if timezone.is_aware(inicio) else inicio
    agregados = 0
    while agregados < cantidad:
        actual += timedelta(days=1)
        if es_dia_habil(actual.date()):
            agregados += 1
    return actual


def dias_habiles_restantes(ahora, fecha_limite):
    """Cuenta días hábiles pendientes; un valor negativo indica vencimiento."""
    ahora_local = timezone.localtime(ahora) if timezone.is_aware(ahora) else ahora
    limite_local = timezone.localtime(fecha_limite) if timezone.is_aware(fecha_limite) else fecha_limite
    if ahora_local <= limite_local:
        cursor = ahora_local.date()
        restantes = 0
        while cursor < limite_local.date():
            cursor += timedelta(days=1)
            if es_dia_habil(cursor):
                restantes += 1
        return restantes

    cursor = limite_local.date()
    vencidos = 0
    while cursor < ahora_local.date():
        cursor += timedelta(days=1)
        if es_dia_habil(cursor):
            vencidos += 1
    return -max(1, vencidos)


def segundos_habiles_entre(inicio, fin):
    """Cuenta tiempo calendario únicamente dentro de fechas hábiles colombianas."""
    if fin <= inicio:
        return 0
    actual = timezone.localtime(inicio) if timezone.is_aware(inicio) else inicio
    limite = timezone.localtime(fin) if timezone.is_aware(fin) else fin
    total = 0
    while actual < limite:
        siguiente = actual.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        tramo_fin = min(siguiente, limite)
        if es_dia_habil(actual.date()):
            total += max(0, int((tramo_fin - actual).total_seconds()))
        actual = tramo_fin
    return total


def sumar_segundos_habiles(inicio, segundos):
    """Desplaza una fecha consumiendo segundos solo en días hábiles."""
    actual = timezone.localtime(inicio) if timezone.is_aware(inicio) else inicio
    restantes = max(0, int(segundos))
    while restantes:
        if not es_dia_habil(actual.date()):
            actual = actual.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
            continue
        siguiente = actual.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        disponibles = int((siguiente - actual).total_seconds())
        if restantes <= disponibles:
            return actual + timedelta(seconds=restantes)
        restantes -= disponibles
        actual = siguiente
    return actual
