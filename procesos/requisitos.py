"""Requisitos de cada etapa y validación común para formularios y decisiones."""

from django.core.exceptions import ValidationError


CUMPLE = "CUMPLE"
NO_CUMPLE = "NO_CUMPLE"
RESULTADOS_REQUISITO = ((CUMPLE, "Cumple"), (NO_CUMPLE, "No cumple"))

REQUISITOS_ETAPA = {
    "RRHH": (
        {"codigo": "antecedentes_judiciales", "nombre": "Antecedentes judiciales"},
        {"codigo": "procuraduria", "nombre": "Antecedentes de la Procuraduría"},
        {"codigo": "contraloria", "nombre": "Antecedentes de la Contraloría"},
        {"codigo": "medidas_correctivas", "nombre": "Medidas correctivas"},
        {"codigo": "redam", "nombre": "REDAM"},
    ),
    "PSICOLOGIA": (
        {"codigo": "entrevista", "nombre": "Entrevista"},
        {"codigo": "prueba_psicotecnica", "nombre": "Prueba psicotécnica"},
    ),
    "SEGURIDAD": ({"codigo": "examen_ingreso", "nombre": "Examen de ingreso"},),
}


def obtener_requisitos(etapa):
    """Devuelve copias para evitar que un consumidor modifique el catálogo común."""
    return tuple(dict(requisito) for requisito in REQUISITOS_ETAPA.get(etapa, ()))


def validar_verificaciones(etapa, resultado, verificaciones):
    """Valida respuestas explícitas y produce una copia histórica de los requisitos.

    No marcar un requisito no significa que haya fallado: cada requisito debe
    responderse como CUMPLE o NO_CUMPLE antes de aprobar o rechazar.
    """
    requisitos = obtener_requisitos(etapa)
    if not requisitos:
        if verificaciones not in (None, {}):
            raise ValidationError("Esta etapa no tiene una lista de verificaciones.")
        return {}

    if not isinstance(verificaciones, dict):
        raise ValidationError("Debe responder todos los requisitos de la etapa antes de decidir.")
    codigos = {requisito["codigo"] for requisito in requisitos}
    if set(verificaciones) != codigos or any(
        valor not in (CUMPLE, NO_CUMPLE) for valor in verificaciones.values()
    ):
        raise ValidationError("Responda cada requisito con Cumple o No cumple antes de decidir.")

    no_cumplidos = [requisito["nombre"] for requisito in requisitos if verificaciones[requisito["codigo"]] == NO_CUMPLE]
    if resultado == "APROBADO" and no_cumplidos:
        raise ValidationError("Para aprobar, todos los requisitos deben estar marcados como Cumple.")
    if resultado == "RECHAZADO" and not no_cumplidos:
        raise ValidationError("Para rechazar, marque al menos un requisito como No cumple y explique el motivo.")
    if resultado not in ("APROBADO", "RECHAZADO"):
        raise ValidationError("La decisión no es válida.")

    return {
        "version": 1,
        "requisitos": [
            {**requisito, "resultado": verificaciones[requisito["codigo"]]}
            for requisito in requisitos
        ],
    }
