"""Menú interactivo y flujos de usuario."""

import json
from datetime import date

from . import export, importador, repo, stats, vista
from .db import respaldar
from .modelos import Estado, normalizar
from .prompts import (
    confirmar, elegir_de_lista, pedir_estado, pedir_fecha, pedir_monto,
    pedir_partidos, pedir_texto,
)
from .validacion import ErrorValidacion

MENU = """
ARBITRAJE
1) Registrar jornada
2) Ver historial
3) Buscar
4) Estadisticas
5) Importar historico
6) Configuracion
7) Exportar
8) Salir
"""


def _leer(prompt):
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(130)


def run(conn):
    while True:
        print(MENU)
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
        print("  aviso: ya existen %d jornada(s) con esa fecha (se permite)" % len(existentes))

    estado = pedir_estado()
    partidos = bruto = None
    elegidos = []
    if estado == Estado.ARBITRADO:
        partidos = pedir_partidos("Partidos", default=1)
        bruto = pedir_monto("Ingreso bruto", default=0, permitir_nulo=True)
        print("Descuentos")
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
                    print("  error: %s" % error)
                    continue
            # Evitar duplicar mismo concepto en la misma jornada
            if any(c["id"] == cid for c, _ in elegidos):
                print("  ya existe ese descuento en esta jornada")
                continue
            monto = pedir_monto(f"Monto {nombre}", default=0)
            if monto is None or monto <= 0:
                print("  monto debe ser > 0, omitido")
                continue
            # Resolver objeto concepto para guardar
            concepto_obj = next((c for c in repo.listar_conceptos(conn) if c["id"] == cid), None)
            if concepto_obj is None:
                continue
            elegidos.append((concepto_obj, monto))

    torneo_id = _pedir_torneo(conn)
    nota = pedir_texto("Nota", "")

    total_desc = sum(m for _, m in elegidos)
    neto = None if bruto is None else bruto - total_desc
    print("Bruto: %s Bs" % ("-" if bruto is None else bruto))
    print("Descuentos: %d Bs" % total_desc)
    print("Neto: %s Bs" % ("-" if neto is None else neto))
    if not confirmar("Guardar?"):
        print("cancelado")
        return None
    try:
        jid = repo.crear_jornada(
            conn, fecha.isoformat(), estado,
            partidos_total=partidos, bruto=bruto,
            torneo_id=torneo_id, nota=nota or None,
        )
        for concepto, monto in elegidos:
            repo.agregar_descuento(conn, jid, concepto["id"], monto)
    except ErrorValidacion as error:
        print("  error: %s" % error)
        return None
    print("guardada jornada #%d" % jid)
    return jid


def _pedir_torneo(conn):
    texto = pedir_texto("Torneo", "")
    if not texto:
        return None
    torneo = repo.buscar_torneo(conn, texto)
    if torneo:
        return torneo["id"]
    candidatos = [t for t in repo.listar_torneos(conn)
                  if normalizar(texto) in normalizar(t["nombre"])]
    elegido = elegir_de_lista("Coincidencias", candidatos,
                              formato=lambda t: t["nombre"])
    if elegido:
        return elegido["id"]
    if confirmar("No existe. Crear torneo %r?" % texto):
        return repo.obtener_o_crear_torneo(conn, texto)
    return None


# ---------------------------------------------------------------- historial

def historial(conn):
    jornadas = repo.listar_jornadas(conn, limite=20)
    vista.tabla_jornadas(jornadas)
    _ver_detalle_opcional(conn)


def buscar(conn):
    print("Buscar por: 1) rango de fechas 2) estado 3) torneo 4) texto en nota 5) todo")
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
        filtros["torneo_texto"] = pedir_texto("Torneo contiene", "")
    elif opcion == "4":
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
            print("(id inexistente)")


# ---------------------------------------------------------------- edicion

def editar(conn, jornada_id=None):
    if jornada_id is None:
        texto = _leer("Id de la jornada: ")
        if not texto.isdigit():
            return
        jornada_id = int(texto)
    jornada = repo.obtener_jornada(conn, jornada_id)
    if not jornada:
        print("(id inexistente)")
        return
    vista.detalle_jornada(conn, jornada)
    cambios = {}
    while True:
        campo = _leer("[f]echa [e]stado [p]artidos [b]ruto [t]orneo [n]ota [c]erteza [d]escuentos [g]uardar [k]BORRAR [x]salir: ").lower()
        try:
            if campo == "f":
                cambios["fecha"] = pedir_fecha("Fecha").isoformat()
            elif campo == "e":
                cambios["estado"] = pedir_estado()
            elif campo == "p":
                cambios["partidos_total"] = pedir_partidos("Partidos", permitir_nulo=True)
            elif campo == "b":
                cambios["bruto"] = pedir_monto("Ingreso bruto", permitir_nulo=True)
            elif campo == "t":
                cambios["torneo_id"] = _pedir_torneo(conn)
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
                    print("actualizada")
                return
            elif campo == "k":
                if confirmar("Borrar jornada #%d? Esta acción no se puede deshacer" % jornada_id, default=False):
                    if _leer("Escriba SI para confirmar: ") == "SI":
                        try:
                            from .db import respaldar
                            bkp = respaldar()
                            print(f"  backup: {bkp}")
                        except Exception:
                            pass
                        repo.eliminar_jornada(conn, jornada_id)
                        print("jornada eliminada")
                        return
                    print("cancelado")
                else:
                    print("cancelado")
            elif campo == "x":
                print("sin guardar cambios" if cambios else "")
                return
        except ErrorValidacion as error:
            print("  error: %s" % error)


def _editar_descuentos(conn, jornada_id):
    while True:
        descuentos = repo.descuentos_de(conn, jornada_id)
        for d in descuentos:
            print("  #%d %-10s %5d Bs %s" % (
                d["id"], d["concepto_nombre"], d["monto"], d["nota"] or ""))
        opcion = _leer("[a]gregar [e]ditar monto [b]orrar [v]olver: ").lower()
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
                                     formato=lambda d: "%s %d" % (d["concepto_nombre"], d["monto"]))
            if actual:
                repo.actualizar_descuento(conn, actual["id"],
                                          monto=pedir_monto("Nuevo monto"))
        elif opcion == "b":
            actual = elegir_de_lista("Descuento", descuentos,
                                     formato=lambda d: "%s %d" % (d["concepto_nombre"], d["monto"]))
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
        print("(id inexistente)")
        return
    vista.detalle_jornada(conn, jornada)
    respuesta = _leer("Escriba SI para eliminar: ")
    if respuesta == "SI":
        try:
            from .db import respaldar
            print(f"  backup: {respaldar()}")
        except Exception:
            pass
        repo.eliminar_jornada(conn, jornada_id)
        print("eliminada")
    else:
        print("cancelado")


# ---------------------------------------------------------------- estadisticas

def estadisticas(conn):
    while True:
        print("\nEstadisticas: 1) resumen 2) por mes 3) por anio"
              " 4) por torneo 5) descuentos por concepto"
              " 6) mejores jornadas 7) jornadas por estado 0) volver")
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
            desde, hasta = _pedir_rango()
            stats.imprimir_tabla_estadistica(
                "POR TORNEO", stats.por_torneo(conn, desde, hasta), clave_periodo="torneo")
        elif opcion == "5":
            año = _pedir_año()
            stats.imprimir_descuentos_por_concepto(
                stats.descuentos_por_concepto(conn, "%s-01-01" % año, "%s-12-31" % año),
                titulo="DESCUENTOS %s" % año)
        elif opcion == "6":
            cantidad = pedir_monto("Cantidad de jornadas", default=5)
            desde, hasta = _pedir_rango()
            _imprimir_mejores(conn, int(cantidad), desde, hasta)
        elif opcion == "7":
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
    print("MEJORES JORNADAS")
    for f in filas:
        print("  %s  neto %5d Bs  (bruto %d - desc %d)%s" % (
            f["fecha"], f["neto"], f["bruto"], f["descuentos"],
            "  %.1f part" % f["partidos"] if f["partidos"] else ""))


# ---------------------------------------------------------------- importación

def importar_historico(conn):
    ruta = pedir_texto("Archivo del historico", "historico/historico.txt")
    try:
        with open(ruta, encoding="utf-8") as archivo:
            texto = archivo.read()
    except OSError as error:
        print("  no se pudo leer: %s" % error)
        return
    año_inicial = _pedir_año_inicial()
    mapas = importador.Mapas(conn)
    resultado = importador.parsear(texto, mapas, ano_inicial=año_inicial)
    print(importador.reporte(resultado))
    if not confirmar("Aplicar a la base? (se crea backup antes)", default=False):
        print("dry-run solamente; nada fue escrito")
        return
    backup = respaldar()
    print("backup: %s" % backup)
    conteo = importador.aplicar(resultado, conn)
    print("insertadas: %(jornadas)d jornadas, %(descuentos)d descuentos,"
          " %(issues)d issues a revision" % conteo)


def _pedir_año_inicial():
    texto = pedir_texto("Anio inicial del historico", "2024")
    return int(texto) if texto.isdigit() else 2024


def review(conn):
    pendientes = repo.issues_pendientes(conn)
    if not pendientes:
        print("cola de revision vacia")
        return
    for i, issue in enumerate(pendientes, 1):
        linea = issue["linea"][:60]
        print("%2d) [%s] %s" % (i, issue["problema"], linea))
    elegido = elegir_de_lista("Issue a revisar", pendientes,
                              formato=lambda i: i["problema"])
    if not elegido:
        return
    print("linea     : %s" % elegido["linea"])
    print("problema  : %s" % elegido["problema"])
    print("sugerencia: %s" % (elegido["sugerencia"] or "-"))
    if elegido.get("payload"):
        datos = json.loads(elegido["payload"])
        print("datos     : %s" % json.dumps(datos, ensure_ascii=False))
    opcion = _leer("[r]esuelta [a]lta manual [Enter] dejar pendiente: ").lower()
    if opcion == "r":
        repo.marcar_issue_resuelta(conn, elegido["id"])
        print("marcada resuelta")
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
        print("\nConfiguracion: 1) conceptos 2) torneos 0) volver")
        opcion = _leer("Opcion: ")
        if opcion == "0":
            return
        if opcion == "1":
            _config_conceptos(conn)
        elif opcion == "2":
            _config_torneos(conn)


def _config_conceptos(conn):
    while True:
        conceptos = repo.listar_conceptos(conn)
        for c in conceptos:
            estado = "activo" if c["activo"] else "INACTIVO"
            print("  #%-2d %-10s def=%-3d %s  aliases: %s" % (
                c["id"], c["nombre"], c["default_monto"], estado, c["aliases"] or "-"))
        opcion = _leer("[c]rear [r]enombrar [a]ctivar/desactivar [d]efault [l]aliases [v]olver: ").lower()
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
        elif opcion == "a":
            repo.set_concepto_activo(conn, elegido["id"], not elegido["activo"])
        elif opcion == "d":
            repo.set_concepto_default(conn, elegido["id"], pedir_monto("Default", default=0))
        elif opcion == "l":
            repo.set_concepto_aliases(conn, elegido["id"], pedir_texto("Aliases", elegido["aliases"] or ""))


def exportar_menu(conn):
    print("\nExportar: 1) CSV  2) XLSX  3) XLS  0) volver")
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


def _config_torneos(conn):
    for t in repo.listar_torneos(conn):
        print("  %s" % t["nombre"])
    if confirmar("Crear torneo nuevo?"):
        nombre = pedir_texto("Nombre", "")
        if nombre:
            repo.obtener_o_crear_torneo(conn, nombre)
