import math
from datetime import time, timedelta
from functools import lru_cache

import holidays
from django.utils import timezone


HORA_INICIO_LABORAL = time(7, 0)
HORA_FIN_LABORAL = time(16, 0)
SEGUNDOS_JORNADA_LABORAL = 9 * 60 * 60


@lru_cache(maxsize=32)
def festivos_colombia(anio):
    """Devuelve los festivos oficiales de Colombia para un año."""
    return holidays.country_holidays("CO", years=anio, language="es")


def es_dia_habil(fecha):
    """Un día hábil no es sábado, domingo ni festivo oficial colombiano."""
    return fecha.weekday() < 5 and fecha not in festivos_colombia(fecha.year)


def sumar_dias_habiles(inicio, cantidad):
    """Suma jornadas laborales de nueve horas, de 7:00 a 16:00."""
    if cantidad < 0:
        raise ValueError("La cantidad de días hábiles no puede ser negativa.")
    if cantidad == 0:
        return inicio
    return sumar_segundos_habiles(inicio, cantidad * SEGUNDOS_JORNADA_LABORAL)


def dias_habiles_restantes(ahora, fecha_limite):
    """Devuelve jornadas laborales restantes; un valor negativo indica mora."""
    if ahora <= fecha_limite:
        segundos = segundos_habiles_entre(ahora, fecha_limite)
        return math.ceil(segundos / SEGUNDOS_JORNADA_LABORAL)
    segundos = segundos_habiles_entre(fecha_limite, ahora)
    return -max(1, math.ceil(segundos / SEGUNDOS_JORNADA_LABORAL))


def segundos_habiles_entre(inicio, fin):
    """Cuenta segundos únicamente de 7:00 a 16:00 en días hábiles."""
    if fin <= inicio:
        return 0
    actual = timezone.localtime(inicio) if timezone.is_aware(inicio) else inicio
    limite = timezone.localtime(fin) if timezone.is_aware(fin) else fin
    total = 0
    cursor = actual.date()
    while cursor <= limite.date():
        if es_dia_habil(cursor):
            inicio_jornada = actual.replace(
                year=cursor.year, month=cursor.month, day=cursor.day,
                hour=HORA_INICIO_LABORAL.hour, minute=0, second=0, microsecond=0,
            )
            fin_jornada = inicio_jornada.replace(hour=HORA_FIN_LABORAL.hour)
            tramo_inicio = max(actual, inicio_jornada)
            tramo_fin = min(limite, fin_jornada)
            if tramo_fin > tramo_inicio:
                total += int((tramo_fin - tramo_inicio).total_seconds())
        cursor += timedelta(days=1)
    return total


def sumar_segundos_habiles(inicio, segundos):
    """Desplaza una fecha consumiendo segundos de 7:00 a 16:00."""
    actual = timezone.localtime(inicio) if timezone.is_aware(inicio) else inicio
    restantes = max(0, int(segundos))
    while restantes:
        inicio_jornada = actual.replace(
            hour=HORA_INICIO_LABORAL.hour, minute=0, second=0, microsecond=0,
        )
        fin_jornada = actual.replace(
            hour=HORA_FIN_LABORAL.hour, minute=0, second=0, microsecond=0,
        )
        if not es_dia_habil(actual.date()) or actual >= fin_jornada:
            actual = inicio_jornada + timedelta(days=1)
            continue
        if actual < inicio_jornada:
            actual = inicio_jornada
        disponibles = int((fin_jornada - actual).total_seconds())
        if restantes <= disponibles:
            return actual + timedelta(seconds=restantes)
        restantes -= disponibles
        actual = inicio_jornada + timedelta(days=1)
    return actual
