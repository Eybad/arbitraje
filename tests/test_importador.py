"""Tests del importador: cada decisión del plan v2 como aserción."""

import unittest
from pathlib import Path

from arbitraje import importador, repo
from arbitraje.db import conectar

HISTORICO = Path(__file__).resolve().parent.parent / "historico" / "historico.txt"

FIXTURE = """\
1) Sab 7 sep: 3 = 160 (-20)
Dom 8 sep: 3 = 150 (-30 a)

2025

17) Dom 5 ene:  2 = 100 (-10 a, -10 multa) *-50*
-Llegué este domingo en la mañana

27) Dom 16 mar: no recuerdo, tal vez lluvia o 1 en la CC.

30) Dom 6 abr: viaje

52x) Dom 7 sep: DÍA DEL PEATÓN

82q) Dom 5 abr: 1 = 70 -lluvia

76z) Jue 19 feb:
Vie 20 feb:
Sab 21 feb:
Dom 22 feb:

77z) Jue
Vie
Sab
Dom 1 mar:

71k) Jue 15 ene: no designado.
Vie 16 ene: no designado.
Sab 17 ene: no designado.
Dom 18 ene: 3 = 220 (-20 a)

72k) Jue 18 ene: no designado
Vie 19 ene: no designado
Sab 20 ene: no designado
Dom 21 ene: 1 + 3 = 175 (-10 a)

34k) Dom 4 may: 3 = 190 (-10 a, -10 c)
-
Campeonato villa vecinal:
Jue 8 may: 4 = 174
Sab 10 may: 3+1(80%) = 168
total = 516

35k) Sab 10 may: 1 = 50 (La salle)
Dom 11 may: 4 = 210 (-40 pol, -20 pres, -10 a)

86k) Sab 2 may: 130 (-10 c)

101k) Sab 15 ago: 2 res+7 ame= 355 (-30 a, soda)

41k) Sab 21 jun: 2 = 140 (-10 a) FINAL LA SALLE

2026

69k) Jue 1 ene: no hubo.
Dom 4 ene: 2 = 150 (-10 a) coca cola
"""


class TestImportador(unittest.TestCase):
    def setUp(self):
        self.conn = conectar(":memory:")
        self.mapas = importador.Mapas(self.conn)

    def _parsear(self, texto, ano=2024):
        return importador.parsear(texto, self.mapas, ano_inicial=ano)

    def _por_fecha(self, resultado, iso):
        return [c for c in resultado.candidatos
                if c.fecha and c.fecha.isoformat() == iso]

    def test_reconstruccion_bruto_desde_neto(self):
        r = self._parsear("1) Sab 7 sep: 3 = 160 (-20)\n")
        c = self._por_fecha(r, "2024-09-07")[0]
        self.assertEqual(c.bruto, 180)
        self.assertEqual(c.valor_neto, 160)
        self.assertEqual(c.partidos, 3)

    def test_alias_conceptos_y_deuda_marcador(self):
        r = self._parsear(
            "17) Dom 5 ene:  2 = 100 (-10 a, -10 multa) *-50*\n"
            "-Llegué este domingo en la mañana\n", ano=2025)
        c = self._por_fecha(r, "2025-01-05")[0]
        # Decisión B: bruto incluye el -50 de deuda externa
        self.assertEqual(c.bruto, 170)
        montos = {d["nombre"]: d["monto"] for d in c.descuentos.values()}
        self.assertEqual(montos["Asesoría"], 10)
        self.assertEqual(montos["Multa"], 10)
        self.assertEqual(montos["Deuda"], 50)
        self.assertTrue(any("Llegué" in n for n in c.notas))

    def test_dudoso_sin_datos(self):
        r = self._parsear("27) Dom 16 mar: no recuerdo, tal vez lluvia o 1 en la CC.\n", ano=2025)
        c = self._por_fecha(r, "2025-03-16")[0]
        self.assertEqual(c.estado.value, "SIN_DATOS")
        self.assertEqual(c.certeza.value, "DUDOSO")
        self.assertIn("CC", c.notas[0])

    def test_feriado_y_jugado_con_lluvia(self):
        r = self._parsear(
            "52x) Dom 7 sep: DÍA DEL PEATÓN\n"
            "82q) Dom 5 abr: 1 = 70 -lluvia\n", ano=2025)
        feriado = self._por_fecha(r, "2025-09-07")[0]
        self.assertEqual(feriado.estado.value, "FERIADO")
        jugado = self._por_fecha(r, "2025-04-06")[0]
        self.assertEqual(jugado.estado.value, "ARBITRADO")
        self.assertEqual(jugado.bruto, 70)
        self.assertIn("lluvia", jugado.notas)

    def test_placeholders_vacios_son_sin_datos(self):
        r = self._parsear(
            "76z) Jue 19 feb:\nVie 20 feb:\nSab 21 feb:\nDom 22 feb:\n", ano=2025)
        fechas = {c.fecha.isoformat() for c in r.candidatos}
        self.assertEqual(fechas, {"2025-02-20", "2025-02-21",
                                  "2025-02-22", "2025-02-23"})
        self.assertTrue(all(c.estado.value == "SIN_DATOS" for c in r.candidatos))

    def test_dias_sin_numero_se_derivan_del_ancla(self):
        r = self._parsear("77z) Jue\nVie\nSab\nDom 1 mar:\n", ano=2026)
        fechas = sorted(c.fecha.isoformat() for c in r.candidatos if c.fecha)
        # Mar 1 2026 es domingo; la semana es jue 26 feb - dom 1 mar
        self.assertEqual(fechas, ["2026-02-26", "2026-02-27",
                                  "2026-02-28", "2026-03-01"])

    def test_recalibracion_offset_uniforme_por_bloque(self):
        r = self._parsear(
            "71k) Jue 15 ene: no designado.\n"
            "Vie 16 ene: no designado.\n"
            "Sab 17 ene: no designado.\n"
            "Dom 18 ene: 3 = 220 (-20 a)\n", ano=2025)
        fechas = sorted(c.fecha.isoformat() for c in r.candidatos)
        self.assertEqual(fechas, ["2025-01-16", "2025-01-17",
                                  "2025-01-18", "2025-01-19"])
        self.assertTrue(all(c.certeza.value == "PROBABLE" for c in r.candidatos))
        jugado = [c for c in r.candidatos if c.bruto][0]
        self.assertEqual(jugado.bruto, 240)  # 220 neto + 20 asesoría
        self.assertTrue(any("fecha escrita" in n for n in jugado.notas))

    def test_bloques_consecutivos_no_colisionan(self):
        r = self._parsear(
            "71k) Jue 15 ene: no designado.\nDom 18 ene: 3 = 220 (-20 a)\n"
            "72k) Jue 18 ene: no designado\nDom 21 ene: 1 + 3 = 175 (-10 a)\n",
            ano=2025)
        fechas = sorted(c.fecha.isoformat() for c in r.candidatos)
        self.assertEqual(len(set(fechas)), len(fechas))
        self.assertIn("2025-01-26", fechas)  # semana siguiente, no solapada

    def test_doble_jornada_misma_fecha_permite_insertar(self):
        r = self._parsear(FIXTURE)
        diez_mayo = self._por_fecha(r, "2025-05-10")
        self.assertEqual(len(diez_mayo), 2)
        torneos = {c.torneo for c in diez_mayo}
        self.assertEqual(torneos, {"Villa Vecinal", "La Salle"})
        villa = [c for c in diez_mayo if c.torneo == "Villa Vecinal"][0]
        self.assertEqual(villa.partidos, 4)  # 3+1(80%) cuenta físico
        self.assertEqual(villa.roles_detalle, "3+1(80%)")

    def test_encabezado_seccion_asigna_torneo(self):
        r = self._parsear(FIXTURE)
        jueves = self._por_fecha(r, "2025-05-08")[0]
        self.assertEqual(jueves.torneo, "Villa Vecinal")

    def test_linea_solo_monto(self):
        r = self._parsear("86k) Sab 2 may: 130 (-10 c)\n", ano=2026)
        c = self._por_fecha(r, "2026-05-02")[0]
        self.assertIsNone(c.partidos)
        self.assertEqual(c.bruto, 140)

    def test_descuento_sin_monto_bloquea_jornada(self):
        r = self._parsear("101k) Sab 15 ago: 2 res+7 ame= 355 (-30 a, soda)\n", ano=2025)
        bloqueadas = [x for x in r.candidatos if x.bloqueado]
        self.assertEqual(len(bloqueadas), 1)
        self.assertIn("sin monto", bloqueadas[0].bloqueado)
        self.assertTrue(any(i["problema"].startswith("descuento sin monto")
                            for i in r.issues))

    def test_descuento_sin_concepto_va_a_otros(self):
        r = self._parsear("83k) Sab 11 abr: 4 = 130 (-10)\n", ano=2026)
        c = self._por_fecha(r, "2026-04-11")[0]
        montos = {d["nombre"]: d["monto"] for d in c.descuentos.values()}
        self.assertEqual(montos.get("Otros"), 10)
        self.assertEqual(c.bruto, 140)

    def test_expresion_no_parseable_bloquea(self):
        r = self._parsear("102k) Dom 23 ago: 3 = 170 (-30 y 150 ya pagados)\n")
        bloqueadas = [x for x in r.candidatos if x.bloqueado]
        self.assertEqual(len(bloqueadas), 1)
        self.assertIn("no parseable", bloqueadas[0].bloqueado)

    def test_torneo_coca_cola_y_final(self):
        r = self._parsear(FIXTURE)
        coca = self._por_fecha(r, "2026-01-04")[0]
        self.assertEqual(coca.torneo, "Coca Cola")
        final_ = self._por_fecha(r, "2025-06-21")[0]
        self.assertEqual(final_.torneo, "La Salle")
        self.assertIn("FINAL", final_.notas[0])

    def test_token_ambiguo_va_a_revision(self):
        r = self._parsear("56k) Dom 5 oct: descanso/viaje\n")
        bloqueadas = [x for x in r.candidatos if x.bloqueado]
        self.assertEqual(len(bloqueadas), 1)
        self.assertTrue(any("ambiguo" in i["problema"] for i in r.issues))

    def test_aplicar_inserta_y_registra_issues(self):
        r = self._parsear(FIXTURE)
        conteo = importador.aplicar(r, self.conn)
        self.assertGreater(conteo["jornadas"], 0)
        self.assertGreater(conteo["issues"], 0)
        jornadas = repo.listar_jornadas(self.conn)
        brutos = {j["fecha"]: j["bruto"] for j in jornadas}
        self.assertEqual(brutos["2024-09-07"], 180)
        self.assertEqual(brutos["2025-01-05"], 170)
        pendientes = repo.issues_pendientes(self.conn)
        self.assertEqual(len(pendientes), conteo["issues"])

    def test_historico_real_completo(self):
        if not HISTORICO.exists():
            self.skipTest("historico/historico.txt no presente")
        texto = HISTORICO.read_text(encoding="utf-8")
        r = self._parsear(texto)
        validos = [c for c in r.candidatos if not c.bloqueado]
        self.assertGreater(len(validos), 230)
        # Ninguna jornada válida viola las reglas duras del dominio
        for c in validos:
            if c.estado.value != "ARBITRADO":
                self.assertIsNone(c.bruto, "%s %s" % (c.fecha, c.estado))
        # Los tres dudosos explícitos existen
        dudosos = [c for c in validos if c.certeza.value == "DUDOSO"]
        self.assertEqual(len(dudosos), 3)
        # Soda y expresiones no parseables quedaron en cola
        self.assertTrue(any("sin monto" in i["problema"] for i in r.issues))
        self.assertTrue(any("no parseable" in i["problema"] for i in r.issues))


if __name__ == "__main__":
    unittest.main()
