"""Punto de entrada CLI: subcomandos + menú interactivo por defecto."""

import argparse

from . import db, export, importador, menu, repo, stats, vista
from .modelos import Estado


def _construir_parser():
    parser = argparse.ArgumentParser(
        prog="arbitraje",
        description="Registro y análisis de ingresos por arbitraje.",
    )
    sub = parser.add_subparsers(dest="comando")

    sub.add_parser("add", help="registrar jornada (interactivo)")

    p_list = sub.add_parser("list", help="últimas jornadas")
    p_list.add_argument("--limite", type=int, default=20)
    p_list.add_argument("--estado", default=None)
    p_list.add_argument("--desde", default=None)
    p_list.add_argument("--hasta", default=None)
    p_list.add_argument("--torneo", default=None)

    p_search = sub.add_parser("search", help="buscar jornadas")
    p_search.add_argument("--estado", default=None)
    p_search.add_argument("--desde", default=None)
    p_search.add_argument("--hasta", default=None)
    p_search.add_argument("--torneo", default=None)
    p_search.add_argument("--nota", default=None)

    p_stats = sub.add_parser("stats", help="estadísticas")
    p_stats.add_argument("--anio", default=None, dest="anio")
    p_stats.add_argument("--desde", default=None)
    p_stats.add_argument("--hasta", default=None)

    p_edit = sub.add_parser("edit", help="editar jornada")
    p_edit.add_argument("id", type=int)

    p_del = sub.add_parser("delete", help="eliminar jornada")
    p_del.add_argument("id", type=int)

    p_import = sub.add_parser("import", help="importar histórico")
    p_import.add_argument("archivo")
    p_import.add_argument("--commit", action="store_true",
                          help="escribir en la base (por defecto solo reporta)")
    p_import.add_argument("--ano-inicial", type=int, default=2024, dest="ano_inicial")

    sub.add_parser("review", help="revisar excepciones de importación")

    p_export = sub.add_parser("export", help="exportar (csv/xlsx/xls)")
    p_export.add_argument("directorio", nargs="?", default=".")
    p_export.add_argument("--formato", default="csv", choices=["csv","xlsx","xls"], help="formato de salida")

    sub.add_parser("config", help="configurar conceptos y torneos")

    return parser


def main(argv=None):
    parser = _construir_parser()
    args = parser.parse_args(argv)
    conn = db.conectar()
    try:
        _despachar(conn, args, parser)
    finally:
        conn.close()


def _despachar(conn, args, parser):
    comando = args.comando
    if comando is None:
        menu.run(conn)
    elif comando == "add":
        menu.registrar(conn)
    elif comando == "list":
        vista.tabla_jornadas(repo.listar_jornadas(
            conn,
            fecha_desde=args.desde, fecha_hasta=args.hasta,
            estado=Estado(args.estado) if args.estado else None,
            torneo_texto=args.torneo, limite=args.limite,
        ))
    elif comando == "search":
        vista.tabla_jornadas(repo.listar_jornadas(
            conn,
            fecha_desde=args.desde, fecha_hasta=args.hasta,
            estado=Estado(args.estado) if args.estado else None,
            torneo_texto=args.torneo, texto_nota=args.nota,
        ))
    elif comando == "stats":
        _stats_no_interactivo(conn, args)
    elif comando == "edit":
        menu.editar(conn, args.id)
    elif comando == "delete":
        menu.eliminar(conn, args.id)
    elif comando == "import":
        _importar(conn, args)
    elif comando == "review":
        menu.review(conn)
    elif comando == "export":
        rutas = export.exportar(conn, args.directorio, formato=args.formato)
        for ruta in rutas:
            print(ruta)
    elif comando == "config":
        menu.configuracion(conn)


def _stats_no_interactivo(conn, args):
    desde, hasta = args.desde, args.hasta
    anio = args.anio
    if anio:
        desde, hasta = "%s-01-01" % anio, "%s-12-31" % anio
    print("RESUMEN")
    stats.imprimir_resumen(stats.resumen_general(conn, desde, hasta))
    stats.imprimir_tabla_estadistica(
        "\nPOR MES", stats.por_periodo(conn, "%Y-%m", desde, hasta))
    stats.imprimir_tabla_estadistica(
        "\nPOR ANIO", stats.por_periodo(conn, "%Y", desde, hasta))
    stats.imprimir_tabla_estadistica(
        "\nPOR TORNEO", stats.por_torneo(conn, desde, hasta), clave_periodo="torneo")
    stats.imprimir_descuentos_por_concepto(
        stats.descuentos_por_concepto(conn, desde, hasta), titulo="\nDESCUENTOS")


def _importar(conn, args):
    try:
        with open(args.archivo, encoding="utf-8") as archivo:
            texto = archivo.read()
    except OSError as error:
        raise SystemExit("no se pudo leer %s: %s" % (args.archivo, error))
    mapas = importador.Mapas(conn)
    resultado = importador.parsear(texto, mapas, ano_inicial=args.ano_inicial)
    print(importador.reporte(resultado))
    if not args.commit:
        print("\ndry-run: nada fue escrito. Usar --commit para aplicar.")
        return
    backup = db.respaldar()
    print("backup: %s" % backup)
    conteo = importador.aplicar(resultado, conn)
    print("insertadas: %(jornadas)d jornadas, %(descuentos)d descuentos,"
          " %(issues)d issues a revision" % conteo)


if __name__ == "__main__":
    main()
