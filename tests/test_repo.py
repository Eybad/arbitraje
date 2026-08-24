"""Tests de persistencia sobre base en memoria."""

import unittest

from arbitraje import repo
from arbitraje.db import conectar
from arbitraje.modelos import Estado, Certeza
from arbitraje.validacion import ErrorValidacion


class TestRepo(unittest.TestCase):
    def setUp(self):
        self.conn = conectar(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_semillas_cargadas(self):
        conceptos = {c["nombre"] for c in repo.listar_conceptos(self.conn)}
        self.assertIn("Asesoría", conceptos)
        self.assertIn("Deuda", conceptos)
        torneos = {t["nombre"] for t in repo.listar_torneos(self.conn)}
        self.assertIn("Coca Cola", torneos)

    def test_ciclo_jornada_completo(self):
        jid = repo.crear_jornada(
            self.conn, "2025-09-07", Estado.ARBITRADO,
            partidos_total=3, bruto=180, nota="prueba",
        )
        jornada = repo.obtener_jornada(self.conn, jid)
        self.assertEqual(jornada["bruto"], 180)
        self.assertEqual(jornada["estado"], "ARBITRADO")
        self.assertEqual(jornada["certeza"], "CONFIRMADO")

        concepto = repo.listar_conceptos(self.conn)[0]
        repo.agregar_descuento(self.conn, jid, concepto["id"], 10)
        jornada = repo.obtener_jornada(self.conn, jid)
        self.assertEqual(jornada["total_descuentos"], 10)
        self.assertEqual(repo.neto_de(jornada), 170)

        repo.actualizar_jornada(self.conn, jid, {"bruto": 200})
        self.assertEqual(repo.obtener_jornada(self.conn, jid)["bruto"], 200)

        self.assertTrue(repo.eliminar_jornada(self.conn, jid))
        self.assertIsNone(repo.obtener_jornada(self.conn, jid))

    def test_estado_no_arbitrado_sin_bruto(self):
        with self.assertRaises(ErrorValidacion):
            repo.crear_jornada(self.conn, "2025-10-19", Estado.LLUVIA, bruto=50)

    def test_descuento_duplicado_rechazado(self):
        jid = repo.crear_jornada(self.conn, "2025-09-07", Estado.ARBITRADO, bruto=100)
        concepto = repo.listar_conceptos(self.conn)[0]
        repo.agregar_descuento(self.conn, jid, concepto["id"], 10)
        with self.assertRaises(ErrorValidacion):
            repo.agregar_descuento(self.conn, jid, concepto["id"], 5)

    def test_cascade_borra_descuentos(self):
        jid = repo.crear_jornada(self.conn, "2025-09-07", Estado.ARBITRADO, bruto=100)
        concepto = repo.listar_conceptos(self.conn)[0]
        repo.agregar_descuento(self.conn, jid, concepto["id"], 10)
        repo.eliminar_jornada(self.conn, jid)
        restantes = self.conn.execute("SELECT COUNT(*) FROM descuentos").fetchone()[0]
        self.assertEqual(restantes, 0)

    def test_filtros_listado(self):
        repo.crear_jornada(self.conn, "2025-09-07", Estado.ARBITRADO, bruto=100)
        repo.crear_jornada(self.conn, "2025-10-19", Estado.LLUVIA)
        solo_lluvia = repo.listar_jornadas(self.conn, estado=Estado.LLUVIA)
        self.assertEqual(len(solo_lluvia), 1)
        self.assertEqual(solo_lluvia[0]["estado"], "LLUVIA")

    def test_torneo_busqueda_insensible(self):
        tid = repo.obtener_o_crear_torneo(self.conn, "ribereña")
        encontrado = repo.buscar_torneo(self.conn, "RIBEREÑA")
        self.assertEqual(encontrado["id"], tid)

    def test_mapa_aliases(self):
        mapa = repo.mapa_aliases(self.conn)
        self.assertEqual(mapa["a"][1], "Asesoría")
        self.assertEqual(mapa["pol"][1], "Polera")
        self.assertEqual(mapa["asesoria"][1], "Asesoría")


if __name__ == "__main__":
    unittest.main()
