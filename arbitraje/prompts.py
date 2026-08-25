"""Entrada interactiva con defaults, validación y reintento."""

from datetime import date

from .modelos import Estado, normalizar
from .validacion import parse_fecha, parse_monto, parse_partidos, ErrorValidacion


def _leer(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(130)


def pedir_texto(prompt, default=""):
    respuesta = _leer("%s [%s]: " % (prompt, default) if default else "%s: " % prompt)
    return respuesta if respuesta else default


def pedir_fecha(prompt, default=None):
    while True:
        texto = pedir_texto(prompt, default.isoformat() if default else "")
        if not texto:
            return default
        try:
            return parse_fecha(texto)
        except ErrorValidacion as error:
            print("  %s" % error)


def pedir_monto(prompt, default=None, permitir_nulo=False):
    """Entero >= 0. '-' devuelve None (dato desconocido) si permitir_nulo."""
    sufijo = "[%s]" % (default if default is not None else "")
    while True:
        texto = _leer("%s %s: " % (prompt, sufijo))
        if not texto and default is not None:
            return default
        if texto == "-" and permitir_nulo:
            return None
        try:
            return parse_monto(texto)
        except ErrorValidacion as error:
            print("  %s" % error)


def pedir_partidos(prompt, default=None, permitir_nulo=False):
    sufijo = "[%s]" % ("" if default is None else _fmt_float(default))
    while True:
        texto = _leer("%s %s: " % (prompt, sufijo))
        if not texto and default is not None:
            return default
        if texto == "-" and permitir_nulo:
            return None
        try:
            return parse_partidos(texto)
        except ErrorValidacion as error:
            print("  %s" % error)


def _fmt_float(valor):
    if valor == int(valor):
        return str(int(valor))
    return str(valor)


def pedir_estado(default=Estado.ARBITRADO):
    nombres = ", ".join(e.value for e in Estado)
    while True:
        texto = _leer("Estado [%s]: " % default.value)
        if not texto:
            return default
        objetivo = normalizar(texto)
        for estado in Estado:
            if normalizar(estado.value) == objetivo:
                return estado
        coincidencias = [e for e in Estado if normalizar(e.value).startswith(objetivo)]
        if len(coincidencias) == 1:
            return coincidencias[0]
        print("  estado inválido. Opciones: %s" % nombres)


def pedir_certeza(default="CONFIRMADO"):
    opciones = ("CONFIRMADO", "PROBABLE", "DUDOSO")
    while True:
        texto = _leer("Certeza [%s]: " % default)
        if not texto:
            return default
        objetivo = normalizar(texto)
        for opcion in opciones:
            if normalizar(opcion).startswith(objetivo):
                return opcion
        print("  certeza inválida. Opciones: %s" % ", ".join(opciones))


def confirmar(prompt, default=True):
    sugerencia = "S/n" if default else "s/N"
    while True:
        texto = _leer("%s [%s]: " % (prompt, sugerencia)).lower()
        if not texto:
            return default
        if texto in ("s", "si"):
            return True
        if texto in ("n", "no"):
            return False
        print("  responder s o n")


def elegir_de_lista(prompt, opciones, formato=str):
    """opciones: lista de valores; devuelve el elegido o None si cancela."""
    if not opciones:
        return None
    for indice, opcion in enumerate(opciones, 1):
        print("  %2d) %s" % (indice, formato(opcion)))
    while True:
        texto = _leer("%s [1-%d, vacío cancela]: " % (prompt, len(opciones)))
        if not texto:
            return None
        if texto.isdigit() and 1 <= int(texto) <= len(opciones):
            return opciones[int(texto) - 1]
        print("  opción inválida")
