"""Tests de estadísticas: los NULL jamás falsifican totales."""

import unittest

from arbitraje import repo, stats
from arbitraje.db import conectar
from arbitraje.modelos import Estado


class TestStats(unittest.TestCase):
    def setUp(self):
        self.conn = conectar(":memory:")
        asesoría = repo.listar_conceptos(self.conn)[0]
        # 2025-01-05: bruto 170, descuento 10 -> neto 160, 2 partidos
        j1 = repo.crear_jornada(self.conn, "2025-01-05", Estado.ARBITRADO,
                                partidos_total=2, bruto=170)
        repo.agregar_descuento(self.conn, j1, asesoría["id"], 10)
        # 2025-01-12: bruto NULL (desconocido), partidos NULL
        repo.crear_jornada(self.conn, "2025-01-12", Estado.ARBITRADO)
        # 2025-02-02: bruto 260, 4 partidos, sin descuentos
        repo.crear_jornada(self.conn, "2025-02-02", Estado.ARBITRADO,
                           partidos_total=4, bruto=260)
        # lluvia no cuenta en dinero
        repo.crear_jornada(self.conn, "2025-02-09", Estado.LLUVIA)

    def test_resumen_excluye_null_y_lluvia(self):
        resumen = stats.resumen_general(self.conn)
        self.assertEqual(resumen["jornadas"], 2)
        self.assertEqual(resumen["bruto"], 430)
        self.assertEqual(resumen["descuentos"], 10)
        self.assertEqual(resumen["neto"], 420)
        self.assertEqual(resumen["partidos"], 6)

    def test_por_mes(self):
        filas = stats.por_periodo(self.conn, "%Y-%m")
        por_periodo = {f["periodo"]: f for f in filas}
        self.assertEqual(por_periodo["2025-01"]["neto"], 160)
        self.assertEqual(por_periodo["2025-02"]["neto"], 260)

    def test_por_anio(self):
        filas = stats.por_periodo(self.conn, "%Y")
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["jornadas"], 2)

    def test_descuentos_por_concepto(self):
        filas = stats.descuentos_por_concepto(self.conn)
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["concepto"], "Asesoría")
        self.assertEqual(filas[0]["total"], 10)

    def test_mejores_jornadas_orden_descendente(self):
        filas = stats.mejores_jornadas(self.conn, 5)
        self.assertEqual(filas[0]["fecha"], "2025-02-02")
        self.assertEqual(filas[0]["neto"], 260)

    def test_rango_excluye_fuera_de_periodo(self):
        resumen = stats.resumen_general(self.conn, "2025-02-01", "2025-02-28")
        self.assertEqual(resumen["jornadas"], 1)
        self.assertEqual(resumen["neto"], 260)

    def test_render_no_explota_con_vacio(self):
        stats.imprimir_tabla_estadistica("VACIO", [])
        stats.imprimir_descuentos_por_concepto([])
        stats.imprimir_resumen({})


if __name__ == "__main__":
    unittest.main()
