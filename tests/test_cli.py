"""Tests para el punto de entrada CLI y subcomandos no interactivos."""

import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from arbitraje import cli, db, repo
from arbitraje.modelos import Estado


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_file = Path(self.tmp_dir.name) / "test.db"
        self.conn = db.conectar(self.db_file)
        self.jid = repo.crear_jornada(
            self.conn, "2025-06-01", Estado.ARBITRADO,
            partidos_total=2, bruto=150, nota="Torneo Verano",
        )
        c_id = repo.listar_conceptos(self.conn)[0]["id"]
        repo.agregar_descuento(self.conn, self.jid, c_id, 10, nota="descuento asesor")

    def tearDown(self):
        self.conn.close()
        self.tmp_dir.cleanup()

    def _ejecutar(self, args):
        out, err = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", {"ARBITRAJE_DB": str(self.db_file)}), \
             patch("sys.stdout", out), patch("sys.stderr", err):
            try:
                cli.main(args)
                codigo = 0
            except SystemExit as e:
                codigo = e.code if isinstance(e.code, int) else 1
        return codigo, out.getvalue(), err.getvalue()

    def test_version(self):
        codigo, out, err = self._ejecutar(["--version"])
        self.assertEqual(codigo, 0)
        self.assertIn("arbitraje", out)

    def test_list_json(self):
        codigo, out, err = self._ejecutar(["list", "--json"])
        self.assertEqual(codigo, 0)
        datos = json.loads(out)
        self.assertEqual(len(datos), 1)
        self.assertEqual(datos[0]["id"], self.jid)
        self.assertEqual(datos[0]["neto"], 140)

    def test_list_plain(self):
        codigo, out, err = self._ejecutar(["list", "--plain"])
        self.assertEqual(codigo, 0)
        self.assertIn("2025-06-01", out)
        self.assertIn("150", out)

    def test_search_nota(self):
        codigo, out, err = self._ejecutar(["search", "--nota", "Verano", "--json"])
        self.assertEqual(codigo, 0)
        datos = json.loads(out)
        self.assertEqual(len(datos), 1)

    def test_stats_json(self):
        codigo, out, err = self._ejecutar(["stats", "--json"])
        self.assertEqual(codigo, 0)
        datos = json.loads(out)
        self.assertIn("resumen", datos)
        self.assertEqual(datos["resumen"]["bruto"], 150)
        self.assertEqual(datos["resumen"]["neto"], 140)

    def test_export_subcomando_csv(self):
        export_dir = Path(self.tmp_dir.name) / "export_out"
        codigo, out, err = self._ejecutar(["export", str(export_dir), "--formato", "csv"])
        self.assertEqual(codigo, 0)
        self.assertTrue((export_dir / "jornadas.csv").exists())
        self.assertTrue((export_dir / "descuentos.csv").exists())

    def test_estado_invalido_devuelve_exit_2_sin_traceback(self):
        codigo, out, err = self._ejecutar(["list", "--estado", "ESTADO_INEXISTENTE"])
        self.assertEqual(codigo, 2)
        self.assertIn("error:", err)
        self.assertNotIn("Traceback", err)

    def test_id_inexistente_en_edit_y_delete_retorna_error(self):
        codigo, out, err = self._ejecutar(["edit", "999999"])
        self.assertEqual(codigo, 1)
        self.assertIn("inexistente", err)

        codigo, out, err = self._ejecutar(["delete", "999999"])
        self.assertEqual(codigo, 1)
        self.assertIn("inexistente", err)


if __name__ == "__main__":
    unittest.main()
