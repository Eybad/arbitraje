"""Backend de selección/navegación 100% stdlib, sin dependencias.

Contrato:
- Rich = presentación (tablas, Panel estático).
- Este módulo = interacción con flechas en modo crudo tty/termios.
  Cero pip. Si TERM=dumb o no hay TTY de salida, fallback numerado.
- prompts.py = API de dominio. Este módulo no conoce Estado/Concepto.

Reglas:
- Solo ↑↓ + Enter (+ dígitos como atajo). Enter = default.
  Esc/q = cancela (None). Ctrl-C/EOF = SystemExit(130).
- Sin stdin TTY = error + hint a stderr, exit 2 (fail-closed).
- Borrado con SI literal queda fuera de flechas (ver menu.eliminar).
"""

import os
import sys
import tty  # Ansioso a propósito: tty hace `from termios import *` al
             # importarse. Si su primera importación ocurriera dentro de un
             # test con termios mockeado, congelaría el mock para siempre.

_MAX_VISIBLE = 8


def es_tty():
    """Hay terminal interactiva para leer flechas."""
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def _salida_tty():
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def _colores_activos():
    try:
        if os.environ.get("NO_COLOR", "") != "":
            return False
        if os.environ.get("TERM", "") == "dumb":
            return False
        return _salida_tty()
    except Exception:
        return False


def _error_sin_tty(hint):
    print("error: se necesita terminal interactiva", file=sys.stderr)
    if hint:
        print("hint: %s" % hint, file=sys.stderr)
    raise SystemExit(2)


def seleccionar(titulo, opciones, formato=str, default=None, texto="",
                hint="", usar_default_sin_tty=False):
    """Elige un elemento de opciones con flechas nativas.

    Devuelve el valor elegido o None si cancela (Esc/q/vacío sin default).
    EOF/Ctrl-C -> SystemExit(130) como el resto del proyecto.
    """
    opciones = list(opciones or [])
    if not opciones:
        return None
    if default is not None and default not in opciones:
        default = None

    if not es_tty():
        if usar_default_sin_tty and default is not None:
            return default
        _error_sin_tty(hint or "ejecutar en terminal (ej arbitraje en Termux)")

    # Sin salida TTY o TERM=dumb: no tiene sentido el repintado ANSI.
    if not _salida_tty() or os.environ.get("TERM", "") == "dumb":
        return _fallback_numerado(titulo, opciones, formato, default)

    try:
        return _nativo(titulo, opciones, formato, default, texto)
    except SystemExit:
        raise
    except Exception:
        return _fallback_numerado(titulo, opciones, formato, default)


def seleccionar_clave(titulo, pares, default_clave=None, texto="", hint="",
                      usar_default_sin_tty=False):
    """pares: [(clave, etiqueta)]. Devuelve la clave elegida o None."""
    pares = list(pares or [])
    if not pares:
        return None
    claves = [c for c, _ in pares]
    etiquetas = {c: e for c, e in pares}
    if default_clave is not None and default_clave not in claves:
        default_clave = None
    return seleccionar(
        titulo, claves,
        formato=lambda c: etiquetas.get(c, str(c)),
        default=default_clave, texto=texto, hint=hint,
        usar_default_sin_tty=usar_default_sin_tty,
    )


def confirmar_flechas(prompt, default=True, hint=""):
    """Sí/No con flechas nativas. Sin TTY: fail-closed con error+hint."""
    if not es_tty():
        _error_sin_tty(hint or "confirmar en terminal (ej ejecutar en Termux)")
    elegido = seleccionar(
        prompt, [True, False],
        formato=lambda v: "Sí" if v else "No",
        default=default if default in (True, False) else True,
        texto="↑↓ + Enter elige · Esc cancela",
        hint=hint, usar_default_sin_tty=False,
    )
    return elegido


# Alias para el plan (mismo backend nativo).
confirmar_nativo = confirmar_flechas


# ---------------------------------------------------------------- nativo

def _leer_tecla():
    """Lee una tecla en modo crudo. Devuelve token: UP/DOWN/ENTER/ESC/Q/DIGITO/...

    Usa os.read sobre el fd (sin buffer de usuario): sys.stdin.read(1)
    tragaba la secuencia completa al buffer de TextIOWrapper y el select
    posterior ya no veía los bytes -> toda flecha se parseaba como ESC.
    """
    import termios
    fd = sys.stdin.fileno()
    attrs = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        primero = os.read(fd, 1)
        if primero in (b"", None):
            raise EOFError
        if primero == b"\x03":
            raise KeyboardInterrupt
        if primero in (b"\r", b"\n"):
            return ("ENTER", None)
        if primero in (b"q", b"Q"):
            return ("Q", None)
        if primero == b"\x7f":
            return ("BACKSPACE", None)
        try:
            ch = primero.decode("ascii")
        except Exception:
            ch = ""
        if ch.isdigit():
            return ("DIGITO", ch)
        if primero == b"\x1b":
            # Secuencias de flecha: normal ESC [ A/B y modo aplicación
            # ESC O A/B (Termux/xterm con DECCKM). Se leen los bytes de
            # continuación disponibles; Esc solo (sin más bytes) = cancela.
            # Desconocido = OTRA (ignorar, nunca cerrar el programa).
            import select as _select
            import time as _time
            resto = b""
            plazo = _time.monotonic() + 0.15
            while len(resto) < 4:
                queda = plazo - _time.monotonic()
                if queda <= 0:
                    break
                listos, _, _ = _select.select([fd], [], [], queda)
                if not listos:
                    break
                trozo = os.read(fd, 1)
                if not trozo:
                    break
                resto += trozo
                if resto in (b"[A", b"[B", b"[C", b"[D", b"[H", b"[F",
                            b"OA", b"OB", b"OC", b"OD", b"OH", b"OF"):
                    break
                if len(resto) >= 2 and resto[:1] == b"[" and resto[-1:].isalpha():
                    break
            if resto in (b"[A", b"OA"):
                return ("UP", None)
            if resto in (b"[B", b"OB"):
                return ("DOWN", None)
            if resto == b"":
                return ("ESC", None)
            return ("OTRA", None)
        return ("OTRA", None)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, attrs)


def _limpiar(txt, largo=0):
    """Quita ANSI/control para redraw seguro. largo>0 trunca."""
    txt = str(txt).replace("\x1b", "").replace("\r", " ").replace("\n", " ")
    if largo > 0 and len(txt) > largo:
        txt = txt[:largo - 1] + "…"
    return txt


def _nativo(titulo, opciones, formato, default, texto):
    color = _colores_activos()
    n = len(opciones)
    try:
        idx = opciones.index(default) if default is not None else 0
    except ValueError:
        idx = 0
    buf = ""
    import shutil
    altura = _MAX_VISIBLE
    try:
        cols = shutil.get_terminal_size().columns
    except Exception:
        cols = 80
    if cols < 20:
        cols = 80

    def etiqueta(i):
        try:
            txt = str(formato(opciones[i]))
        except Exception:
            txt = str(opciones[i])
        return _limpiar(txt, cols - 8)

    def bloque(inicio):
        lineas = []
        titulo_limpio = _limpiar(titulo, cols)
        if color:
            lineas.append("\x1b[35;1m%s\x1b[0m" % titulo_limpio)
        else:
            lineas.append(titulo_limpio)
        ayuda = _limpiar(texto or "↑↓ + Enter elige · Esc cancela", cols)
        if default is not None:
            try:
                ayuda = "%s · Enter=%s" % (ayuda, _limpiar(formato(default), cols))
            except Exception:
                pass
        lineas.append(ayuda)
        fin = min(n, inicio + altura)
        if inicio > 0:
            lineas.append("  … %d más arriba" % inicio)
        for i in range(inicio, fin):
            marca = ">" if i == idx else " "
            if color and i == idx:
                lineas.append("\x1b[36m%s %d) %s\x1b[0m" % (marca, i + 1, etiqueta(i)))
            else:
                lineas.append("%s %d) %s" % (marca, i + 1, etiqueta(i)))
        if fin < n:
            lineas.append("  … %d más abajo" % (n - fin))
        if buf:
            lineas.append("  filtro: %s" % buf)
        return lineas

    inicio = max(0, min(idx - altura + 1, n - altura)) if n > altura else 0
    if idx < inicio:
        inicio = idx
    lineas = bloque(inicio)
    for ln in lineas:
        print(ln)
    alto_bloque = len(lineas)

    while True:
        try:
            tipo, valor = _leer_tecla()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(130)
        if tipo == "UP":
            idx = (idx - 1) % n
            buf = ""
        elif tipo == "DOWN":
            idx = (idx + 1) % n
            buf = ""
        elif tipo == "DIGITO":
            if len(buf) < 6:
                buf += valor
        elif tipo == "BACKSPACE":
            buf = buf[:-1]
        elif tipo in ("ESC", "Q"):
            return None
        elif tipo == "ENTER":
            if buf:
                try:
                    numero = int(buf)
                except ValueError:
                    numero = 0
                if 1 <= numero <= n:
                    return opciones[numero - 1]
                buf = ""
            elif default is not None and idx == _indice_default(opciones, default):
                return default
            else:
                # Enter sobre resaltado: si hay default y no se movió,
                # equivale a default; si se movió, equivale a resaltado.
                if default is not None and buf == "":
                    # Si el cursor sigue en el default, devolverlo;
                    # si no, devolver el resaltado actual.
                    return opciones[idx]
                return opciones[idx]
        else:
            continue
        # Recalcular ventana y repintar encima.
        if n > altura:
            if idx < inicio:
                inicio = idx
            elif idx >= inicio + altura:
                inicio = idx - altura + 1
        sys.stdout.write("\x1b[%dA" % alto_bloque)
        nuevas = bloque(inicio)
        # Limpiar y reescribir cada línea del bloque.
        for ln in nuevas:
            sys.stdout.write("\x1b[2K\r%s\n" % ln)
        # Si el bloque se achicó (filtro borrado), limpiar resto.
        if len(nuevas) < alto_bloque:
            for _ in range(alto_bloque - len(nuevas)):
                sys.stdout.write("\x1b[2K\r\n")
            sys.stdout.write("\x1b[%dA" % (alto_bloque - len(nuevas)))
        sys.stdout.flush()
        alto_bloque = len(nuevas)


def _indice_default(opciones, default):
    try:
        return opciones.index(default)
    except ValueError:
        return 0


def _fallback_numerado(titulo, opciones, formato, default):
    """Lista numerada Panel Rich si hay color, plana si no."""
    pares = [(str(i + 1), _etiqueta_segura(formato, op)) for i, op in enumerate(opciones)]
    try:
        from .vista_rich import print_menu
        print_menu(titulo, pares)
    except Exception:
        print("\n%s" % titulo)
        for num, etiqueta in pares:
            print("  %s) %s" % (num, etiqueta))
    if default is not None:
        try:
            n_default = str(opciones.index(default) + 1)
        except ValueError:
            n_default = None
    else:
        n_default = None
    while True:
        if n_default is not None:
            sugerencia = "1-%d, Enter=%s" % (len(opciones), n_default)
        else:
            sugerencia = "1-%d, vacío cancela" % len(opciones)
        try:
            texto = input("%s [%s]: " % (titulo, sugerencia)).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(130)
        if not texto:
            if default is not None:
                return default
            return None
        if texto.lower() in ("q", "esc"):
            return None
        if texto.isdigit() and len(texto) <= 6:
            try:
                numero = int(texto)
            except ValueError:
                numero = 0
            if 1 <= numero <= len(opciones):
                return opciones[numero - 1]
        print("  opción inválida")


def _etiqueta_segura(formato, valor):
    try:
        return _limpiar(formato(valor))
    except Exception:
        return _limpiar(valor)


def leer_linea(prompt, hint=""):
    """Lee una línea con eco; ESC solo cancela (devuelve None).

    Para prompts de navegación (id, SI) donde ESC debe volver atrás sin
    esperar Enter. Sin TTY de entrada/salida o TERM=dumb: fallback a
    input() clásico (ahí ESC+Enter también cancela al no matchear).
    EOF/Ctrl-C -> SystemExit(130) como el resto del proyecto.
    """
    if not (es_tty() and _salida_tty()) or os.environ.get("TERM", "") == "dumb":
        try:
            return input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            raise SystemExit(130)
    import termios
    import select as _select
    import time as _time
    sys.stdout.write(prompt)
    sys.stdout.flush()
    fd = sys.stdin.fileno()
    attrs = termios.tcgetattr(fd)
    texto = ""
    pendiente = bytearray()
    try:
        tty.setraw(fd)
        while True:
            ch = os.read(fd, 1)
            if not ch:
                sys.stdout.write("\r\n")
                raise SystemExit(130)
            if ch == b"\x03":
                sys.stdout.write("\r\n")
                raise SystemExit(130)
            if ch in (b"\r", b"\n"):
                sys.stdout.write("\r\n")
                sys.stdout.flush()
                return texto.strip()
            if ch in (b"\x7f", b"\x08"):
                if texto:
                    texto = texto[:-1]
                    sys.stdout.write("\r\x1b[2K%s%s" % (prompt, texto))
                    sys.stdout.flush()
                continue
            if ch == b"\x15":  # Ctrl-U: borra la línea
                texto = ""
                sys.stdout.write("\r\x1b[2K%s" % prompt)
                sys.stdout.flush()
                continue
            if ch == b"\x1b":
                # ¿ESC solo (cancela) o secuencia (se ignora)?
                plazo = _time.monotonic() + 0.15
                resto = b""
                while len(resto) < 4:
                    queda = plazo - _time.monotonic()
                    if queda <= 0:
                        break
                    listos, _, _ = _select.select([fd], [], [], queda)
                    if not listos:
                        break
                    trozo = os.read(fd, 1)
                    if not trozo:
                        break
                    resto += trozo
                    if len(resto) >= 2 and resto[-1:].isalpha():
                        break
                if resto == b"":
                    sys.stdout.write("\r\n")
                    sys.stdout.flush()
                    return None
                continue
            pendiente += ch
            try:
                texto += pendiente.decode("utf-8")
                sys.stdout.write(pendiente.decode("utf-8"))
                sys.stdout.flush()
                pendiente = bytearray()
            except UnicodeDecodeError:
                if len(pendiente) > 4:
                    pendiente = bytearray()
                continue
    except OSError:
        sys.stdout.write("\r\n")
        sys.stdout.flush()
        raise SystemExit(130)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
