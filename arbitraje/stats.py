"""Estadísticas: consultas y render. Los NULL jamás falsifican totales."""

_BASE = (
    "WITH base AS ("
    " SELECT j.*, (SELECT COALESCE(SUM(monto), 0) FROM descuentos d"
    "   WHERE d.jornada_id = j.id) AS descuentos"
    " FROM jornadas j"
    " WHERE j.estado = 'ARBITRADO' AND j.bruto IS NOT NULL"
)


def _rango(desde, hasta):
    condiciones, valores = "", []
    if desde:
        condiciones += " AND j.fecha >= ?"
        valores.append(desde)
    if hasta:
        condiciones += " AND j.fecha <= ?"
        valores.append(hasta)
    return condiciones, valores


def _filas(conn, consulta, valores=()):
    return [dict(f) for f in conn.execute(consulta, valores)]


def por_periodo(conn, formato_sql, desde=None, hasta=None):
    """formato_sql: '%Y-%m' para meses, '%Y' para años."""
    condiciones, valores = _rango(desde, hasta)
    consulta = _BASE + condiciones + ")"
    consulta += (
        " SELECT strftime(?, fecha) AS periodo,"
        " COUNT(*) AS jornadas, SUM(partidos_total) AS partidos,"
        " SUM(bruto) AS bruto, SUM(descuentos) AS descuentos,"
        " SUM(bruto - descuentos) AS neto"
        " FROM base GROUP BY periodo ORDER BY periodo"
    )
    return _filas(conn, consulta, valores + [formato_sql])





def descuentos_por_concepto(conn, desde=None, hasta=None):
    condiciones, valores = _rango(desde, hasta)
    consulta = (
        "SELECT c.nombre AS concepto, SUM(d.monto) AS total, COUNT(*) AS veces"
        " FROM descuentos d"
        " JOIN conceptos_descuento c ON c.id = d.concepto_id"
        " JOIN jornadas j ON j.id = d.jornada_id"
        " WHERE j.estado = 'ARBITRADO'" + condiciones +
        " GROUP BY c.id HAVING total > 0 ORDER BY total DESC"
    )
    return _filas(conn, consulta, valores)


def mejores_jornadas(conn, cantidad=5, desde=None, hasta=None):
    condiciones, valores = _rango(desde, hasta)
    consulta = _BASE + condiciones + ")"
    consulta += (
        " SELECT id, fecha, bruto, descuentos, (bruto - descuentos) AS neto,"
        " partidos_total AS partidos"
        " FROM base ORDER BY neto DESC, fecha LIMIT ?"
    )
    return _filas(conn, consulta, valores + [cantidad])


def resumen_general(conn, desde=None, hasta=None):
    condiciones, valores = _rango(desde, hasta)
    consulta = _BASE + condiciones + ")"
    consulta += (
        " SELECT COUNT(*) AS jornadas, SUM(partidos_total) AS partidos,"
        " SUM(bruto) AS bruto, SUM(descuentos) AS descuentos,"
        " SUM(bruto - descuentos) AS neto FROM base"
    )
    filas = _filas(conn, consulta, valores)
    return filas[0] if filas else {}


def jornadas_por_estado(conn, desde=None, hasta=None):
    condiciones, valores = _rango(desde, hasta)
    consulta = (
        "SELECT estado, COUNT(*) AS cantidad FROM jornadas j WHERE 1=1" +
        condiciones + " GROUP BY estado ORDER BY cantidad DESC"
    )
    return _filas(conn, consulta, valores)


# ---------------------------------------------------------------- render

def _fmt_desc(v):
    if not v:
        return "0"
    return f"-{v}"


def _linea(valores, anchos):
    return "  ".join(str(v).rjust(a) for v, a in zip(valores, anchos))


def imprimir_tabla_estadistica(titulo, filas, clave_periodo="periodo", plain=None):
    # plain=None auto-detecta; si Rich disponible y no plain, usar rich
    if not plain:
        import os, sys
        is_plain = ("NO_COLOR" in os.environ) or (plain is True)
        if not is_plain and sys.stdout.isatty():
            try:
                from .vista_rich import tabla_estadistica_rich
                if tabla_estadistica_rich(titulo, filas, clave_periodo):
                    return
            except Exception:
                pass
    print(titulo)
    if not filas:
        print("  (sin datos)")
        return
    anchos = [12, 8, 8, 9, 9, 9]
    print(_linea(["periodo", "jornads", "partids", "bruto", "desc", "neto"], anchos))
    for f in filas:
        print(_linea([
            f.get(clave_periodo, ""),
            f["jornadas"],
            "-" if f["partidos"] is None else round(f["partidos"], 1),
            f["bruto"] or 0,
            _fmt_desc(f["descuentos"]),
            f["neto"] or 0,
        ], anchos))


def imprimir_descuentos_por_concepto(filas, titulo="DESCUENTOS", plain=None):
    if not plain:
        import os, sys
        is_plain = ("NO_COLOR" in os.environ) or (plain is True)
        if not is_plain and sys.stdout.isatty():
            try:
                from .vista_rich import descuentos_rich
                if descuentos_rich(filas, titulo):
                    return
            except Exception:
                pass
    print(titulo)
    if not filas:
        print("  (sin datos)")
        return
    ancho = max(len(f["concepto"]) for f in filas) + 2
    total = 0
    for f in filas:
        print("  %-*s -%6d Bs" % (ancho, f["concepto"], f["total"]))
        total += f["total"]
    print("  %s" % ("-" * (ancho + 10)))
    print("  %-*s -%6d Bs" % (ancho, "TOTAL", total))


def imprimir_resumen(resumen):
    if not resumen:
        print("(sin datos)")
        return
    jornadas = resumen["jornadas"] or 0
    partidos = resumen["partidos"]
    bruto = resumen["bruto"] or 0
    neto = resumen["neto"] or 0
    print("  jornadas : %d" % jornadas)
    print("  partidos : %s" % ("-" if partidos is None else round(partidos, 1)))
    print("  bruto    : %d Bs" % bruto)
    print("  descuentos: %s Bs" % _fmt_desc(resumen["descuentos"]))
    print("  neto     : %d Bs" % neto)
    if jornadas:
        print("  prom/jornada: %d Bs" % round(neto / jornadas))
    if partidos:
        print("  prom/partido: %d Bs" % round(neto / partidos))
