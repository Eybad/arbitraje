"""Conexión SQLite, esquema, migraciones y semillas."""

import os
import sqlite3
from pathlib import Path

from .modelos import CONCEPTOS_SEED

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS conceptos_descuento (
    id            INTEGER PRIMARY KEY,
    nombre        TEXT NOT NULL UNIQUE,
    activo        INTEGER NOT NULL DEFAULT 1 CHECK (activo IN (0, 1)),
    default_monto INTEGER NOT NULL DEFAULT 0 CHECK (default_monto >= 0),
    orden         INTEGER,
    aliases       TEXT
);

CREATE TABLE IF NOT EXISTS jornadas (
    id             INTEGER PRIMARY KEY,
    fecha          TEXT NOT NULL,             -- ISO AAAA-MM-DD
    estado         TEXT NOT NULL CHECK (estado IN (
        'ARBITRADO', 'NO_DESIGNADO', 'NO_HUBO', 'LLUVIA', 'ELECCIONES',
        'VIAJE', 'DESCANSO', 'RECHAZADO', 'SIN_DATOS', 'OTRO', 'FERIADO')),
    partidos_total REAL CHECK (partidos_total IS NULL OR partidos_total >= 0),
    roles_detalle  TEXT,
    bruto          INTEGER CHECK (bruto IS NULL OR bruto >= 0),
    certeza        TEXT NOT NULL DEFAULT 'CONFIRMADO'
                    CHECK (certeza IN ('CONFIRMADO', 'PROBABLE', 'DUDOSO')),
    nota           TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jornadas_fecha ON jornadas(fecha);

CREATE TABLE IF NOT EXISTS descuentos (
    id          INTEGER PRIMARY KEY,
    jornada_id  INTEGER NOT NULL REFERENCES jornadas(id) ON DELETE CASCADE,
    concepto_id INTEGER NOT NULL REFERENCES conceptos_descuento(id),
    monto       INTEGER NOT NULL CHECK (monto >= 0),
    nota        TEXT,
    UNIQUE (jornada_id, concepto_id)
);

CREATE TABLE IF NOT EXISTS import_issues (
    id         INTEGER PRIMARY KEY,
    linea      TEXT NOT NULL,
    problema   TEXT NOT NULL,
    sugerencia TEXT,
    payload    TEXT,
    resuelto   INTEGER NOT NULL DEFAULT 0 CHECK (resuelto IN (0, 1)),
    created_at TEXT NOT NULL
);
"""


def db_path():
    """Ruta de la base: ARBITRAJE_DB o ~/.local/share/arbitraje/arbitraje.db."""
    entorno = os.environ.get("ARBITRAJE_DB")
    if entorno:
        return Path(entorno).expanduser()
    return Path.home() / ".local" / "share" / "arbitraje" / "arbitraje.db"


def _chmod_600(path):
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _chmod_700(path):
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass


def conectar(ruta=None):
    """Abre la base, aplica esquema y semillas. foreign_keys siempre ON."""
    ruta = Path(ruta) if ruta else db_path()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    _chmod_700(ruta.parent)
    conn = sqlite3.connect(str(ruta))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    inicializar(conn)
    # hardening: DB 0600 best-effort (umask puede dejar 644)
    _chmod_600(ruta)
    return conn


def inicializar(conn):
    conn.executescript(_SCHEMA)
    fila = conn.execute("SELECT version FROM schema_version").fetchone()
    if fila is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    else:
        version_actual = fila[0]
        if version_actual < 2:
            _migrar_1_a_2(conn)
            conn.execute("UPDATE schema_version SET version = ?", (SCHEMA_VERSION,))
    _sembrar(conn)
    conn.commit()


def _migrar_1_a_2(conn):
    """Migra v1→v2: vuelca torneos a nota y hace drop duro."""
    # Detectar si existe la tabla/columnas v1
    tablas = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "torneos" not in tablas:
        # Verificar si jornadas aún tiene torneo_id
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jornadas)")}
        if "torneo_id" not in cols:
            return
    # Volcar torneo a nota con formato [Torneo: X] ; nota
    cols_j = {r[1] for r in conn.execute("PRAGMA table_info(jornadas)")}
    tiene_torneo_id = "torneo_id" in cols_j
    tiene_torneos = "torneos" in tablas
    if tiene_torneo_id and tiene_torneos:
        filas = conn.execute(
            "SELECT j.id, j.nota, t.nombre AS torneo_nombre "
            "FROM jornadas j LEFT JOIN torneos t ON t.id = j.torneo_id "
            "WHERE t.nombre IS NOT NULL"
        ).fetchall()
        for fid, nota, torneo_nombre in filas:
            if nota and "[Torneo:" in nota:
                continue  # ya migrada
            prefijo = f"[Torneo: {torneo_nombre}]"
            nueva = prefijo if not nota else f"{prefijo} ; {nota}"
            conn.execute("UPDATE jornadas SET nota = ? WHERE id = ?", (nueva, fid))
    elif tiene_torneo_id and not tiene_torneos:
        # torneo_id huérfano sin tabla — solo limpiar columna luego
        pass
    # Drop columna torneo_id y tabla torneos (SQLite >=3.35)
    if tiene_torneo_id:
        try:
            conn.execute("ALTER TABLE jornadas DROP COLUMN torneo_id")
        except Exception:
            # Fallback: recrear tabla sin torneo_id (para SQLite viejo)
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS jornadas_new (
                    id             INTEGER PRIMARY KEY,
                    fecha          TEXT NOT NULL,
                    estado         TEXT NOT NULL CHECK (estado IN (
                        'ARBITRADO', 'NO_DESIGNADO', 'NO_HUBO', 'LLUVIA', 'ELECCIONES',
                        'VIAJE', 'DESCANSO', 'RECHAZADO', 'SIN_DATOS', 'OTRO', 'FERIADO')),
                    partidos_total REAL CHECK (partidos_total IS NULL OR partidos_total >= 0),
                    roles_detalle  TEXT,
                    bruto          INTEGER CHECK (bruto IS NULL OR bruto >= 0),
                    certeza        TEXT NOT NULL DEFAULT 'CONFIRMADO'
                                   CHECK (certeza IN ('CONFIRMADO', 'PROBABLE', 'DUDOSO')),
                    nota           TEXT,
                    created_at     TEXT NOT NULL,
                    updated_at     TEXT NOT NULL
                );
                INSERT INTO jornadas_new (id, fecha, estado, partidos_total, roles_detalle, bruto, certeza, nota, created_at, updated_at)
                    SELECT id, fecha, estado, partidos_total, roles_detalle, bruto, certeza, nota, created_at, updated_at FROM jornadas;
                DROP TABLE jornadas;
                ALTER TABLE jornadas_new RENAME TO jornadas;
                CREATE INDEX IF NOT EXISTS idx_jornadas_fecha ON jornadas(fecha);
            """)
    if "torneos" in tablas:
        conn.execute("DROP TABLE IF EXISTS torneos")


def _sembrar(conn):
    for nombre, default_monto, orden, aliases in CONCEPTOS_SEED:
        conn.execute(
            "INSERT OR IGNORE INTO conceptos_descuento (nombre, activo, default_monto, orden, aliases)"
            " VALUES (?, 1, ?, ?, ?)",
            (nombre, default_monto, orden, aliases),
        )


def respaldar(ruta=None):
    """Copia timestamped de la base; devuelve la ruta del backup."""
    import shutil
    import time
    ruta = Path(ruta) if ruta else db_path()
    destino = Path(str(ruta) + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
    shutil.copy2(str(ruta), str(destino))
    _chmod_600(destino)
    return destino
