"""Menú interactivo y flujos de usuario."""

import json
import os
import sys
from datetime import date

from . import export, importador, repo, stats, vista
from .db import respaldar
from .modelos import Estado, normalizar
from .prompts import (
    confirmar, elegir_de_lista, pedir_estado, pedir_fecha, pedir_monto,
    pedir_partidos, pedir_texto,
)
from .validacion import ErrorValidacion

try:
    from .vista_rich import cprint, print_menu, _use_color
except ImportError:
    def _use_color():
        return False
    def cprint(t, **k):
        import re
        print(re.sub(r"\[/?[^\]]*\]", "", t))
    def print_menu(t, opts):
        print(f"\n{t}")
        for n,d in opts:
            print(f"  {n}) {d}")

MENU_OPTS = [
    ("1", "Registrar jornada"),
    ("2", "Ver historial"),
    ("3", "Buscar"),
    ("4", "Estadisticas"),
    ("5", "Importar historico"),
    ("6", "Configuracion"),
    ("7", "Exportar"),
    ("8", "Salir"),
]


def _colorear_prompt(prompt):
    if _use_color():
        # prompts en amarillo, input sin color
        return f"[yellow]{prompt}[/]"
    return prompt


def _leer(prompt):
    try:
        p = _colorear_prompt(prompt)
        if _use_color():
            try:
                from rich.console import Console
                Console().print(p, end="", markup=True, soft_wrap=True)
                return input().strip()
            except Exception:
                pass
        return input(p).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(130)


def _info(msg):
    cprint(f"[dim]{msg}[/]")

def _ok(msg):
    cprint(f"[green]{msg}[/]")

def _warn(msg):
    cprint(f"[yellow]{msg}[/]")

def _err(msg):
    cprint(f"[red]{msg}[/]")


def run(conn):
    while True:
        print_menu("ARBITRAJE", MENU_OPTS)
        opcion = _leer("Opcion: ")
        if opcion == "1":
            registrar(conn)
        elif opcion == "2":
            historial(conn)
        elif opcion == "3":
            buscar(conn)
        elif opcion == "4":
            estadisticas(conn)
        elif opcion == "5":
            importar_historico(conn)
        elif opcion == "6":
            configuracion(conn)
        elif opcion == "7":
            exportar_menu(conn)
        elif opcion in ("8", "s", "S", "q", "Q"):
            return


# ---------------------------------------------------------------- registro

def registrar(conn, fecha_default=None):
    fecha = pedir_fecha("Fecha", fecha_default or date.today())
    existentes = repo.listar_jornadas(
        conn, fecha_desde=fecha.isoformat(), fecha_hasta=fecha.isoformat())
    if existentes:
        _warn("  aviso: ya existen %d jornada(s) con esa fecha (se permite)" % len(existentes))

    estado = pedir_estado()
    partidos = bruto = None
    elegidos = []
    if estado == Estado.ARBITRADO:
        partidos = pedir_partidos("Partidos", default=1)
        bruto = pedir_monto("Ingreso bruto", default=0, permitir_nulo=True)
        cprint("[bold magenta]Descuentos[/]")
        for concepto in repo.listar_conceptos(conn, solo_activos=True):
            monto = pedir_monto(concepto["nombre"], default=concepto["default_monto"])
            if monto > 0:
                elegidos.append((concepto, monto))
        # Descuentos puntuales extra (no saturar el alta diaria)
        while True:
            nombre = pedir_texto("Otro descuento puntual (vacío termina)", "")
            if not nombre:
                break
            # Buscar concepto existente (incluye inactivos) por nombre/alias normalizado
            mapa = repo.mapa_aliases(conn)
            clave = normalizar(nombre)
            cid = None
            if clave in mapa:
                cid = mapa[clave][0]
            else:
                # Crear nuevo concepto para este puntual, dejarlo inactivo para no saturar futuros altas
                try:
                    cid = repo.crear_concepto(conn, nombre.strip(), 0, "")
                    repo.set_concepto_activo(conn, cid, False)
                except ErrorValidacion as error:
                    _err("  error: %s" % error)
                    continue
            # Evitar duplicar mismo concepto en la misma jornada
            if any(c["id"] == cid for c, _ in elegidos):
                _warn("  ya existe ese descuento en esta jornada")
                continue
            monto = pedir_monto(f"Monto {nombre}", default=0)
            if monto is None or monto <= 0:
                _warn("  monto debe ser > 0, omitido")
                continue
            # Resolver objeto concepto para guardar
            concepto_obj = next((c for c in repo.listar_conceptos(conn) if c["id"] == cid), None)
            if concepto_obj is None:
                continue
            elegidos.append((concepto_obj, monto))

    nota = pedir_texto("Nota", "")

    total_desc = sum(m for _, m in elegidos)
    neto = None if bruto is None else bruto - total_desc
    # colores semánticos: bruto green, descuentos red, neto bold green
    if _use_color():
        cprint(f"Bruto: [green]{'-' if bruto is None else bruto} Bs[/]")
        cprint(f"Descuentos: [red]-{total_desc} Bs[/]" if total_desc else "Descuentos: 0 Bs")
        cprint(f"Neto: [bold green]{'-' if neto is None else neto} Bs[/]")
    else:
        print("Bruto: %s Bs" % ("-" if bruto is None else bruto))
        print("Descuentos: -%d Bs" % total_desc if total_desc else "Descuentos: 0 Bs")
        print("Neto: %s Bs" % ("-" if neto is None else neto))
    if not confirmar("Guardar?"):
        _warn("cancelado")
        return None
    try:
        jid = repo.crear_jornada(
            conn, fecha.isoformat(), estado,
            partidos_total=partidos, bruto=bruto,
            nota=nota or None,
        )
        for concepto, monto in elegidos:
            repo.agregar_descuento(conn, jid, concepto["id"], monto)
    except ErrorValidacion as error:
        _err("  error: %s" % error)
        return None
    _ok("guardada jornada #%d" % jid)
    return jid


# ---------------------------------------------------------------- historial

def historial(conn):
    jornadas = repo.listar_jornadas(conn, limite=20)
    vista.tabla_jornadas(jornadas)
    _ver_detalle_opcional(conn)


def buscar(conn):
    print_menu("Buscar", [("1","rango de fechas"),("2","estado"),("3","texto en nota"),("4","todo")])
    opcion = _leer("Criterio: ")
    filtros = {}
    if opcion == "1":
        desde = pedir_fecha("Desde", None)
        hasta = pedir_fecha("Hasta", None)
        filtros["fecha_desde"] = desde.isoformat() if desde else None
        filtros["fecha_hasta"] = hasta.isoformat() if hasta else None
    elif opcion == "2":
        filtros["estado"] = pedir_estado()
    elif opcion == "3":
        filtros["texto_nota"] = pedir_texto("Nota contiene", "")
    jornadas = repo.listar_jornadas(conn, **filtros)
    vista.tabla_jornadas(jornadas)
    _ver_detalle_opcional(conn)


def _ver_detalle_opcional(conn):
    texto = _leer("Ver detalle (id o Enter): ")
    if texto.isdigit():
        jornada = repo.obtener_jornada(conn, int(texto))
        if jornada:
            vista.detalle_jornada(conn, jornada)
        else:
            _err("(id inexistente)")


# ---------------------------------------------------------------- edicion

def editar(conn, jornada_id=None):
    if jornada_id is None:
        texto = _leer("Id de la jornada: ")
        if not texto.isdigit():
            return
        jornada_id = int(texto)
    jornada = repo.obtener_jornada(conn, jornada_id)
    if not jornada:
        _err("(id inexistente)")
        return
    vista.detalle_jornada(conn, jornada)
    cambios = {}
    while True:
        campo = _leer("[cyan][f][/]echa [cyan][e][/]stado [cyan][p][/]artidos [cyan][b][/]ruto [cyan][n][/]ota [cyan][c][/]erteza [cyan][d][/]escuentos [green][g][/]uardar [red][k]BORRAR[/] [yellow][x]salir[/]: ").lower()
        try:
            if campo == "f":
                cambios["fecha"] = pedir_fecha("Fecha").isoformat()
            elif campo == "e":
                cambios["estado"] = pedir_estado()
            elif campo == "p":
                cambios["partidos_total"] = pedir_partidos("Partidos", permitir_nulo=True)
            elif campo == "b":
                cambios["bruto"] = pedir_monto("Ingreso bruto", permitir_nulo=True)
            elif campo == "n":
                cambios["nota"] = pedir_texto("Nota", "") or None
            elif campo == "c":
                from .prompts import pedir_certeza
                cambios["certeza"] = pedir_certeza(str(jornada["certeza"]))
            elif campo == "d":
                _editar_descuentos(conn, jornada_id)
            elif campo == "g":
                if cambios:
                    repo.actualizar_jornada(conn, jornada_id, cambios)
                    _ok("actualizada")
                return
            elif campo == "k":
                if confirmar("Borrar jornada #%d? Esta acción no se puede deshacer" % jornada_id, default=False):
                    if _leer("Escriba SI para confirmar: ") == "SI":
                        try:
                            from .db import respaldar
                            bkp = respaldar()
                            cprint(f"  backup: [dim]{bkp}[/]")
                        except Exception:
                            pass
                        repo.eliminar_jornada(conn, jornada_id)
                        _ok("jornada eliminada")
                        return
                    _warn("cancelado")
                else:
                    _warn("cancelado")
            elif campo == "x":
                if cambios:
                    _warn("sin guardar cambios")
                return
        except ErrorValidacion as error:
            _err("  error: %s" % error)


def _editar_descuentos(conn, jornada_id):
    while True:
        descuentos = repo.descuentos_de(conn, jornada_id)
        for d in descuentos:
            cprint(f"  [dim]#{d['id']}[/] [white]{d['concepto_nombre']:<10}[/] [red]-{d['monto']:>5} Bs[/] {d['nota'] or ''}")
        opcion = _leer("[cyan][a][/]gregar [cyan][e][/]ditar monto [cyan][b][/]orrar [cyan][v][/]olver: ").lower()
        if opcion == "a":
            conceptos = repo.listar_conceptos(conn, solo_activos=True)
            concepto = elegir_de_lista("Concepto", conceptos,
                                       formato=lambda c: c["nombre"])
            if concepto:
                monto = pedir_monto("Monto")
                nota = pedir_texto("Nota del descuento", "")
                try:
                    repo.agregar_descuento(conn, jornada_id, concepto["id"], monto,
                                           nota=nota or None)
                except ErrorValidacion as error:
                    print("  error: %s" % error)
        elif opcion == "e":
            actual = elegir_de_lista("Descuento", descuentos,
                                     formato=lambda d: f"{d['concepto_nombre']} -{d['monto']}")
            if actual:
                repo.actualizar_descuento(conn, actual["id"],
                                          monto=pedir_monto("Nuevo monto"))
        elif opcion == "b":
            actual = elegir_de_lista("Descuento", descuentos,
                                     formato=lambda d: f"{d['concepto_nombre']} -{d['monto']}")
            if actual and confirmar("Borrar descuento?"):
                repo.eliminar_descuento(conn, actual["id"])
        elif opcion == "v":
            return


def eliminar(conn, jornada_id=None):
    if jornada_id is None:
        texto = _leer("Id de la jornada: ")
        if not texto.isdigit():
            return
        jornada_id = int(texto)
    jornada = repo.obtener_jornada(conn, jornada_id)
    if not jornada:
        _err("(id inexistente)")
        return
    vista.detalle_jornada(conn, jornada)
    respuesta = _leer("Escriba SI para eliminar: ")
    if respuesta == "SI":
        try:
            from .db import respaldar
            cprint(f"  backup: [dim]{respaldar()}[/]")
        except Exception:
            pass
        repo.eliminar_jornada(conn, jornada_id)
        _ok("eliminada")
    else:
        _warn("cancelado")


# ---------------------------------------------------------------- estadisticas

def estadisticas(conn):
    while True:
        print_menu("Estadisticas", [("1","resumen"),("2","por mes"),("3","por anio"),("4","descuentos por concepto"),("5","mejores jornadas"),("6","jornadas por estado"),("0","volver")])
        opcion = _leer("Opcion: ")
        if opcion == "0":
            return
        if opcion == "1":
            desde, hasta = _pedir_rango()
            stats.imprimir_resumen(stats.resumen_general(conn, desde, hasta))
        elif opcion == "2":
            año = _pedir_año()
            filas = stats.por_periodo(conn, "%Y-%m", "%s-01-01" % año, "%s-12-31" % año)
            stats.imprimir_tabla_estadistica("POR MES %s" % año, filas)
        elif opcion == "3":
            stats.imprimir_tabla_estadistica("POR ANIO", stats.por_periodo(conn, "%Y"))
        elif opcion == "4":
            año = _pedir_año()
            stats.imprimir_descuentos_por_concepto(
                stats.descuentos_por_concepto(conn, "%s-01-01" % año, "%s-12-31" % año),
                titulo="DESCUENTOS %s" % año)
        elif opcion == "5":
            cantidad = pedir_monto("Cantidad de jornadas", default=5)
            desde, hasta = _pedir_rango()
            _imprimir_mejores(conn, int(cantidad), desde, hasta)
        elif opcion == "6":
            año = _pedir_año()
            filas = stats.jornadas_por_estado(conn, "%s-01-01" % año, "%s-12-31" % año)
            for f in filas:
                print("  %-13s %d" % (f["estado"], f["cantidad"]))


def _pedir_rango():
    desde = pedir_fecha("Desde (vacío = inicio)", None)
    hasta = pedir_fecha("Hasta (vacío = hoy)", None)
    return (desde.isoformat() if desde else None,
            hasta.isoformat() if hasta else None)


def _pedir_año():
    texto = pedir_texto("Anio", str(date.today().year))
    return texto if texto.isdigit() else str(date.today().year)


def _imprimir_mejores(conn, cantidad, desde, hasta):
    filas = stats.mejores_jornadas(conn, cantidad, desde, hasta)
    cprint("[bold magenta]MEJORES JORNADAS[/]")
    for f in filas:
        desc_str = f"-{f['descuentos']}" if f["descuentos"] else "0"
        cprint(f"  [cyan]{f['fecha']}[/]  neto [bold green]{f['neto']:>5} Bs[/]  (bruto [green]{f['bruto']}[/] - desc [red]{desc_str}[/])[dim]{'  %.1f part' % f['partidos'] if f['partidos'] else ''}[/]")


# ---------------------------------------------------------------- importación

def importar_historico(conn):
    ruta = pedir_texto("Archivo del historico", "historico/historico.txt")
    try:
        with open(ruta, encoding="utf-8") as archivo:
            texto = archivo.read()
    except OSError as error:
        _err("  no se pudo leer: %s" % error)
        return
    año_inicial = _pedir_año_inicial()
    mapas = importador.Mapas(conn)
    resultado = importador.parsear(texto, mapas, ano_inicial=año_inicial)
    cprint(f"[dim]{importador.reporte(resultado)}[/]")
    if not confirmar("Aplicar a la base? (se crea backup antes)", default=False):
        _warn("dry-run solamente; nada fue escrito")
        return
    backup = respaldar()
    cprint(f"backup: [dim]{backup}[/]")
    conteo = importador.aplicar(resultado, conn)
    _ok("insertadas: %(jornadas)d jornadas, %(descuentos)d descuentos,"
          " %(issues)d issues a revision" % conteo)


def _pedir_año_inicial():
    texto = pedir_texto("Anio inicial del historico", "2024")
    return int(texto) if texto.isdigit() else 2024


def review(conn):
    pendientes = repo.issues_pendientes(conn)
    if not pendientes:
        _ok("cola de revision vacia")
        return
    for i, issue in enumerate(pendientes, 1):
        linea = issue["linea"][:60]
        cprint(f"[cyan]{i:2d})[/] [yellow][{issue['problema']}[/]] {linea}")
    elegido = elegir_de_lista("Issue a revisar", pendientes,
                              formato=lambda i: i["problema"])
    if not elegido:
        return
    cprint(f"linea     : [white]{elegido['linea']}[/]")
    cprint(f"problema  : [red]{elegido['problema']}[/]")
    cprint(f"sugerencia: [yellow]{elegido['sugerencia'] or '-'}[/]")
    if elegido.get("payload"):
        datos = json.loads(elegido["payload"])
        cprint(f"datos     : [dim]{json.dumps(datos, ensure_ascii=False)}[/]")
    opcion = _leer("[green][r][/]esuelta [cyan][a][/]lta manual [dim][Enter] dejar pendiente[/]: ").lower()
    if opcion == "r":
        repo.marcar_issue_resuelta(conn, elegido["id"])
        _ok("marcada resuelta")
    elif opcion == "a":
        fecha_default = None
        if elegido.get("payload"):
            datos = json.loads(elegido["payload"])
            if datos.get("fecha"):
                from .validacion import parse_fecha
                try:
                    fecha_default = parse_fecha(datos["fecha"])
                except ErrorValidacion:
                    pass
        registrar(conn, fecha_default=fecha_default)
        repo.marcar_issue_resuelta(conn, elegido["id"])


# ---------------------------------------------------------------- configuración

def configuracion(conn):
    while True:
        print_menu("Configuracion", [("1","conceptos"),("0","volver")])
        opcion = _leer("Opcion: ")
        if opcion == "0":
            return
        if opcion == "1":
            _config_conceptos(conn)


def _config_conceptos(conn):
    while True:
        conceptos = repo.listar_conceptos(conn)
        for c in conceptos:
            estado = "activo" if c["activo"] else "INACTIVO"
            col = "green" if c["activo"] else "red"
            cprint(f"  [dim]#{c['id']:<-2d}[/] [white]{c['nombre']:<10}[/] def=[yellow]{c['default_monto']:<-3d}[/] [{col}]{estado}[/]  aliases: [dim]{c['aliases'] or '-'}[/]")
        opcion = _leer("[cyan][c][/]rear [cyan][r][/]enombrar [cyan][a][/]ctivar/desactivar [cyan][d][/]efault [cyan][l][/]aliases [cyan][v][/]olver: ").lower()
        if opcion == "v":
            return
        if opcion == "c":
            nombre = pedir_texto("Nombre del concepto", "")
            if nombre:
                default = pedir_monto("Default mensual", default=0)
                aliases = pedir_texto("Aliases separados por coma", "")
                try:
                    repo.crear_concepto(conn, nombre, default, aliases)
                except ErrorValidacion as error:
                    print("  error: %s" % error)
            continue
        elegido = elegir_de_lista("Concepto", conceptos, formato=lambda c: c["nombre"])
        if not elegido:
            continue
        if opcion == "r":
            repo.renombrar_concepto(conn, elegido["id"], pedir_texto("Nuevo nombre", elegido["nombre"]))
            _ok("renombrado")
        elif opcion == "a":
            repo.set_concepto_activo(conn, elegido["id"], not elegido["activo"])
            _ok("actualizado")
        elif opcion == "d":
            repo.set_concepto_default(conn, elegido["id"], pedir_monto("Default", default=0))
            _ok("actualizado")
        elif opcion == "l":
            repo.set_concepto_aliases(conn, elegido["id"], pedir_texto("Aliases", elegido["aliases"] or ""))
            _ok("actualizado")


def exportar_menu(conn):
    print_menu("Exportar", [("1","CSV"),("2","XLSX"),("3","XLS"),("0","volver")])
    opcion = _leer("Formato: ")
    if opcion not in ("1", "2", "3"):
        return
    directorio = pedir_texto("Directorio destino", ".")
    formatos = {"1": "csv", "2": "xlsx", "3": "xls"}
    formato = formatos[opcion]
    try:
        rutas = export.exportar(conn, directorio, formato=formato)
        for r in rutas:
            print(f"  -> {r}")
    except Exception as e:
        print(f"  error: {e}")



