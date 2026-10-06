"""Tests selector nativo stdlib + fail-closed sin TTY."""

import io
import sys
import unittest
from unittest.mock import patch

from arbitraje import selector


class TestTTYGate(unittest.TestCase):
    def test_default_sin_tty_permitido(self):
        with patch.object(selector, "es_tty", return_value=False):
            self.assertEqual(
                selector.seleccionar(
                    "T", ["a", "b"], default="a",
                    usar_default_sin_tty=True,
                ),
                "a",
            )

    def test_sin_tty_sin_permiso_falla_2(self):
        with patch.object(selector, "es_tty", return_value=False):
            err = io.StringIO()
            with patch.object(sys, "stderr", err):
                with self.assertRaises(SystemExit) as ctx:
                    selector.seleccionar("T", ["a", "b"], hint="usar terminal")
            self.assertEqual(ctx.exception.code, 2)
            self.assertIn("error:", err.getvalue())
            self.assertIn("hint:", err.getvalue())

    def test_confirmar_sin_tty_falla(self):
        with patch.object(selector, "es_tty", return_value=False):
            err = io.StringIO()
            with patch.object(sys, "stderr", err):
                with self.assertRaises(SystemExit) as ctx:
                    selector.confirmar_flechas("Guardar?", default=True)
            self.assertEqual(ctx.exception.code, 2)


class TestFallbackNumerado(unittest.TestCase):
    def _tty_sin_salida(self):
        return (patch.object(selector, "es_tty", return_value=True),
                patch.object(selector, "_salida_tty", return_value=False))

    def test_elige_segundo(self):
        m_tty, m_sal = self._tty_sin_salida()
        with m_tty, m_sal, patch("builtins.input", return_value="2"):
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(
                    selector.seleccionar("T", ["a", "b", "c"]), "b")

    def test_enter_devuelve_default(self):
        m_tty, m_sal = self._tty_sin_salida()
        with m_tty, m_sal, patch("builtins.input", return_value=""):
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(
                    selector.seleccionar("T", ["a", "b"], default="b"), "b")

    def test_q_cancela(self):
        m_tty, m_sal = self._tty_sin_salida()
        with m_tty, m_sal, patch("builtins.input", return_value="q"):
            with patch("sys.stdout", io.StringIO()):
                self.assertIsNone(selector.seleccionar("T", ["a", "b"]))

    def test_clave(self):
        m_tty, m_sal = self._tty_sin_salida()
        pares = [("1", "Uno"), ("8", "Salir")]
        with m_tty, m_sal, patch("builtins.input", return_value="2"):
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(
                    selector.seleccionar_clave("M", pares), "8")

    def test_eof_es_130(self):
        m_tty, m_sal = self._tty_sin_salida()
        with m_tty, m_sal, patch("builtins.input", side_effect=EOFError):
            with patch("sys.stdout", io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    selector.seleccionar("T", ["a"])
            self.assertEqual(ctx.exception.code, 130)

    def test_numero_gigante_no_explota(self):
        m_tty, m_sal = self._tty_sin_salida()
        with m_tty, m_sal, patch("builtins.input",
                                 side_effect=["9" * 5000, "q"]):
            with patch("sys.stdout", io.StringIO()):
                self.assertIsNone(selector.seleccionar("T", ["a", "b"]))


class TestLeerTecla(unittest.TestCase):
    def _tecla(self, secuencia, listo=True):
        datos = list(secuencia)
        sel_ret = ([0], [], []) if listo else ([], [], [])
        def fake_read(fd, n=1):
            return datos.pop(0) if datos else b""
        class FakeStdin:
            def fileno(self):
                return 0
            def isatty(self):
                return True
        with patch.object(selector.sys, "stdin", FakeStdin()), \
             patch("termios.tcgetattr", return_value="a"), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("os.read", side_effect=fake_read), \
             patch("select.select", return_value=sel_ret):
            return selector._leer_tecla()

    def test_up_normal(self):
        self.assertEqual(self._tecla([b"\x1b", b"[", b"A"]), ("UP", None))

    def test_down_normal(self):
        self.assertEqual(self._tecla([b"\x1b", b"[", b"B"]), ("DOWN", None))

    def test_up_app_mode_no_cierra(self):
        # Regresión: ESC O A se parseaba como ESC → cerraba el programa.
        self.assertEqual(self._tecla([b"\x1b", b"O", b"A"]), ("UP", None))

    def test_down_app_mode_no_cierra(self):
        self.assertEqual(self._tecla([b"\x1b", b"O", b"B"]), ("DOWN", None))

    def test_esc_solo_cancela(self):
        self.assertEqual(self._tecla([b"\x1b"], listo=False), ("ESC", None))

    def test_secuencia_desconocida_se_ignora(self):
        self.assertEqual(self._tecla([b"\x1b", b"[", b"Z"]), ("OTRA", None))

    def test_enter(self):
        self.assertEqual(self._tecla([b"\r"]), ("ENTER", None))

    def test_digito(self):
        self.assertEqual(self._tecla([b"2"]), ("DIGITO", "2"))


class TestLeerLinea(unittest.TestCase):
    def _linea_con(self, octetos, tty=True, salida_tty=True):
        datos = list(octetos)

        def fake_read(fd, n=1):
            return datos.pop(0) if datos else b""

        def fake_select(r, w, x, timeout=None):
            return ([r], [], []) if datos else ([], [], [])
        with patch.object(selector, "es_tty", return_value=tty), \
             patch.object(selector, "_salida_tty", return_value=salida_tty), \
             patch("termios.tcgetattr", return_value="a"), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("os.read", side_effect=fake_read), \
             patch("select.select", side_effect=fake_select), \
             patch("sys.stdout", io.StringIO()):
            return selector.leer_linea("Id: ")

    def test_esc_solo_cancela(self):
        self.assertIsNone(self._linea_con([b"\x1b"]))

    def test_digitos_enter(self):
        self.assertEqual(self._linea_con([b"4", b"2", b"\r"]), "42")

    def test_backspace_borra(self):
        self.assertEqual(
            self._linea_con([b"4", b"3", b"\x7f", b"\r"]), "4")

    def test_utf8_multibyte(self):
        self.assertEqual(
            self._linea_con([b"\xc3", b"\xb1", b"\r"]), "ñ")

    def test_flecha_se_ignora_no_cancela(self):
        self.assertEqual(
            self._linea_con([b"\x1b", b"[", b"A", b"5", b"\r"]), "5")

    def test_fallback_sin_tty(self):
        with patch.object(selector, "es_tty", return_value=False), \
             patch("builtins.input", return_value="7"):
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(selector.leer_linea("Id: "), "7")

    def test_eof_es_130(self):
        with patch.object(selector, "es_tty", return_value=True), \
             patch.object(selector, "_salida_tty", return_value=True), \
             patch("termios.tcgetattr", return_value="a"), \
             patch("termios.tcsetattr"), \
             patch("tty.setraw"), \
             patch("os.read", return_value=b""), \
             patch("sys.stdout", io.StringIO()):
            with self.assertRaises(SystemExit) as ctx:
                selector.leer_linea("Id: ")
        self.assertEqual(ctx.exception.code, 130)


@unittest.skipUnless(hasattr(__import__("os"), "openpty"), "sin pty")
class TestPtyReal(unittest.TestCase):
    """Regresión del bug real: con TextIOWrapper bufferizado, sys.stdin.read(1)
    tragaba ESC[A y el select ya no veía nada → ESC → programa cerrado.
    Este test usa pty de verdad, sin mocks de lectura."""

    def _correr_con_pty(self, recipient, escritor):
        import os as _os
        import pty as _pty
        import sys as _sys
        import threading
        m, s = _pty.openpty()
        fin = _os.fdopen(_os.dup(s), "r")
        fout = _os.fdopen(_os.dup(s), "w")
        _os.close(s)
        real_in, real_out = _sys.stdin, _sys.stdout
        _sys.stdin, _sys.stdout = fin, fout
        caja = {}
        def objetivo():
            try:
                caja["r"] = recipient()
            except BaseException as e:  # noqa: BLE001
                caja["e"] = repr(e)
        hilo = threading.Thread(target=objetivo)
        try:
            hilo.start()
            escritor(m)
            hilo.join(10)
            self.assertFalse(hilo.is_alive(), "se colgó esperando tecla")
        finally:
            _sys.stdin, _sys.stdout = real_in, real_out
            try:
                fin.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                fout.close()
            except Exception:  # noqa: BLE001
                pass
            _os.close(m)
        self.assertNotIn("e", caja, caja.get("e"))
        return caja.get("r")

    def test_flecha_up_real_no_es_esc(self):
        import os as _os
        from arbitraje import selector as _sel
        self.assertEqual(
            self._correr_con_pty(
                _sel._leer_tecla, lambda m: _os.write(m, b"\x1b[A")),
            ("UP", None))

    def test_flecha_down_y_enter_elige_segundo(self):
        import os as _os
        import time as _time
        from arbitraje import selector as _sel
        def escribir(m):
            _time.sleep(0.3)
            _os.write(m, b"\x1b[B")
            _time.sleep(0.3)
            _os.write(m, b"\r")
        self.assertEqual(
            self._correr_con_pty(
                lambda: _sel._nativo("T", ["a", "b"], str, "a", ""), escribir),
            "b")

    def test_linea_real_id_enter(self):
        import os as _os
        import time as _time
        from arbitraje import selector as _sel
        def escribir(m):
            _time.sleep(0.3)
            _os.write(m, b"7\r")
        self.assertEqual(
            self._correr_con_pty(
                lambda: _sel.leer_linea("Id: "), escribir),
            "7")

    def test_linea_real_esc_cancela(self):
        import os as _os
        import time as _time
        from arbitraje import selector as _sel
        def escribir(m):
            _time.sleep(0.3)
            _os.write(m, b"\x1b")
        self.assertIsNone(
            self._correr_con_pty(
                lambda: _sel.leer_linea("Id: "), escribir))


class TestNativo(unittest.TestCase):
    def test_enter_devuelve_resaltado(self):
        with patch.object(selector, "_leer_tecla",
                          side_effect=[("ENTER", None)]):
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(
                    selector._nativo("T", ["a", "b"], str, "a", ""), "a")

    def test_flecha_abajo_luego_enter(self):
        with patch.object(selector, "_leer_tecla",
                          side_effect=[("DOWN", None), ("ENTER", None)]):
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(
                    selector._nativo("T", ["a", "b"], str, "a", ""), "b")

    def test_esc_cancela(self):
        with patch.object(selector, "_leer_tecla",
                          side_effect=[("ESC", None)]):
            with patch("sys.stdout", io.StringIO()):
                self.assertIsNone(
                    selector._nativo("T", ["a", "b"], str, None, ""))

    def test_digito_enter_elige(self):
        with patch.object(selector, "_leer_tecla",
                          side_effect=[("DIGITO", "2"), ("ENTER", None)]):
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(
                    selector._nativo("T", ["a", "b", "c"], str, "a", ""), "b")

    def test_eof_es_130(self):
        with patch.object(selector, "_leer_tecla", side_effect=EOFError):
            with patch("sys.stdout", io.StringIO()):
                with self.assertRaises(SystemExit) as ctx:
                    selector._nativo("T", ["a"], str, None, "")
            self.assertEqual(ctx.exception.code, 130)


class TestPromptsDelegan(unittest.TestCase):
    def test_pedir_estado_sin_tty_devuelve_default(self):
        from arbitraje.modelos import Estado
        with patch.object(selector, "es_tty", return_value=False):
            from arbitraje.prompts import pedir_estado
            self.assertEqual(pedir_estado(), Estado.ARBITRADO)

    def test_elegir_lista_vacia_none(self):
        from arbitraje.prompts import elegir_de_lista
        self.assertIsNone(elegir_de_lista("X", []))


if __name__ == "__main__":
    unittest.main()
