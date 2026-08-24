"""Exportación a CSV, XLSX y XLS (todo con stdlib)."""

import csv
import html
import zipfile
import xml.sax.saxutils as sax
from pathlib import Path

from . import repo


def exportar(conn, directorio=".", formato="csv"):
    formato = formato.lower().strip().lstrip(".")
    if formato == "csv":
        return _export_csv(conn, directorio)
    if formato == "xlsx":
        return _export_xlsx(conn, directorio)
    if formato in ("xls", "html"):
        return _export_xls(conn, directorio)
    raise ValueError(f"formato no soportado: {formato} (usar csv/xlsx/xls)")


def _export_csv(conn, directorio):
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


def _export_xls(conn, directorio):
    """XLS compatible con Excel vía HTML tabla (sin dependencias)."""
    destino = Path(directorio).expanduser()
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / "jornadas.xls"
    jornadas = repo.listar_jornadas(conn)
    descuentos_rows = conn.execute(
        "SELECT j.fecha, c.nombre AS concepto, d.monto, j.id"
        " FROM descuentos d JOIN jornadas j ON j.id=d.jornada_id"
        " JOIN conceptos_descuento c ON c.id=d.concepto_id ORDER BY j.fecha"
    ).fetchall()
    with open(ruta, "w", encoding="utf-8") as f:
        f.write('<html><head><meta charset="utf-8"></head><body>')
        f.write('<h3>Jornadas</h3><table border="1"><tr>')
        for h in ["id","fecha","estado","partidos","roles","bruto","desc","neto","torneo","certeza","nota"]:
            f.write(f"<th>{h}</th>")
        f.write("</tr>")
        for j in jornadas:
            neto = repo.neto_de(j)
            f.write("<tr>")
            for v in [j["id"], j["fecha"], j["estado"],
                      j["partidos_total"] or "", j["roles_detalle"] or "",
                      j["bruto"] or "", j["total_descuentos"], neto or "",
                      j.get("torneo_nombre") or "", j["certeza"], j["nota"] or ""]:
                f.write(f"<td>{html.escape(str(v))}</td>")
            f.write("</tr>")
        f.write("</table>")
        f.write('<h3>Descuentos</h3><table border="1"><tr><th>fecha</th><th>concepto</th><th>monto</th><th>jornada_id</th></tr>')
        for r in descuentos_rows:
            f.write(f"<tr><td>{r['fecha']}</td><td>{html.escape(r['concepto'])}</td><td>{r['monto']}</td><td>{r['id']}</td></tr>")
        f.write("</table></body></html>")
    return (ruta,)


def _export_xlsx(conn, directorio):
    """XLSX mínimo vía zipfile + xml inlineStr (stdlib only)."""
    destino = Path(directorio).expanduser()
    destino.mkdir(parents=True, exist_ok=True)
    ruta = destino / "arbitraje.xlsx"
    jornadas = repo.listar_jornadas(conn)
    desc_rows = conn.execute(
        "SELECT j.id, j.fecha, c.nombre AS concepto, d.monto FROM descuentos d "
        "JOIN jornadas j ON j.id=d.jornada_id JOIN conceptos_descuento c ON c.id=d.concepto_id ORDER BY j.fecha"
    ).fetchall()

    def esc(s):
        return sax.escape(str(s))

    def row_xml(cells, row_num):
        xml = f'<row r="{row_num}">'
        for col_idx, val in enumerate(cells, 1):
            col = chr(64+col_idx) if col_idx <=26 else f"A{chr(64+col_idx-26)}"
            # Detectar número vs texto
            if isinstance(val, (int,float)) and val != "":
                xml += f'<c r="{col}{row_num}"><v>{val}</v></c>'
            else:
                xml += f'<c r="{col}{row_num}" t="inlineStr"><is><t>{esc(val)}</t></is></c>'
        xml += '</row>'
        return xml

    # Sheet 1: jornadas
    header_j = ["id","fecha","estado","partidos","roles","bruto","desc","neto","torneo","certeza","nota"]
    sheet1_rows = [row_xml(header_j, 1)]
    for i, j in enumerate(jornadas, 2):
        neto = repo.neto_de(j)
        vals = [j["id"], j["fecha"], j["estado"], j["partidos_total"] or "", j["roles_detalle"] or "", j["bruto"] or "", j["total_descuentos"], neto or "", j.get("torneo_nombre") or "", j["certeza"], j["nota"] or ""]
        sheet1_rows.append(row_xml(vals, i))
    sheet1_xml = f'''<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{''.join(sheet1_rows)}</sheetData></worksheet>'''

    # Sheet 2: descuentos
    header_d = ["jornada_id","fecha","concepto","monto"]
    sheet2_rows = [row_xml(header_d, 1)]
    for i, r in enumerate(desc_rows, 2):
        sheet2_rows.append(row_xml([r["id"], r["fecha"], r["concepto"], r["monto"]], i))
    sheet2_xml = f'''<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{''.join(sheet2_rows)}</sheetData></worksheet>'''

    # Partes fijas del zip
    content_types = '''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'''
    rels = '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'''
    workbook = '''<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Jornadas" sheetId="1" r:id="rId1"/><sheet name="Descuentos" sheetId="2" r:id="rId2"/></sheets></workbook>'''
    wb_rels = '''<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
    styles = '''<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="1"><font><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs></styleSheet>'''

    with zipfile.ZipFile(ruta, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', rels)
        z.writestr('xl/workbook.xml', workbook)
        z.writestr('xl/_rels/workbook.xml.rels', wb_rels)
        z.writestr('xl/worksheets/sheet1.xml', sheet1_xml)
        z.writestr('xl/worksheets/sheet2.xml', sheet2_xml)
        z.writestr('xl/styles.xml', styles)
    return (ruta,)
