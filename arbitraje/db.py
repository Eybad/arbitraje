"""Conexión SQLite, esquema, migraciones y semillas."""

import os
import sqlite3
from pathlib import Path

from .modelos import CONCEPTOS_SEED, TORNEOS_SEED

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS torneos (
    id     INTEGER PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE
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
    torneo_id      INTEGER REFERENCES torneos(id),
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


def conectar(ruta=None):
    """Abre la base, aplica esquema y semillas. foreign_keys siempre ON."""
    ruta = Path(ruta) if ruta else db_path()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(ruta))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    inicializar(conn)
    return conn


def inicializar(conn):
    conn.executescript(_SCHEMA)
    fila = conn.execute("SELECT version FROM schema_version").fetchone()
    if fila is None:
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
    _sembrar(conn)
    conn.commit()


def _sembrar(conn):
    for nombre, default_monto, orden, aliases in CONCEPTOS_SEED:
        conn.execute(
            "INSERT OR IGNORE INTO conceptos_descuento (nombre, activo, default_monto, orden, aliases)"
            " VALUES (?, 1, ?, ?, ?)",
            (nombre, default_monto, orden, aliases),
        )
    for nombre in TORNEOS_SEED:
        conn.execute("INSERT OR IGNORE INTO torneos (nombre) VALUES (?)", (nombre,))
