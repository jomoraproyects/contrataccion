import re

from django.core.exceptions import ValidationError


CEDULA_SEPARADORES = re.compile(r"[.\s-]")
CELULAR_SEPARADORES = re.compile(r"[\s-]")


def normalizar_cedula(valor):
    """Normaliza separadores comunes y rechaza cualquier otro carácter."""
    cedula = CEDULA_SEPARADORES.sub("", (valor or "").strip())
    if not cedula.isdigit() or not 5 <= len(cedula) <= 15:
        raise ValidationError("Escriba una cédula válida de 5 a 15 números.")
    return cedula


def normalizar_celular(valor):
    celular = CELULAR_SEPARADORES.sub("", (valor or "").strip())
    numero = celular[1:] if celular.startswith("+") else celular
    if not numero.isdigit() or not 7 <= len(numero) <= 15:
        raise ValidationError("Escriba un celular válido de 7 a 15 números.")
    return celular
