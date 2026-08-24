"""Validación y conversión de entradas de usuario."""

from datetime import datetime


class ErrorValidacion(ValueError):
    """Entrada rechazada con mensaje para el usuario."""


FORMATOS_FECHA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y")


def parse_fecha(texto):
    """Convierte la entrada a date. Rechaza fechas imposibles (31/09)."""
    texto = texto.strip()
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ErrorValidacion(
        "fecha inválida: %r (usar AAAA-MM-DD o DD/MM/AAAA)" % texto
    )


def parse_monto(texto):
    """Entero >= 0 en Bs. Acepta separadores de miles."""
    texto = texto.strip().replace("Bs", "").replace(".", "").replace(",", "").strip()
    if not texto or not texto.lstrip("-").isdigit():
        raise ErrorValidacion("monto inválido: %r" % texto)
    valor = int(texto)
    if valor < 0:
        raise ErrorValidacion("el monto no puede ser negativo")
    return valor


def parse_partidos(texto):
    """Float >= 0; admite decimales (2.5)."""
    texto = texto.strip().replace(",", ".")
    try:
        valor = float(texto)
    except ValueError:
        raise ErrorValidacion("partidos inválidos: %r" % texto)
    if valor < 0:
        raise ErrorValidacion("los partidos no pueden ser negativos")
    return valor
