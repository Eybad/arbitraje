"""Persistencia: jornadas, descuentos, conceptos, torneos e issues."""

from datetime import datetime, timezone

from .modelos import Estado, Certeza, validar_jornada, calcular_neto, normalizar
from .validacion import ErrorValidacion


def _ahora():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dict(fila):
    return dict(fila) if fila is not None else None


# ---------------------------------------------------------------- jornadas

def crear_jornada(conn, fecha, estado, partidos_total=None, roles_detalle=None,
                  bruto=None, torneo_id=None, certeza=Certeza.CONFIRMADO, nota=None):
    errores = validar_jornada(estado, bruto, partidos_total)
    if errores:
        raise ErrorValidacion("; ".join(errores))
    ahora = _ahora()
    cursor = conn.execute(
        "INSERT INTO jornadas (fecha, estado, partidos_total, roles_detalle, bruto,"
        " torneo_id, certeza, nota, created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (fecha, Estado(estado).value, partidos_total, roles_detalle, bruto,
         torneo_id, Certeza(certeza).value, nota, ahora, ahora),
    )
    conn.commit()
    return cursor.lastrowid


def actualizar_jornada(conn, jornada_id, cambios):
    """cambios: dict con claves opcionales del dominio. Valida el resultado final."""
    actual = obtener_jornada(conn, jornada_id)
    if actual is None:
        raise ErrorValidacion("jornada %s no existe" % jornada_id)
    estado = cambios.get("estado", actual["estado"])
    bruto = cambios.get("bruto", actual["bruto"])
    partidos = cambios.get("partidos_total", actual["partidos_total"])
    errores = validar_jornada(Estado(estado), bruto, partidos)
    if errores:
        raise ErrorValidacion("; ".join(errores))
    columnas = ("fecha", "estado", "partidos_total", "roles_detalle", "bruto",
                "torneo_id", "certeza", "nota")
    asignaciones, valores = [], []
    for columna in columnas:
        if columna in cambios:
            valor = cambios[columna]
            if columna == "estado":
                valor = Estado(valor).value
            elif columna == "certeza":
                valor = Certeza(valor).value
            asignaciones.append("%s = ?" % columna)
            valores.append(valor)
    asignaciones.append("updated_at = ?")
    valores.append(_ahora())
    valores.append(jornada_id)
    conn.execute(
        "UPDATE jornadas SET %s WHERE id = ?" % ", ".join(asignaciones), valores
    )
    conn.commit()


def eliminar_jornada(conn, jornada_id):
    cursor = conn.execute("DELETE FROM jornadas WHERE id = ?", (jornada_id,))
    conn.commit()
    return cursor.rowcount > 0


def obtener_jornada(conn, jornada_id):
    fila = conn.execute(
        "SELECT j.*, t.nombre AS torneo_nombre,"
        " (SELECT COALESCE(SUM(monto), 0) FROM descuentos d"
        "   WHERE d.jornada_id = j.id) AS total_descuentos"
        " FROM jornadas j LEFT JOIN torneos t ON t.id = j.torneo_id"
        " WHERE j.id = ?",
        (jornada_id,),
    ).fetchone()
    return _dict(fila)


def listar_jornadas(conn, fecha_desde=None, fecha_hasta=None, estado=None,
                    torneo_texto=None, texto_nota=None, limite=None):
    consulta = (
        "SELECT j.*, t.nombre AS torneo_nombre,"
        " (SELECT COALESCE(SUM(monto), 0) FROM descuentos d"
        "   WHERE d.jornada_id = j.id) AS total_descuentos"
        " FROM jornadas j LEFT JOIN torneos t ON t.id = j.torneo_id WHERE 1=1"
    )
    valores = []
    if fecha_desde:
        consulta += " AND j.fecha >= ?"
        valores.append(fecha_desde)
    if fecha_hasta:
        consulta += " AND j.fecha <= ?"
        valores.append(fecha_hasta)
    if estado:
        consulta += " AND j.estado = ?"
        valores.append(Estado(estado).value)
    if torneo_texto:
        consulta += " AND t.nombre LIKE ?"
        valores.append("%" + torneo_texto + "%")
    if texto_nota:
        consulta += " AND j.nota LIKE ?"
        valores.append("%" + texto_nota + "%")
    if limite:
        consulta += " ORDER BY j.fecha DESC, j.id DESC LIMIT ?"
        valores.append(limite)
        filas = [dict(f) for f in conn.execute(consulta, valores)]
        filas.reverse()
        return filas
    consulta += " ORDER BY j.fecha ASC, j.id ASC"
    return [dict(f) for f in conn.execute(consulta, valores)]


def neto_de(jornada):
    """Neto derivado a partir de un dict con bruto y total_descuentos."""
    return calcular_neto(jornada["bruto"], jornada.get("total_descuentos"))


# ---------------------------------------------------------------- descuentos

def descuentos_de(conn, jornada_id):
    return [
        dict(f)
        for f in conn.execute(
            "SELECT d.*, c.nombre AS concepto_nombre FROM descuentos d"
            " JOIN conceptos_descuento c ON c.id = d.concepto_id"
            " WHERE d.jornada_id = ? ORDER BY c.orden, c.id",
            (jornada_id,),
        )
    ]


def agregar_descuento(conn, jornada_id, concepto_id, monto, nota=None):
    existente = conn.execute(
        "SELECT id FROM descuentos WHERE jornada_id = ? AND concepto_id = ?",
        (jornada_id, concepto_id),
    ).fetchone()
    if existente:
        raise ErrorValidacion("esa jornada ya tiene un descuento de ese concepto")
    cursor = conn.execute(
        "INSERT INTO descuentos (jornada_id, concepto_id, monto, nota) VALUES (?, ?, ?, ?)",
        (jornada_id, concepto_id, monto, nota),
    )
    conn.commit()
    return cursor.lastrowid


def actualizar_descuento(conn, descuento_id, monto=None, nota=None):
    if monto is not None:
        if monto < 0:
            raise ErrorValidacion("el monto no puede ser negativo")
        conn.execute("UPDATE descuentos SET monto = ? WHERE id = ?", (monto, descuento_id))
    if nota is not None:
        conn.execute("UPDATE descuentos SET nota = ? WHERE id = ?", (nota, descuento_id))
    conn.commit()


def eliminar_descuento(conn, descuento_id):
    cursor = conn.execute("DELETE FROM descuentos WHERE id = ?", (descuento_id,))
    conn.commit()
    return cursor.rowcount > 0


# ---------------------------------------------------------------- conceptos

def listar_conceptos(conn, solo_activos=False):
    consulta = "SELECT * FROM conceptos_descuento"
    if solo_activos:
        consulta += " WHERE activo = 1"
    consulta += " ORDER BY orden, id"
    return [dict(f) for f in conn.execute(consulta)]


def mapa_aliases(conn):
    """{alias normalizado o nombre normalizado: (id, nombre)} para el importador."""
    mapa = {}
    for concepto in listar_conceptos(conn):
        clave = normalizar(concepto["nombre"])
        mapa[clave] = (concepto["id"], concepto["nombre"])
        for alias in (concepto["aliases"] or "").split(","):
            alias = alias.strip()
            if alias:
                mapa.setdefault(normalizar(alias), (concepto["id"], concepto["nombre"]))
    return mapa


def crear_concepto(conn, nombre, default_monto=0, aliases=""):
    try:
        cursor = conn.execute(
            "INSERT INTO conceptos_descuento (nombre, activo, default_monto, orden, aliases)"
            " VALUES (?, 1, ?, (SELECT COALESCE(MAX(orden), 0) + 1 FROM conceptos_descuento), ?)",
            (nombre.strip(), default_monto, aliases.strip()),
        )
        conn.commit()
        return cursor.lastrowid
    except Exception:
        conn.rollback()
        raise ErrorValidacion("no se pudo crear el concepto %r (¿duplicado?)" % nombre)


def renombrar_concepto(conn, concepto_id, nombre):
    conn.execute(
        "UPDATE conceptos_descuento SET nombre = ? WHERE id = ?", (nombre.strip(), concepto_id)
    )
    conn.commit()


def set_concepto_activo(conn, concepto_id, activo):
    conn.execute(
        "UPDATE conceptos_descuento SET activo = ? WHERE id = ?",
        (1 if activo else 0, concepto_id),
    )
    conn.commit()


def set_concepto_default(conn, concepto_id, default_monto):
    if default_monto < 0:
        raise ErrorValidacion("el default no puede ser negativo")
    conn.execute(
        "UPDATE conceptos_descuento SET default_monto = ? WHERE id = ?",
        (default_monto, concepto_id),
    )
    conn.commit()


def set_concepto_aliases(conn, concepto_id, aliases):
    conn.execute(
        "UPDATE conceptos_descuento SET aliases = ? WHERE id = ?", (aliases.strip(), concepto_id)
    )
    conn.commit()


# ---------------------------------------------------------------- torneos

def listar_torneos(conn):
    return [dict(f) for f in conn.execute("SELECT * FROM torneos ORDER BY nombre")]


def buscar_torneo(conn, texto):
    fila = conn.execute("SELECT * FROM torneos").fetchall()
    objetivo = normalizar(texto)
    for t in fila:
        if normalizar(t["nombre"]) == objetivo:
            return dict(t)
    return None


def obtener_o_crear_torneo(conn, nombre):
    existente = buscar_torneo(conn, nombre)
    if existente:
        return existente["id"]
    cursor = conn.execute("INSERT INTO torneos (nombre) VALUES (?)", (nombre.strip(),))
    conn.commit()
    return cursor.lastrowid


# ---------------------------------------------------------------- issues

def crear_issue(conn, linea, problema, sugerencia=None, payload=None):
    cursor = conn.execute(
        "INSERT INTO import_issues (linea, problema, sugerencia, payload, resuelto, created_at)"
        " VALUES (?, ?, ?, ?, 0, ?)",
        (linea, problema, sugerencia, payload, _ahora()),
    )
    conn.commit()
    return cursor.lastrowid


def issues_pendientes(conn):
    return [
        dict(f)
        for f in conn.execute(
            "SELECT * FROM import_issues WHERE resuelto = 0 ORDER BY id"
        )
    ]


def marcar_issue_resuelta(conn, issue_id):
    conn.execute("UPDATE import_issues SET resuelto = 1 WHERE id = ?", (issue_id,))
    conn.commit()
