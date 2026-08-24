"""Exportación a CSV."""

import csv
from pathlib import Path

from . import repo


def exportar(conn, directorio="."):
    destino = Path(directorio).expanduser()
    destino.mkdir(parents=True, exist_ok=True)

    ruta_jornadas = destino / "jornadas.csv"
    with open(ruta_jornadas, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow([
            "id", "fecha", "estado", "partidos_total", "roles_detalle",
            "bruto", "total_descuentos", "neto", "torneo", "certeza", "nota",
        ])
        for j in repo.listar_jornadas(conn):
            escritor.writerow([
                j["id"], j["fecha"], j["estado"],
                j["partidos_total"] if j["partidos_total"] is not None else "",
                j["roles_detalle"] or "",
                j["bruto"] if j["bruto"] is not None else "",
                j["total_descuentos"],
                repo.neto_de(j) if repo.neto_de(j) is not None else "",
                j.get("torneo_nombre") or "",
                j["certeza"], j["nota"] or "",
            ])

    ruta_descuentos = destino / "descuentos.csv"
    with open(ruta_descuentos, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.writer(archivo)
        escritor.writerow(["jornada_id", "fecha", "concepto", "monto", "nota"])
        filas = conn.execute(
            "SELECT j.id, j.fecha, c.nombre AS concepto, d.monto, d.nota"
            " FROM descuentos d JOIN jornadas j ON j.id = d.jornada_id"
            " JOIN conceptos_descuento c ON c.id = d.concepto_id"
            " ORDER BY j.fecha, c.orden"
        ).fetchall()
        for f in filas:
            escritor.writerow([f["id"], f["fecha"], f["concepto"], f["monto"], f["nota"] or ""])

    return ruta_jornadas, ruta_descuentos
