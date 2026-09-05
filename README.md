# arbitraje

CLI interactiva local para registrar y analizar ingresos por arbitraje.
Python 3 + SQLite, solo biblioteca estándar. Pensada para Termux.

## Uso

    arbitraje              menu interactivo
    arbitraje add          registrar jornada rapida
    arbitraje list         ultimas jornadas (opciones: --desde/--hasta/--estado/--nota/--limite/--plain/--json)
    arbitraje search       buscar (--estado/--desde/--hasta/--nota)
    arbitraje stats        estadisticas (--anio/--desde/--hasta/--plain/--json)
    arbitraje edit ID      editar jornada
    arbitraje delete ID    eliminar jornada (pide confirmacion)
    arbitraje import FILE  importar historico (dry-run por defecto, --commit aplica)
    arbitraje review       revisar excepciones de importacion
    arbitraje export DIR   exportar CSV/XLSX/XLS (--formato csv|xlsx|xls)
    arbitraje --version    version

Notas: --torneo obsoleto (usar --nota "[Torneo: X]"), salida Rich opcional si está instalado (fallback stdlib), respetar NO_COLOR y TTY.

## Base de datos

Por defecto en `~/.local/share/arbitraje/arbitraje.db`.
Override con la variable `ARBITRAJE_DB`.

## Instalacion del comando global

    mkdir -p ~/bin && cat > ~/bin/arbitraje << 'EOF'
    #!/data/data/com.termux/files/usr/bin/sh
    set -eu
    PYTHONPATH="$HOME/proyectos/arbitraje${PYTHONPATH:+:$PYTHONPATH}"
    export PYTHONPATH
    exec python3 -P -m arbitraje "$@"
    EOF
    chmod +x ~/bin/arbitraje

## Desarrollo

    python3 -m unittest discover -s tests -v

El historico personal vive en `historico/` y no se versiona.
Ver `CONTEXT.md` para el glosario del dominio.
