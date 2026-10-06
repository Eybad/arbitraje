"""Entrada interactiva con defaults, validación y reintento."""

import os
import re
import sys
from datetime import date

from .modelos import Estado, normalizar
from .validacion import parse_fecha, parse_monto, parse_partidos, ErrorValidacion


def _use_color():
    return not ("NO_COLOR" in os.environ or not sys.stdout.isatty())


def _cprint(texto):
    if _use_color():
        try:
            from rich.console import Console
            Console().print(texto, markup=True, crop=False, overflow="ignore", soft_wrap=True)
            return
        except Exception:
            pass
    # strip markup
    print(re.sub(r"\[/?[^\]]*\]", "", texto))


def _cerr(texto):
    _cprint(f"[red]{texto}[/]")


def _leer(prompt):
    try:
        if _use_color():
            try:
                from rich.console import Console
                # prompt en amarillo, con rich markup si viene
                Console().print(f"[yellow]{prompt}[/]", end="", markup=True, soft_wrap=True)
                return input().strip()
            except Exception:
                pass
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
            _cerr("  %s" % error)


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
            _cerr("  %s" % error)


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
            _cerr("  %s" % error)


def _fmt_float(valor):
    if valor == int(valor):
        return str(int(valor))
    return str(valor)


def pedir_estado(default=Estado.ARBITRADO):
    # Camino flechas nativas + fallback numerado. Sin TTY devuelve
    # default (caso seguro con default) en vez de fallar.
    try:
        from .selector import seleccionar
        estados = list(Estado)
        elegido = seleccionar(
            "Estado", estados,
            formato=lambda e: e.value,
            default=default if default in estados else estados[0],
            texto="Jornada: qué ocurrió ese día. Solo ARBITRADO genera dinero.",
            hint='ejecutar en terminal (ej arbitraje add en Termux)',
            usar_default_sin_tty=True,
        )
        if elegido is not None:
            return elegido
        return default
    except SystemExit:
        raise
    except Exception:
        pass
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
        _cerr("  estado inválido. Opciones: %s" % nombres)


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
        _cerr("  certeza inválida. Opciones: %s" % ", ".join(opciones))


def confirmar(prompt, default=True):
    # Flechas Sí/No nativas. Sin TTY: fail-closed con error+hint
    # (no auto-confirma un Guardar/Borrar en pipe/CI).
    try:
        from .selector import confirmar_flechas
        resultado = confirmar_flechas(
            prompt, default=default,
            hint="confirmar en terminal (ej ejecutar en Termux sin pipe)",
        )
        if resultado is None:
            # Esc/q en diálogo = cancelar → False seguro (no guarda/borra)
            return False
        return resultado
    except SystemExit:
        raise
    except Exception:
        pass
    sugerencia = "S/n" if default else "s/N"
    while True:
        texto = _leer("%s [%s]: " % (prompt, sugerencia)).lower()
        if not texto:
            return default
        if texto in ("s", "si"):
            return True
        if texto in ("n", "no"):
            return False
        _cerr("  responder s o n")


def elegir_de_lista(prompt, opciones, formato=str):
    """opciones: lista de valores; devuelve el elegido o None si cancela."""
    if not opciones:
        return None
    # Delegar en selector (flechas opt-in + fallback Panel Rich).
    try:
        from .selector import seleccionar
        return seleccionar(
            prompt, list(opciones), formato=formato, default=None,
            texto="↑↓ + Enter elige · Esc cancela",
            hint="elegir en terminal (ej ejecutar en Termux sin pipe)",
            usar_default_sin_tty=False,
        )
    except SystemExit:
        raise
    except Exception:
        pass
    for indice, opcion in enumerate(opciones, 1):
        if _use_color():
            _cprint(f"  [cyan]{indice:2d})[/] [white]{formato(opcion)}[/]")
        else:
            print("  %2d) %s" % (indice, formato(opcion)))
    while True:
        texto = _leer("%s [1-%d, vacío cancela]: " % (prompt, len(opciones)))
        if not texto:
            return None
        if texto.isdigit() and len(texto) <= 6:
            try:
                numero = int(texto)
            except ValueError:
                numero = 0
            if 1 <= numero <= len(opciones):
                return opciones[numero - 1]
        _cerr("  opción inválida")
