"""Tests para el módulo de exportación (CSV, XLSX, JSON, JSONL)."""

import csv
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from arbitraje import db, export, repo
from arbitraje.modelos import Estado


class TestExport(unittest.TestCase):
    def setUp(self):
        self.conn = db.conectar(":memory:")
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.destino = Path(self.tmp_dir.name)

        # Jornada normal
        self.j1 = repo.crear_jornada(
            self.conn, "2025-05-10", Estado.ARBITRADO,
            partidos_total=2, bruto=140, nota="=formula_peligrosa",
        )
        c_id = repo.listar_conceptos(self.conn)[0]["id"]
        repo.agregar_descuento(self.conn, self.j1, c_id, 10, nota="+nota_descuento")

        # Jornada con ceros legítimos (bruto=0, partidos=0, neto=0)
        self.j_cero = repo.crear_jornada(
            self.conn, "2025-05-11", Estado.ARBITRADO,
            partidos_total=0, bruto=0, nota="formativo",
        )

        # Jornada en otro estado (NO_HUBO) para probar filtros
        self.j_nohubo = repo.crear_jornada(
            self.conn, "2025-05-12", Estado.NO_HUBO,
            nota="lluvia previa",
        )

    def tearDown(self):
        self.conn.close()
        self.tmp_dir.cleanup()

    def test_ceros_no_se_convierten_en_vacio_csv(self):
        rutas = export.exportar(self.conn, self.destino, formato="csv")
        ruta_j = rutas[0]
        with open(ruta_j, encoding="utf-8") as f:
            filas = list(csv.reader(f))
            # Cabecera: id, fecha, estado, partidos_total, roles_detalle, bruto, total_descuentos, neto, certeza, nota
            # Fila de j_cero es la segunda jornada (indice 2)
            fila_cero = [r for r in filas[1:] if r[0] == str(self.j_cero)][0]
            self.assertEqual(fila_cero[3], "0")  # partidos_total
            self.assertEqual(fila_cero[5], "0")  # bruto
            self.assertEqual(fila_cero[6], "0")  # total_descuentos
            self.assertEqual(fila_cero[7], "0")  # neto

    def test_descuento_nota_preservada_en_csv_y_xlsx(self):
        rutas_csv = export.exportar(self.conn, self.destino, formato="csv")
        ruta_d_csv = rutas_csv[1]
        with open(ruta_d_csv, encoding="utf-8") as f:
            filas_d = list(csv.reader(f))
            # Cabecera: jornada_id, fecha, concepto, monto, nota
            self.assertEqual(filas_d[0], ["jornada_id", "fecha", "concepto", "monto", "nota"])
            self.assertTrue(filas_d[1][4].endswith("nota_descuento"))

        rutas_xlsx = export.exportar(self.conn, self.destino, formato="xlsx")
        ruta_xlsx = rutas_xlsx[0]
        with zipfile.ZipFile(ruta_xlsx) as z:
            sheet2 = z.read("xl/worksheets/sheet2.xml").decode("utf-8")
            self.assertIn("nota", sheet2)
            self.assertIn("nota_descuento", sheet2)

    def test_exportar_csv_sanitiza_formulas(self):
        rutas = export.exportar(self.conn, self.destino, formato="csv")
        ruta_j = rutas[0]
        with open(ruta_j, encoding="utf-8") as f:
            filas = list(csv.reader(f))
            # La nota de j1 tiene "=formula_peligrosa" -> debe empezar con '=
            fila_j1 = [r for r in filas[1:] if r[0] == str(self.j1)][0]
            self.assertTrue(fila_j1[9].startswith("'="))

    def test_exportar_xlsx_valido_y_tres_hojas(self):
        rutas = export.exportar(self.conn, self.destino, formato="xlsx")
        self.assertEqual(len(rutas), 1)
        ruta_xlsx = rutas[0]
        with zipfile.ZipFile(ruta_xlsx) as z:
            nombres = set(z.namelist())
            self.assertIn("[Content_Types].xml", nombres)
            self.assertIn("xl/workbook.xml", nombres)
            self.assertIn("xl/worksheets/sheet1.xml", nombres)
            self.assertIn("xl/worksheets/sheet2.xml", nombres)
            self.assertIn("xl/worksheets/sheet3.xml", nombres)
            wb_xml = z.read("xl/workbook.xml").decode("utf-8")
            self.assertIn('name="Jornadas"', wb_xml)
            self.assertIn('name="Descuentos"', wb_xml)
            self.assertIn('name="Resumen"', wb_xml)

    def test_ceros_en_xlsx_como_numeros(self):
        rutas = export.exportar(self.conn, self.destino, formato="xlsx")
        with zipfile.ZipFile(rutas[0]) as z:
            sheet1 = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            # Los números cero deben grabarse como <v>0</v>
            self.assertIn("<v>0</v>", sheet1)

    def test_caracteres_control_sanitizados_en_xlsx(self):
        # Nota con caracter de control inválido en XML 1.0 (\x0c form feed, \x1b esc)
        jid = repo.crear_jornada(
            self.conn, "2025-05-15", Estado.ARBITRADO,
            bruto=100, nota="test\x0ccon\x1bcontrol",
        )
        rutas = export.exportar(self.conn, self.destino, formato="xlsx")
        with zipfile.ZipFile(rutas[0]) as z:
            sheet1 = z.read("xl/worksheets/sheet1.xml").decode("utf-8")
            self.assertNotIn("\x0c", sheet1)
            self.assertNotIn("\x1b", sheet1)
            self.assertIn("testconcontrol", sheet1)

    def test_exportar_json_y_jsonl(self):
        rutas_json = export.exportar(self.conn, self.destino, formato="json")
        self.assertEqual(len(rutas_json), 1)
        with open(rutas_json[0], encoding="utf-8") as f:
            data = json.load(f)
            self.assertIn("jornadas", data)
            self.assertIn("descuentos", data)
            self.assertEqual(len(data["jornadas"]), 3)

        rutas_jsonl = export.exportar(self.conn, self.destino, formato="jsonl")
        self.assertEqual(len(rutas_jsonl), 1)
        with open(rutas_jsonl[0], encoding="utf-8") as f:
            lineas = [json.loads(l) for l in f if l.strip()]
            tipos = {item.get("tipo") for item in lineas}
            self.assertIn("jornada", tipos)
            self.assertIn("descuento", tipos)

    def test_filtrado_exportacion(self):
        rutas = export.exportar(
            self.conn, self.destino, formato="csv",
            estado=Estado.ARBITRADO, fecha_desde="2025-05-11", fecha_hasta="2025-05-11",
        )
        with open(rutas[0], encoding="utf-8") as f:
            filas = list(csv.reader(f))
            # Solo j_cero debe estar
            self.assertEqual(len(filas), 2)  # cabecera + 1 fila
            self.assertEqual(filas[1][0], str(self.j_cero))

        # La tabla de descuentos debe estar vacía para esa fecha (j_cero no tiene descuentos)
        with open(rutas[1], encoding="utf-8") as f:
            filas_d = list(csv.reader(f))
            self.assertEqual(len(filas_d), 1)  # solo cabecera

    def test_formato_invalido_falla(self):
        with self.assertRaises(ValueError):
            export.exportar(self.conn, self.destino, formato="invalido")


if __name__ == "__main__":
    unittest.main()
