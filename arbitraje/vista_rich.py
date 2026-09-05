"""Render Rich opcional para tablas. Si Rich no está, devuelve False para fallback."""

import os
import sys

THEME = {
    "title": "bold magenta",
    "option_num": "cyan",
    "option_txt": "white",
    "prompt": "yellow",
    "error": "red",
    "ok": "green",
    "dim": "dim",
}


def _use_color():
    return not ("NO_COLOR" in os.environ or not sys.stdout.isatty())


def _get_console():
    try:
        from rich.console import Console
        return Console()
    except ImportError:
        return None


def _trunc10(texto):
    s = str(texto or "")
    return s if len(s) <= 10 else s[:9] + "…"


def _fmt_desc(v):
    if not v:
        return "0"
    return f"-{v}"


def cprint(texto, style=None):
    """Print con color si Rich+TTY, fallback plain."""
    if _use_color():
        try:
            from rich.console import Console
            Console().print(texto, style=style, crop=False, overflow="ignore", soft_wrap=True)
            return
        except Exception:
            pass
    # fallback: strip rich markup
    import re
    plain = re.sub(r"\[/?[^\]]*\]", "", texto)
    print(plain)


def print_menu(titulo, opciones):
    """opciones: list de (num, desc) -> coloreado."""
    if _use_color():
        try:
            from rich.console import Console
            from rich.panel import Panel
            console = Console()
            body = "\n".join(f"[cyan]{n})[/] {d}" for n, d in opciones)
            console.print(Panel(body, title=f"[bold magenta]{titulo}[/]", border_style="magenta", padding=(0,1)))
            return
        except Exception:
            pass
    print(f"\n{titulo}")
    for n, d in opciones:
        print(f"  {n}) {d}")


def tabla_jornadas_rich(jornadas):
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box
    except ImportError:
        return False
    if not jornadas:
        return False
    console = Console()
    # Detectar no-TTY ya se hace en vista.py, aquí solo render
    table = Table(
        show_header=True,
        header_style="bold magenta",
        box=box.MINIMAL_DOUBLE_HEAD,
        show_lines=False,
        title="Jornadas",
        title_style="bold",
        expand=False,
    )
    table.add_column("id", style="dim", justify="right", no_wrap=True)
    table.add_column("fecha", style="cyan", no_wrap=True)
    table.add_column("estado", style="yellow", no_wrap=True)
    table.add_column("part", justify="right", no_wrap=True)
    table.add_column("bruto", justify="right", style="green", no_wrap=True)
    table.add_column("desc", justify="right", style="red", no_wrap=True)
    table.add_column("neto", justify="right", style="bold green", no_wrap=True)
    table.add_column("nota", style="dim", no_wrap=True, overflow="ellipsis", max_width=10)

    from .repo import neto_de

    def fmt_float(v):
        if v is None:
            return "-"
        if v == int(v):
            return str(int(v))
        return str(v)

    for j in jornadas:
        neto = neto_de(j)
        neto_str = "-" if neto is None else str(neto)
        estado = j["estado"]
        # Estado colores sutiles
        nota = _trunc10(j.get("nota") or "")
        # Rich no soporta estilo por celda directo en add_row sin markup, usamos estilo columna
        table.add_row(
            str(j["id"]),
            j["fecha"],
            estado,
            fmt_float(j["partidos_total"]),
            "-" if j["bruto"] is None else str(j["bruto"]),
            _fmt_desc(j["total_descuentos"]),
            neto_str,
            nota,
        )
    # Medir ancho natural; cap 120 evita DoS por nota gigante (hardening)
    try:
        from rich.measure import Measurement
        m = Measurement.get(console, console.options, table)
        table.width = min(m.maximum, 120)
    except Exception:
        pass
    console.print(table, crop=False, overflow="ignore", soft_wrap=True)
    return True


def tabla_estadistica_rich(titulo, filas, clave_periodo="periodo"):
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box
    except ImportError:
        return False
    if not filas:
        return False
    console = Console()
    table = Table(title=titulo.strip(), box=box.MINIMAL_DOUBLE_HEAD, show_header=True, header_style="bold magenta")
    col_label = clave_periodo
    table.add_column(col_label, style="cyan", no_wrap=True)
    table.add_column("jornads", justify="right", no_wrap=True)
    table.add_column("partids", justify="right", no_wrap=True)
    table.add_column("bruto", justify="right", style="green", no_wrap=True)
    table.add_column("desc", justify="right", style="red", no_wrap=True)
    table.add_column("neto", justify="right", style="bold green", no_wrap=True)
    for f in filas:
        partidos = f["partidos"]
        partidos_str = "-" if partidos is None else str(round(partidos, 1))
        table.add_row(
            str(f.get(clave_periodo, "")),
            str(f["jornadas"]),
            partidos_str,
            str(f["bruto"] or 0),
            _fmt_desc(f["descuentos"]),
            str(f["neto"] or 0),
        )
    console.print(table, crop=False, overflow="ignore", soft_wrap=True)
    return True


def descuentos_rich(filas, titulo="DESCUENTOS"):
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box
    except ImportError:
        return False
    if not filas:
        return False
    console = Console()
    table = Table(title=titulo.strip(), box=box.MINIMAL_DOUBLE_HEAD, header_style="bold magenta")
    table.add_column("concepto", style="cyan", no_wrap=True)
    table.add_column("total Bs", justify="right", style="green", no_wrap=True)
    total = 0
    for f in filas:
        table.add_row(f["concepto"], _fmt_desc(f["total"]))
        total += f["total"]
    table.add_row("TOTAL", _fmt_desc(total), style="bold")
    console.print(table, crop=False, overflow="ignore", soft_wrap=True)
    return True
