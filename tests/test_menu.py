"""Tests navegación ESC: vuelve atrás, en el principal no hace nada."""

import unittest
from unittest.mock import MagicMock, patch

from arbitraje import menu


def _jornada():
    return {"id": 1, "fecha": "2025-01-01", "estado": "ARBITRADO",
            "certeza": "CONFIRMADO", "partidos_total": 1, "bruto": 100,
            "total_descuentos": 0, "nota": None}


class TestMenuPrincipal(unittest.TestCase):
    def test_esc_no_hace_nada_y_sigue(self):
        conn = MagicMock()
        with patch("arbitraje.selector.seleccionar_clave",
                   side_effect=[None, "8"]) as sel:
            menu.run(conn)
        self.assertEqual(sel.call_count, 2)
        conn.assert_not_called()

    def test_salir_con_8(self):
        conn = MagicMock()
        with patch("arbitraje.selector.seleccionar_clave",
                   return_value="8") as sel:
            menu.run(conn)
        sel.assert_called_once()
        conn.assert_not_called()


class TestSubmenusVuelven(unittest.TestCase):
    def test_buscar_esc_vuelve(self):
        conn = MagicMock()
        with patch("arbitraje.selector.seleccionar_clave",
                   return_value=None):
            self.assertIsNone(menu.buscar(conn))
        conn.assert_not_called()

    def test_estadisticas_esc_vuelve(self):
        conn = MagicMock()
        with patch("arbitraje.selector.seleccionar_clave",
                   return_value=None):
            self.assertIsNone(menu.estadisticas(conn))
        conn.assert_not_called()

    def test_configuracion_esc_vuelve(self):
        conn = MagicMock()
        with patch("arbitraje.selector.seleccionar_clave",
                   return_value=None):
            self.assertIsNone(menu.configuracion(conn))
        conn.assert_not_called()

    def test_exportar_esc_vuelve(self):
        conn = MagicMock()
        with patch("arbitraje.selector.seleccionar_clave",
                   return_value=None):
            self.assertIsNone(menu.exportar_menu(conn))
        conn.assert_not_called()

    def test_descuentos_esc_vuelve(self):
        conn = MagicMock()
        conn.execute.return_value = []
        with patch("arbitraje.selector.seleccionar_clave",
                   return_value=None):
            self.assertIsNone(menu._editar_descuentos(conn, 1))

    def test_conceptos_esc_vuelve(self):
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        with patch("arbitraje.selector.seleccionar_clave",
                   return_value=None):
            self.assertIsNone(menu._config_conceptos(conn))

    def test_editar_esc_sale_sin_guardar(self):
        conn = MagicMock()
        with patch.object(menu.repo, "obtener_jornada",
                          return_value=_jornada()), \
             patch.object(menu.vista, "detalle_jornada"), \
             patch.object(menu.repo, "actualizar_jornada") as upd, \
             patch("arbitraje.selector.seleccionar_clave",
                   return_value=None):
            self.assertIsNone(menu.editar(conn, 1))
        upd.assert_not_called()

    def test_review_esc_deja_pendiente(self):
        conn = MagicMock()
        issue = {"id": 7, "linea": "x", "problema": "P",
                 "sugerencia": None, "payload": None}
        with patch.object(menu.repo, "issues_pendientes",
                          return_value=[issue]), \
             patch.object(menu, "elegir_de_lista", return_value=issue), \
             patch.object(menu.repo, "marcar_issue_resuelta") as marca, \
             patch("arbitraje.selector.seleccionar_clave",
                   return_value=None):
            self.assertIsNone(menu.review(conn))
        marca.assert_not_called()


    def test_historial_esc_vuelve(self):
        conn = MagicMock()
        conn.execute.return_value = []
        with patch("arbitraje.selector.leer_linea", return_value=None):
            self.assertIsNone(menu.historial(conn))

    def test_eliminar_id_esc_vuelve(self):
        conn = MagicMock()
        with patch("arbitraje.selector.leer_linea", return_value=None):
            self.assertIsNone(menu.eliminar(conn))
        conn.assert_not_called()

    def test_editar_id_esc_vuelve(self):
        conn = MagicMock()
        with patch("arbitraje.selector.leer_linea", return_value=None):
            self.assertIsNone(menu.editar(conn))
        conn.assert_not_called()


if __name__ == "__main__":
    unittest.main()
