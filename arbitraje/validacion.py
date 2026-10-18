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


import math

MAX_MONTO_BS = 100_000
MAX_PARTIDOS_JORNADA = 30.0


def parse_monto(texto):
    """Entero >= 0 en Bs. Acepta separadores de miles, rechaza centavos."""
    limpio = str(texto).strip().replace("Bs", "").strip()
    if not limpio:
        raise ErrorValidacion("monto inválido: %r" % texto)
    if "." in limpio or "," in limpio:
        partes = limpio.replace(",", ".").split(".")
        if len(partes) == 2 and len(partes[1]) in (1, 2):
            raise ErrorValidacion("no se admiten centavos en el monto: %r" % texto)
        limpio = limpio.replace(".", "").replace(",", "")
    if not limpio.lstrip("-").isdigit():
        raise ErrorValidacion("monto inválido: %r" % texto)
    try:
        valor = int(limpio)
    except (ValueError, OverflowError):
        raise ErrorValidacion("monto inválido: %r" % texto)
    if valor < 0:
        raise ErrorValidacion("el monto no puede ser negativo")
    if valor > MAX_MONTO_BS:
        raise ErrorValidacion("monto excede el límite permitido (%d Bs)" % MAX_MONTO_BS)
    return valor


def parse_partidos(texto):
    """Float >= 0 y finito; admite decimales (2.5)."""
    limpio = str(texto).strip().replace(",", ".")
    try:
        valor = float(limpio)
    except ValueError:
        raise ErrorValidacion("partidos inválidos: %r" % texto)
    if math.isnan(valor) or math.isinf(valor):
        raise ErrorValidacion("partidos inválidos: %r" % texto)
    if valor < 0:
        raise ErrorValidacion("los partidos no pueden ser negativos")
    if valor > MAX_PARTIDOS_JORNADA:
        raise ErrorValidacion("partidos exceden el máximo permitido: %r" % texto)
    return valor
