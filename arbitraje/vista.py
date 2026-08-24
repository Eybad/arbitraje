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


def tabla_jornadas(jornadas):
    if not jornadas:
        print("(sin resultados)")
        return
    encabezado = "%-4s %-10s %-13s %6s %7s %5s %7s %s" % (
        "id", "fecha", "estado", "part", "bruto", "desc", "neto", "torneo")
    print(encabezado)
    print("-" * len(encabezado))
    for j in jornadas:
        neto = repo.neto_de(j)
        print("%-4s %-10s %-13s %6s %7s %5s %7s %s" % (
            j["id"], j["fecha"], j["estado"],
            _fmt_float(j["partidos_total"]),
            _fmt_monto(j["bruto"]),
            j["total_descuentos"] or 0,
            "-" if neto is None else neto,
            j.get("torneo_nombre") or "",
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
            print("    %-10s %5d Bs%s" % (d["concepto_nombre"], d["monto"], nota))
    else:
        print("  descuentos: ninguno")
    print("  neto     : %s Bs" % _fmt_monto(repo.neto_de(jornada)))
    print("  torneo   : %s" % (jornada.get("torneo_nombre") or "-"))
    if jornada.get("nota"):
        print("  nota     : %s" % jornada["nota"])
