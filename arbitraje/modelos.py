"""Dominio: enums, tokens del histórico, semillas y reglas de derivación."""

import unicodedata
from enum import Enum


class Estado(str, Enum):
    ARBITRADO = "ARBITRADO"
    NO_DESIGNADO = "NO_DESIGNADO"
    NO_HUBO = "NO_HUBO"
    LLUVIA = "LLUVIA"
    ELECCIONES = "ELECCIONES"
    VIAJE = "VIAJE"
    DESCANSO = "DESCANSO"
    RECHAZADO = "RECHAZADO"
    SIN_DATOS = "SIN_DATOS"
    OTRO = "OTRO"
    FERIADO = "FERIADO"


class Certeza(str, Enum):
    CONFIRMADO = "CONFIRMADO"
    PROBABLE = "PROBABLE"
    DUDOSO = "DUDOSO"


# Rótulos de día -> número ISO (0=lunes .. 6=domingo). Incluye typos del histórico.
DIAS_SEMANA = {
    "lun": 0, "mar": 1, "mie": 2, "jue": 3,
    "vie": 4, "vier": 4, "vue": 4,
    "sab": 5, "dom": 6,
}

MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "set": 9, "oct": 10, "nov": 11, "dic": 12,
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}


def normalizar(texto):
    """Minúsculas sin tildes, para comparaciones insensibles."""
    texto = unicodedata.normalize("NFD", texto.strip().lower())
    return "".join(c for c in texto if not unicodedata.combining(c))


# Tokens de estado reconocidos (clave normalizada).
ESTADO_TOKENS = {
    "no designado": Estado.NO_DESIGNADO,
    "no hubo": Estado.NO_HUBO,
    "lluvia": Estado.LLUVIA,
    "elecciones": Estado.ELECCIONES,
    "viaje": Estado.VIAJE,
    "descanso": Estado.DESCANSO,
    "rechaze": Estado.RECHAZADO,
    "rechazado": Estado.RECHAZADO,
    "dia del peaton": Estado.FERIADO,
    "todos santos": Estado.FERIADO,
    "sin datos": Estado.SIN_DATOS,
}

# Tokens ambiguos: a cola de revisión con sugerencia, sin insertar.
TOKENS_AMBIGUOS = {
    "nada": Estado.NO_DESIGNADO,
    "descanso/viaje": Estado.DESCANSO,
}

# Frases de duda explícita del histórico.
FRASE_DUDA = "no recuerdo"

CONCEPTOS_SEED = [
    # (nombre, default_monto, orden, aliases normalizados separados por coma)
    ("Asesoría", 10, 1, "a,asesor,asesoria"),
    ("Caja", 0, 2, "c"),
    ("Polera", 0, 3, "pol,polera"),
    ("Fondo", 0, 4, "f"),
    ("Multa", 0, 5, ""),
    ("Soda", 0, 6, "soda"),
    ("Rifa", 0, 7, "rifa"),
    ("Aporte", 0, 8, "aporte"),
    ("Cena", 0, 9, "cena"),
    ("Preste", 0, 10, "pres,preste"),
    ("Ali", 0, 11, "ali"),
    ("Rider", 0, 12, "rider,perdida rider"),
    ("Reemplazo", 0, 13, "rplzo,reemplazo"),
    ("1ro M", 0, 14, "1ro m"),
    ("Otros", 0, 15, "otros"),
    ("Deuda", 0, 16, "deuda"),
]

TORNEOS_SEED = ["Ribereña", "Paisanos", "La Salle", "Villa Vecinal", "LIFJUVE", "Coca Cola"]


def validar_jornada(estado, bruto, partidos_total=None):
    """Reglas duras del dominio. Devuelve lista de errores (vacía si ok)."""
    errores = []
    if estado != Estado.ARBITRADO and bruto is not None:
        errores.append("solo ARBITRADO puede tener bruto")
    if bruto is not None and bruto < 0:
        errores.append("bruto negativo")
    if partidos_total is not None and partidos_total < 0:
        errores.append("partidos negativos")
    return errores


def calcular_neto(bruto, total_descuentos):
    """Neto siempre derivado; bruto NULL => neto NULL."""
    if bruto is None:
        return None
    return bruto - (total_descuentos or 0)
