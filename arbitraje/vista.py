"""Render de tablas y detalles para CLI y menú."""

from . import repo
from .modelos import Estado


def _fmt_float(valor):
    if valor is None:
        return "-"
    if valor == int(valor):
        return str(int(valor))
    return str(valor)


def _fmt_monto(valor):
    return "-" if valor is None else str(valor)


def _fmt_desc(valor):
    if not valor:
        return "0"
    return f"-{valor}"


def _trunc(texto, largo=22):
    if not texto:
        return ""
    texto = str(texto)
    return texto if len(texto) <= largo else texto[: largo - 1] + "…"


def tabla_jornadas(jornadas, plain=None):
    # plain=True fuerza salida sin colores (para pipe); si None detecta TTY/NO_COLOR
    if not jornadas:
        print("(sin resultados)")
        return
    # Intentar Rich si disponible y no es plain
    use_plain = plain
    if use_plain is None:
        import os, sys
        use_plain = ("NO_COLOR" in os.environ) or not sys.stdout.isatty()
    if not use_plain:
        try:
            from .vista_rich import tabla_jornadas_rich
            if tabla_jornadas_rich(jornadas):
                return
        except Exception:
            pass
    encabezado = "%-4s %-10s %-13s %6s %7s %5s %7s %s" % (
        "id", "fecha", "estado", "part", "bruto", "desc", "neto", "nota")
    print(encabezado)
    print("-" * len(encabezado))
    for j in jornadas:
        neto = repo.neto_de(j)
        print("%-4s %-10s %-13s %6s %7s %5s %7s %s" % (
            j["id"], j["fecha"], j["estado"],
            _fmt_float(j["partidos_total"]),
            _fmt_monto(j["bruto"]),
            _fmt_desc(j["total_descuentos"]),
            "-" if neto is None else neto,
            _trunc(j.get("nota") or "", 10),
        ))


def detalle_jornada(conn, jornada):
    print("Jornada #%s  %s  %s  certeza=%s" % (
        jornada["id"], jornada["fecha"], jornada["estado"], jornada["certeza"]))
    print("  partidos : %s" % _fmt_float(jornada["partidos_total"]))
    if jornada.get("roles_detalle"):
        print("  roles    : %s" % jornada["roles_detalle"])
    print("  bruto    : %s Bs" % _fmt_monto(jornada["bruto"]))
    descuentos = repo.descuentos_de(conn, jornada["id"])
    if descuentos:
        print("  descuentos:")
        for d in descuentos:
            nota = (" (%s)" % d["nota"]) if d["nota"] else ""
            print("    %-10s -%5d Bs%s" % (d["concepto_nombre"], d["monto"], nota))
    else:
        print("  descuentos: ninguno")
    print("  neto     : %s Bs" % _fmt_monto(repo.neto_de(jornada)))
    if jornada.get("nota"):
        print("  nota     : %s" % jornada["nota"])
