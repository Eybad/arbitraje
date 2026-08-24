"""Tests del núcleo: validación, reglas de dominio y persistencia."""

import unittest

from arbitraje.modelos import (
    Estado, Certeza, validar_jornada, calcular_neto, normalizar,
)
from arbitraje.validacion import parse_fecha, parse_monto, parse_partidos, ErrorValidacion


class TestNormalizar(unittest.TestCase):
    def test_tildes_y_mayusculas(self):
        self.assertEqual(normalizar("Asesoría"), "asesoria")
        self.assertEqual(normalizar("  DÍA DEL PEATÓN "), "dia del peaton")

    def test_dias_y_meses_cubren_historico(self):
        from arbitraje.modelos import DIAS_SEMANA, MESES
        self.assertEqual(DIAS_SEMANA["vue"], 4)   # typo del histórico
        self.assertEqual(DIAS_SEMANA["vier"], 4)
        self.assertEqual(MESES["set"], 9)
        self.assertEqual(MESES["julio"], 7)


class TestValidarJornada(unittest.TestCase):
    def test_solo_arbitrado_tiene_bruto(self):
        self.assertTrue(validar_jornada(Estado.LLUVIA, 100))
        self.assertFalse(validar_jornada(Estado.ARBITRADO, 100))
        self.assertFalse(validar_jornada(Estado.LLUVIA, None))

    def test_negativos_rechazados(self):
        self.assertTrue(validar_jornada(Estado.ARBITRADO, -1))
        self.assertTrue(validar_jornada(Estado.ARBITRADO, 0, partidos_total=-2))

    def test_neto_derivado(self):
        self.assertEqual(calcular_neto(190, 10), 180)
        self.assertIsNone(calcular_neto(None, 10))
        self.assertEqual(calcular_neto(100, None), 100)


class TestParseFecha(unittest.TestCase):
    def test_formatos_aceptados(self):
        self.assertEqual(parse_fecha("2025-09-07").isoformat(), "2025-09-07")
        self.assertEqual(parse_fecha("07/09/2025").isoformat(), "2025-09-07")
        self.assertEqual(parse_fecha("7-9-2025").isoformat(), "2025-09-07")

    def test_fecha_imposible(self):
        with self.assertRaises(ErrorValidacion):
            parse_fecha("31/09/2025")
        with self.assertRaises(ErrorValidacion):
            parse_fecha("garbage")


class TestMontosYPartidos(unittest.TestCase):
    def test_monto_entero_no_negativo(self):
        self.assertEqual(parse_monto("190"), 190)
        self.assertEqual(parse_monto("1.000"), 1000)
        with self.assertRaises(ErrorValidacion):
            parse_monto("-5")
        with self.assertRaises(ErrorValidacion):
            parse_monto("abc")

    def test_partidos_fraccionarios(self):
        self.assertEqual(parse_partidos("2.5"), 2.5)
        self.assertEqual(parse_partidos("2,5"), 2.5)
        with self.assertRaises(ErrorValidacion):
            parse_partidos("-1")


if __name__ == "__main__":
    unittest.main()
