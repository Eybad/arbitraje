"""Exportación a CSV, XLSX, JSON y JSONL (100% biblioteca estándar)."""

import csv
import json
import os
import re
import xml.sax.saxutils as sax
import zipfile
from pathlib import Path

from . import repo, stats

_RE_XML_INVALIDO = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _sanitize_csv(valor):
    if not isinstance(valor, str):
        return valor
    texto = valor.strip()
    if texto.startswith(("=", "+", "-", "@", "|", "%")):
        return "'" + valor
    return valor


def _limpiar_xml(valor):
    if valor is None:
        return ""
    limpio = _RE_XML_INVALIDO.sub("", str(valor))
    return sax.escape(limpio)


def _col_excel(n):
    resultado = []
    while n > 0:
        n, resto = divmod(n - 1, 26)
        resultado.append(chr(65 + resto))
    return "".join(reversed(resultado))


def _chmod_600(path):
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _chmod_700(path):
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def _fmt_partidos(valor):
    if valor is None:
        return ""
    try:
        if valor == int(valor):
            return int(valor)
        return valor
    except (ValueError, TypeError):
        return valor


def exportar(conn, directorio=".", formato="csv", fecha_desde=None,
             fecha_hasta=None, estado=None, texto_nota=None):
    fmt = formato.lower().strip().lstrip(".")
    jornadas = repo.listar_jornadas(
        conn, fecha_desde=fecha_desde, fecha_hasta=fecha_hasta,
        estado=estado, texto_nota=texto_nota,
    )
    if jornadas:
        ids_sql = ",".join(str(j["id"]) for j in jornadas)
        filas_desc = conn.execute(
            f"SELECT d.jornada_id, j.fecha, c.nombre AS concepto, d.monto, d.nota"
            f" FROM descuentos d JOIN jornadas j ON j.id = d.jornada_id"
            f" JOIN conceptos_descuento c ON c.id = d.concepto_id"
            f" WHERE d.jornada_id IN ({ids_sql})"
            f" ORDER BY j.fecha, c.orden, d.id"
        ).fetchall()
        descuentos = [dict(d) for d in filas_desc]
    else:
        descuentos = []

    destino = Path(directorio).expanduser().resolve()
    if not destino.exists():
        destino.mkdir(parents=True, exist_ok=True)
        _chmod_700(destino)

    if fmt == "csv":
        return _export_csv(jornadas, descuentos, destino)
    if fmt == "xlsx":
        resumen = stats.resumen_general(conn, fecha_desde, fecha_hasta)
        return _export_xlsx(jornadas, descuentos, resumen, destino)
    if fmt == "json":
        return _export_json(jornadas, descuentos, destino)
    if fmt == "jsonl":
        return _export_jsonl(jornadas, descuentos, destino)
    raise ValueError(f"formato no soportado: {formato} (usar csv, xlsx, json, jsonl)")


def _export_csv(jornadas, descuentos, destino):
    ruta_j = destino / "jornadas.csv"
    with open(ruta_j, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "id", "fecha", "estado", "partidos_total", "roles_detalle",
            "bruto", "total_descuentos", "neto", "certeza", "nota",
        ])
        for j in jornadas:
            neto = repo.neto_de(j)
            partidos = _fmt_partidos(j["partidos_total"])
            w.writerow([
                j["id"],
                j["fecha"],
                j["estado"],
                partidos if partidos != "" else "",
                _sanitize_csv(j["roles_detalle"] or ""),
                j["bruto"] if j["bruto"] is not None else "",
                j["total_descuentos"] if j["total_descuentos"] is not None else 0,
                neto if neto is not None else "",
                j["certeza"],
                _sanitize_csv(j["nota"] or ""),
            ])
    _chmod_600(ruta_j)

    ruta_d = destino / "descuentos.csv"
    with open(ruta_d, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["jornada_id", "fecha", "concepto", "monto", "nota"])
        for d in descuentos:
            w.writerow([
                d["jornada_id"],
                d["fecha"],
                _sanitize_csv(d["concepto"]),
                d["monto"],
                _sanitize_csv(d["nota"] or ""),
            ])
    _chmod_600(ruta_d)
    return ruta_j, ruta_d


def _export_json(jornadas, descuentos, destino):
    ruta = destino / "arbitraje.json"
    data = {
        "jornadas": [
            {
                "id": j["id"],
                "fecha": j["fecha"],
                "estado": j["estado"],
                "partidos_total": j["partidos_total"],
                "roles_detalle": j["roles_detalle"],
                "bruto": j["bruto"],
                "total_descuentos": j["total_descuentos"],
                "neto": repo.neto_de(j),
                "certeza": j["certeza"],
                "nota": j["nota"],
            }
            for j in jornadas
        ],
        "descuentos": descuentos,
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    _chmod_600(ruta)
    return (ruta,)


def _export_jsonl(jornadas, descuentos, destino):
    ruta = destino / "arbitraje.jsonl"
    with open(ruta, "w", encoding="utf-8") as f:
        for j in jornadas:
            item = dict(j)
            item["tipo"] = "jornada"
            item["neto"] = repo.neto_de(j)
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
        for d in descuentos:
            item = dict(d)
            item["tipo"] = "descuento"
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    _chmod_600(ruta)
    return (ruta,)


def _generar_hoja_xml(filas_matriz):
    cuerpo = []
    max_c = 1
    for r_idx, fila in enumerate(filas_matriz, 1):
        celdas = []
        if len(fila) > max_c:
            max_c = len(fila)
        for c_idx, val in enumerate(fila, 1):
            ref = f"{_col_excel(c_idx)}{r_idx}"
            if val is None or val == "":
                continue
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                celdas.append(f'<c r="{ref}"><v>{val}</v></c>')
            else:
                txt = _limpiar_xml(val)
                celdas.append(f'<c r="{ref}" t="inlineStr"><is><t>{txt}</t></is></c>')
        cuerpo.append(f'<row r="{r_idx}">{"".join(celdas)}</row>')
    dim = f"A1:{_col_excel(max_c)}{max(1, len(filas_matriz))}"
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<dimension ref="{dim}"/>'
        f'<sheetData>{"".join(cuerpo)}</sheetData>'
        '</worksheet>'
    )


def _export_xlsx(jornadas, descuentos, resumen, destino):
    ruta = destino / "arbitraje.xlsx"

    cabecera_j = ["id", "fecha", "estado", "partidos_total", "roles_detalle",
                  "bruto", "total_descuentos", "neto", "certeza", "nota"]
    matriz_j = [cabecera_j]
    for j in jornadas:
        matriz_j.append([
            j["id"],
            j["fecha"],
            j["estado"],
            _fmt_partidos(j["partidos_total"]),
            j["roles_detalle"] or "",
            j["bruto"] if j["bruto"] is not None else "",
            j["total_descuentos"] if j["total_descuentos"] is not None else 0,
            repo.neto_de(j) if repo.neto_de(j) is not None else "",
            j["certeza"],
            j["nota"] or "",
        ])
    sheet1_xml = _generar_hoja_xml(matriz_j)

    cabecera_d = ["jornada_id", "fecha", "concepto", "monto", "nota"]
    matriz_d = [cabecera_d]
    for d in descuentos:
        matriz_d.append([
            d["jornada_id"],
            d["fecha"],
            d["concepto"],
            d["monto"],
            d["nota"] or "",
        ])
    sheet2_xml = _generar_hoja_xml(matriz_d)

    matriz_r = [
        ["Métrica", "Valor"],
        ["Total Jornadas", resumen.get("jornadas", 0) or 0],
        ["Partidos Totales", resumen.get("partidos", 0) or 0],
        ["Total Bruto (Bs)", resumen.get("bruto", 0) or 0],
        ["Total Descuentos (Bs)", resumen.get("descuentos", 0) or 0],
        ["Total Neto (Bs)", resumen.get("neto", 0) or 0],
    ]
    sheet3_xml = _generar_hoja_xml(matriz_r)

    content_types = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '</Types>'
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets>'
        '<sheet name="Jornadas" sheetId="1" r:id="rId1"/>'
        '<sheet name="Descuentos" sheetId="2" r:id="rId2"/>'
        '<sheet name="Resumen" sheetId="3" r:id="rId3"/>'
        '</sheets>'
        '</workbook>'
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet3.xml"/>'
        '<Relationship Id="rId4" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        '</Relationships>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>'
        '</styleSheet>'
    )

    with zipfile.ZipFile(ruta, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet1_xml)
        z.writestr("xl/worksheets/sheet2.xml", sheet2_xml)
        z.writestr("xl/worksheets/sheet3.xml", sheet3_xml)
        z.writestr("xl/styles.xml", styles)
    _chmod_600(ruta)
    return (ruta,)
