"""Importador del histórico de texto.

Reglas congeladas en el plan v2 (ver CONTEXT.md):
- Los valores tras '=' son NETOS: bruto = valor + suma(descuentos) (+ marcador *N*).
- El rótulo del día manda sobre la fecha escrita (offset uniforme por bloque).
- Nada se inventa: lo ambiguo va a la cola de revisión (import_issues).
"""

import json
import re
from datetime import date, timedelta

from .modelos import (
    Certeza, DIAS_SEMANA, ESTADO_TOKENS, Estado, FRASE_DUDA, MESES,
    TOKENS_AMBIGUOS, normalizar,
)
from . import repo

RE_ANO = re.compile(r"^(\d{4})$")
RE_BLOQUE = re.compile(r"^\d+[A-Za-z]*\s*\)\s*")
RE_TOTAL = re.compile(r"^total\b")
RE_NUMEROS = re.compile(r"\d+(?:[.,]\d+)?")
RE_PARENS = re.compile(r"\([^)]*\)")
RE_MARCADOR_DEUDA = re.compile(r"\*\s*-?\s*(\d+)\s*\*")
RE_TOKEN_DESCUENTO = re.compile(r"-\s*(\d+(?:[.,]\d+)?)\s*(.*)$")
# Número standalone en el resto del token: indica una segunda cifra real
# ("y 150 ya pagados"). Los ordinales tipo "1ro M" no cuentan (dígito pegado a letras).
RE_NUMERO_SUELTO = re.compile(r"(?<![\w.])\d+(?![\w])")

_RE_DIA = re.compile(
    r"^(lun|mar|mie|jue|vier|vue|vie|sab|dom)"
    r"(?:\s+(\d{1,2})\s+(?:de\s+)?([a-záéíóúñ]+))?"
    r"\s*:?\s*(.*)$",
    re.IGNORECASE,
)

_DIAS = {normalizar(k): v for k, v in DIAS_SEMANA.items()}


class Mapas:
    """Catálogos cargados una vez por corrida del importador."""

    def __init__(self, conn):
        self.conceptos = repo.mapa_aliases(conn)
        self.otros = self._concepto_por_nombre("Otros")
        self.deuda = self._concepto_por_nombre("Deuda")
        self.torneos = {
            normalizar(t["nombre"]): t["nombre"]
            for t in repo.listar_torneos(conn)
        }

    def _concepto_por_nombre(self, nombre):
        for par in self.conceptos.values():
            if par[1] == nombre:
                return par
        return None


class LineaDia:
    def __init__(self, texto, dia_idx, numero, mes_txt, contenido):
        self.texto = texto
        self.dia_idx = dia_idx
        self.numero = numero
        self.mes_txt = normalizar(mes_txt) if mes_txt else None
        self.contenido = contenido
        self.nota_ajuste = None
        self.adjuntas = []  # líneas "-nota" sueltas asociadas a este día
        self.seccion = None  # torneo de encabezado vigente al cargar la línea


class Candidato:
    def __init__(self, fecha, linea):
        self.fecha = fecha
        self.linea = linea
        self.estado = Estado.SIN_DATOS
        self.certeza = Certeza.CONFIRMADO
        self.partidos = None
        self.roles_detalle = None
        self.valor_neto = None
        self.bruto = None
        self.torneo = None
        self.notas = []
        self.descuentos = {}   # concepto_id -> {nombre, monto, notas}
        self.bloqueado = None

    def nota(self, texto):
        if texto and texto not in self.notas:
            self.notas.append(texto)


class Resultado:
    def __init__(self):
        self.candidatos = []
        self.issues = []
        self.recalculadas = 0
        self.fechas_usadas = set()

    def issue(self, linea, problema, sugerencia=None, candidato=None):
        payload = None
        if candidato is not None:
            payload = json.dumps({
                "fecha": candidato.fecha.isoformat() if candidato.fecha else None,
                "estado": candidato.estado.value,
                "partidos": candidato.partidos,
                "bruto": candidato.bruto,
                "torneo": candidato.torneo,
                "notas": candidato.notas,
            }, ensure_ascii=False)
        self.issues.append({
            "linea": linea, "problema": problema,
            "sugerencia": sugerencia, "payload": payload,
        })


# ---------------------------------------------------------------- parsing

def parsear(texto, mapas, ano_inicial=2024):
    resultado = Resultado()
    estado_ano = {"año": ano_inicial, "mes_previo": None}
    torneo_seccion = None
    bucket = []
    ultimo_candidato = []

    def volcar():
        nonlocal bucket, torneo_seccion
        _volcar(bucket, estado_ano, resultado, mapas)
        bucket = []
        torneo_seccion = None

    def agregar_dia(texto_dia):
        linea_dia = _linea_dia(texto_dia)
        linea_dia.seccion = torneo_seccion
        bucket.append(linea_dia)

    for cruda in texto.splitlines():
        linea = cruda.strip()
        if not linea:
            continue
        if RE_ANO.match(linea):
            volcar()
            estado_ano["año"] = int(linea)
            estado_ano["mes_previo"] = None
            continue
        if RE_TOTAL.match(normalizar(linea)):
            continue
        sin_bloque = RE_BLOQUE.sub("", linea).strip()
        if sin_bloque != linea:
            volcar()
            linea = sin_bloque
            if not linea:
                continue

        if linea.startswith("-"):
            interior = linea.lstrip("-").strip()
            if interior and _es_linea_dia(interior):
                agregar_dia(interior)
            elif interior and bucket:
                # Nota suelta referida al último día pendiente del bloque.
                bucket[-1].adjuntas.append(interior)
            elif interior and ultimo_candidato:
                ultimo_candidato[0].nota(interior)
            continue

        if _es_linea_dia(linea):
            agregar_dia(linea)
            continue

        if linea.endswith(":"):
            torneo_seccion = _limpiar_encabezado(linea.rstrip(":").strip())
            continue

        volcar()
        # Línea suelta sin fecha: puede ser un estado de semana completa.
        clave = normalizar(linea)
        sugerencia = None
        for token, est in TOKENS_AMBIGUOS.items():
            if normalizar(token) in clave:
                sugerencia = est.value
        if sugerencia or any(normalizar(t) in clave for t in ESTADO_TOKENS):
            resultado.issue(linea, "estado de semana sin fechas",
                            sugerencia=sugerencia or "crear jornadas manualmente")
        else:
            resultado.issue(linea, "línea no reconocida")

    _volcar(bucket, estado_ano, resultado, mapas)
    return resultado


def _es_linea_dia(texto):
    m = _RE_DIA.match(texto)
    if not m:
        return False
    etiqueta = normalizar(m.group(1))
    return etiqueta[:3] in _DIAS or etiqueta[:4] in _DIAS


def _linea_dia(texto):
    m = _RE_DIA.match(texto)
    etiqueta = normalizar(m.group(1))
    dia_idx = _DIAS.get(etiqueta[:3], _DIAS.get(etiqueta[:4]))
    numero = int(m.group(2)) if m.group(2) else None
    mes_txt = m.group(3)
    contenido = (m.group(4) or "").strip()
    return LineaDia(texto, dia_idx, numero, mes_txt, contenido)


def _limpiar_encabezado(nombre):
    limpio = normalizar(nombre)
    for prefijo in ("campeonato", "torneo", "copa"):
        if limpio.startswith(prefijo + " "):
            return nombre[len(prefijo) + 1:].strip()
    return nombre


# ------------------------------------------------------- resolución fechas

def _volcar(bucket, estado_ano, resultado, mapas):
    if not bucket:
        return
    fechas, certezas = _resolver_fechas(bucket, estado_ano, resultado)
    for linea, fecha, certeza in zip(bucket, fechas, certezas):
        if fecha is None:
            continue
        resultado.fechas_usadas.add(fecha)
        candidato = _construir_candidato(
            linea, fecha, certeza, resultado, mapas)
        for extra in linea.adjuntas:
            candidato.nota(extra)
        resultado.candidatos.append(candidato)


def _resolver_fechas(bucket, estado_ano, resultado):
    fechas = [None] * len(bucket)
    certezas = [Certeza.CONFIRMADO] * len(bucket)
    if estado_ano["año"] is None:
        for linea in bucket:
            resultado.issue(linea.texto, "línea antes de cualquier año conocido",
                            sugerencia="indicar --ano-inicial")
        return fechas, certezas

    año = estado_ano["año"]
    bases = {}
    meses = []
    for i, linea in enumerate(bucket):
        if not (linea.numero and linea.mes_txt):
            continue
        mes = MESES.get(linea.mes_txt)
        if mes is None or not 1 <= linea.numero <= 31:
            resultado.issue(linea.texto, "mes o día no reconocido")
            continue
        try:
            bases[i] = date(año, mes, linea.numero)
            meses.append(mes)
        except ValueError:
            resultado.issue(linea.texto, "fecha imposible según calendario",
                            sugerencia="%d-%02d: corregir el día" % (año, mes))

    # Rollover defensivo dic->ene sin encabezado de año.
    if meses and meses[-1] == 1 and estado_ano["mes_previo"] == 12:
        año += 1
        estado_ano["año"] = año
        bases = {}
        meses = []
        for i, linea in enumerate(bucket):
            if not (linea.numero and linea.mes_txt):
                continue
            mes = MESES.get(linea.mes_txt)
            if mes is None:
                continue
            try:
                bases[i] = date(año, mes, linea.numero)
                meses.append(mes)
            except ValueError:
                pass
    if meses:
        estado_ano["mes_previo"] = meses[-1]

    offset = None
    if bases:
        validos = []
        for candidato_offset in sorted(range(-10, 11), key=abs):
            if all((base + timedelta(days=candidato_offset)).weekday() ==
                   bucket[i].dia_idx for i, base in bases.items()):
                validos.append(candidato_offset)
        if validos:
            # Si offset=0 es válido por día-semana, se conserva aunque colisione:
            # es una doble jornada genuina del mismo día (decisión #1).
            if 0 in validos:
                offset = 0
            else:
                libres = [o for o in validos
                          if not any((base + timedelta(days=o)) in resultado.fechas_usadas
                                     for base in bases.values())]
                if libres:
                    offset = libres[0]
                else:
                    offset = validos[0]
                    resultado.issue(
                        "; ".join(l.texto for l in bucket),
                        "todas las alineaciones posibles colisionan con otras semanas",
                        sugerencia="verificar fechas manualmente")
    if offset is not None:
        for i, base in bases.items():
            fechas[i] = base + timedelta(days=offset)
            if offset != 0:
                certezas[i] = Certeza.PROBABLE
                resultado.recalculadas += 1
                bucket[i].nota_ajuste = "[fecha escrita: %d %s]" % (
                    bucket[i].numero, bucket[i].mes_txt)
    elif bases:
        # Sin offset uniforme: resolver línea a línea al día más cercano.
        for i, base in bases.items():
            alternativa = _mas_cercana(base, bucket[i].dia_idx)
            if alternativa and alternativa != base:
                fechas[i] = alternativa
                certezas[i] = Certeza.PROBABLE
                resultado.recalculadas += 1
            elif alternativa:
                fechas[i] = alternativa
            else:
                resultado.issue(bucket[i].texto,
                                "no se pudo alinear la fecha con el día de semana")
        resultado.issue(
            "; ".join(l.texto for l in bucket),
            "semana con fechas inconsistentes entre sí (resuelta línea a línea)",
            sugerencia="verificar manualmente")

    ancla = next(((i, f) for i, f in enumerate(fechas) if f is not None), None)
    for i, linea in enumerate(bucket):
        if fechas[i] is None and linea.numero is None and ancla is not None:
            _, af = ancla
            delta = (af.weekday() - linea.dia_idx) % 7
            fechas[i] = af - timedelta(days=delta)
    for i, linea in enumerate(bucket):
        if fechas[i] is None:
            resultado.issue(linea.texto, "día sin fecha derivable",
                            sugerencia="completar fecha manualmente")
    return fechas, certezas


def _mas_cercana(base, dia_idx):
    for distancia in range(0, 11):
        for signo in (1, -1):
            candidata = base + timedelta(days=signo * distancia)
            if candidata.weekday() == dia_idx:
                return candidata
    return None


# ------------------------------------------------------------ contenido

def _construir_candidato(linea, fecha, certeza, resultado, mapas):
    c = Candidato(fecha, linea.texto)
    c.certeza = certeza
    if linea.nota_ajuste:
        c.nota(linea.nota_ajuste)
    contenido = linea.contenido

    if linea.seccion:
        c.torneo = mapas.torneos.get(normalizar(linea.seccion), linea.seccion)

    if not contenido:
        return c  # placeholder vacío -> SIN_DATOS

    if normalizar(contenido).startswith(FRASE_DUDA):
        c.nota(contenido)
        c.certeza = Certeza.DUDOSO
        return c

    if "=" in contenido:
        izquierda, derecha = contenido.split("=", 1)
    elif RE_NUMEROS.match(contenido):
        izquierda, derecha = "", contenido
    else:
        izquierda, derecha = contenido, ""

    _parsear_partidos(c, izquierda.strip())
    _parsear_lado_valor(c, derecha.strip(), resultado, mapas)
    _aplicar_marcador_deuda(c, mapas)
    _detectar_ambiguos(c, contenido, resultado)
    _aplicar_estado(c, contenido)
    _calcular_bruto(c)
    return c


def _aplicar_marcador_deuda(c, mapas):
    """Marcador *N*: deducción por deuda ya descontada del valor neto."""
    if c.valor_neto is None or not mapas.deuda:
        return
    m = RE_MARCADOR_DEUDA.search(c.linea)
    if not m:
        return
    monto = int(m.group(1))
    entrada = c.descuentos.setdefault(mapas.deuda[0], {
        "id": mapas.deuda[0], "nombre": mapas.deuda[1], "monto": 0, "notas": []})
    entrada["monto"] += monto
    entrada["notas"].append("*-%d*" % monto)


def _parsear_partidos(c, texto):
    if not texto:
        return
    limpio = RE_PARENS.sub(" ", texto)
    numeros = RE_NUMEROS.findall(limpio)
    if not numeros:
        return  # texto sin cifras: no es especificación de partidos
    c.roles_detalle = texto
    c.partidos = sum(float(n.replace(",", ".")) for n in numeros)


def _parsear_lado_valor(c, texto, resultado, mapas):
    if not texto:
        return
    m = RE_NUMEROS.search(texto)
    resto = texto
    if m and texto.lstrip().startswith(m.group(0)):
        c.valor_neto = int(float(m.group(0)))
        resto = texto[m.end():].strip()

    for grupo in RE_PARENS.findall(resto):
        interior = grupo[1:-1].strip()
        if "%" in interior:
            continue
        clave = normalizar(interior)
        if clave in mapas.torneos:
            c.torneo = mapas.torneos[clave]
            continue
        _parsear_grupo_descuentos(c, interior, resultado, mapas)

    sobrante = RE_PARENS.sub(" ", resto).strip()
    if sobrante:
        _parsear_trailing(c, sobrante, mapas)


def _parsear_grupo_descuentos(c, interior, resultado, mapas):
    for token in interior.split(","):
        token = token.strip()
        if not token:
            continue
        clave = normalizar(token)
        if clave in ESTADO_TOKENS or clave == "lluvia":
            c.nota("(%s)" % token)
            continue
        m = RE_TOKEN_DESCUENTO.match(token)
        if not m:
            if normalizar(token).isalpha():
                c.bloqueado = "descuento sin monto: %r" % token
                resultado.issue(c.linea, c.bloqueado,
                                sugerencia="completar monto del descuento",
                                candidato=c)
            else:
                c.nota("(%s)" % token)
            continue
        monto = int(float(m.group(1)))
        resto = m.group(2).strip()
        if RE_NUMERO_SUELTO.search(resto):
            c.bloqueado = "expresión de descuento no parseable: %r" % token
            resultado.issue(c.linea, c.bloqueado,
                            sugerencia="cargar el descuento manualmente",
                            candidato=c)
            continue
        if monto == 0:
            c.nota("(%s)" % token)
            continue
        concepto = _buscar_concepto(mapas, resto)
        if concepto is None:
            concepto = mapas.otros
        entrada = c.descuentos.setdefault(concepto[0], {
            "id": concepto[0], "nombre": concepto[1], "monto": 0, "notas": []})
        entrada["monto"] += monto
        entrada["notas"].append("(%s)" % token)


def _buscar_concepto(mapas, frase):
    frase = frase.strip(" -")
    if not frase:
        return None
    clave = normalizar(frase)
    par = mapas.conceptos.get(clave)
    if par:
        return par
    primera = normalizar(frase.split()[0])
    return mapas.conceptos.get(primera)


def _parsear_trailing(c, texto, mapas):
    normalizado = normalizar(texto)

    m_final = re.search(r"final\s+([\w\s]+)", normalizado)
    if m_final:
        torneo = _buscar_torneo_por_frase(mapas, m_final.group(1))
        if torneo:
            c.torneo = torneo
        c.nota(texto)
        return

    m_sufijo = re.search(r"-\s*([A-Za-zÁÉÍÓÚÑáéíóúñ][\wÁÉÍÓÚÑáéíóúñ ]*)\s*$", texto)
    if m_sufijo:
        clave = normalizar(m_sufijo.group(1).strip())
        if clave in mapas.torneos:
            c.torneo = mapas.torneos[clave]
            texto = texto[:m_sufijo.start()].strip()
            normalizado = normalizar(texto)

    if not c.torneo:
        for clave in sorted(mapas.torneos, key=len, reverse=True):
            if clave in normalizado:
                c.torneo = mapas.torneos[clave]
                texto = _quitar_frase(texto, clave).strip()
                normalizado = normalizar(texto)
                break

    for token in TOKENS_AMBIGUOS:
        if normalizar(token) in normalizado:
            c.bloqueado = "token ambiguo en día jugado: %r" % token
            return

    for token in sorted(ESTADO_TOKENS, key=len, reverse=True):
        normalizado = normalizado.replace(normalizar(token), " ")
    restante = _quitar_palabras_sueltas(texto, normalizado)
    restante = re.sub(r"\s+", " ", restante).strip(" -,/")
    if restante:
        c.nota(restante)


def _quitar_frase(texto, clave_normalizada):
    palabras = texto.split()
    salida = []
    i = 0
    while i < len(palabras):
        largo = len(palabras)
        encontrado = False
        for n in range(min(4, largo - i), 0, -1):
            ventana = normalizar(" ".join(palabras[i:i + n]))
            if ventana == clave_normalizada:
                i += n
                encontrado = True
                break
        if not encontrado:
            salida.append(palabras[i])
            i += 1
    return " ".join(salida)


def _quitar_palabras_sueltas(texto, normalizado_restante):
    """Deja en la nota las palabras que no fueron consumidas al quitar tokens."""
    palabras_origen = [p for p in re.split(r"\s+", texto) if p]
    palabras_norm = normalizado_restante.split()
    # Heurística conservadora: si quedó poco texto útil tras quitar estados,
    # se conserva el texto original completo.
    utiles = [p for p in palabras_norm if p.isalnum()]
    if len(utiles) <= 1:
        return ""
    return " ".join(palabras_origen)


def _buscar_torneo_por_frase(mapas, frase):
    palabras = frase.split()
    while palabras:
        clave = normalizar(" ".join(palabras))
        if clave in mapas.torneos:
            return mapas.torneos[clave]
        palabras = palabras[:-1]
    return None


def _detectar_ambiguos(c, contenido, resultado):
    if c.partidos is not None or c.valor_neto is not None:
        return
    normalizado = normalizar(contenido)
    for token, estado in TOKENS_AMBIGUOS.items():
        if normalizar(token) in normalizado:
            c.bloqueado = "token ambiguo: %r" % token
            resultado.issue(c.linea, c.bloqueado,
                            sugerencia="estado sugerido: %s" % estado.value,
                            candidato=c)
            return


def _aplicar_estado(c, contenido):
    normalizado_contenido = normalizar(contenido)
    jugado = c.partidos is not None or c.valor_neto is not None
    tokens = [t for t in sorted(ESTADO_TOKENS, key=len, reverse=True)
              if normalizar(t) in normalizado_contenido]
    if jugado:
        c.estado = Estado.ARBITRADO
        for t in tokens:
            c.nota(t)
        return
    if tokens:
        c.estado = ESTADO_TOKENS[tokens[0]]
        restante = contenido
        for t in tokens:
            restante = re.sub(re.escape(t), " ", restante, flags=re.IGNORECASE)
        restante = re.sub(r"\s+", " ", restante).strip(" -,./()")
        if restante and not restante.isdigit():
            c.nota(restante)
        return
    c.estado = Estado.SIN_DATOS
    c.nota(contenido)


def _calcular_bruto(c):
    if c.valor_neto is None:
        return
    if c.bloqueado:
        return  # bruto indeterminable hasta resolver la cola
    c.bruto = c.valor_neto + sum(d["monto"] for d in c.descuentos.values())


# ---------------------------------------------------------------- aplicación

def aplicar(resultado, conn):
    """Inserta candidatos no bloqueados y vuelca issues. Devuelve contadores."""
    conteo = {"jornadas": 0, "descuentos": 0, "issues": 0}
    for c in resultado.candidatos:
        if c.bloqueado:
            continue
        torneo_id = None
        if c.torneo:
            torneo_id = repo.obtener_o_crear_torneo(conn, c.torneo)
        jid = repo.crear_jornada(
            conn, c.fecha.isoformat(), c.estado,
            partidos_total=c.partidos, roles_detalle=c.roles_detalle,
            bruto=c.bruto, torneo_id=torneo_id, certeza=c.certeza,
            nota="; ".join(c.notas) or None,
        )
        conteo["jornadas"] += 1
        for datos in c.descuentos.values():
            repo.agregar_descuento(
                conn, jid, datos["id"], datos["monto"],
                nota=", ".join(datos["notas"]) or None,
            )
            conteo["descuentos"] += 1
    for issue in resultado.issues:
        repo.crear_issue(conn, issue["linea"], issue["problema"],
                         issue["sugerencia"], issue["payload"])
        conteo["issues"] += 1
    return conteo


# ---------------------------------------------------------------- reporte

def reporte(resultado):
    lineas = []
    estados = {}
    bruto = 0
    validos = [c for c in resultado.candidatos if not c.bloqueado]
    for c in validos:
        estados[c.estado.value] = estados.get(c.estado.value, 0) + 1
        if c.bruto:
            bruto += c.bruto
    lineas.append("jornadas candidatas : %d" % len(validos))
    lineas.append("fechas recalculadas : %d" % resultado.recalculadas)
    lineas.append("bruto reconstruido  : %d Bs" % bruto)
    for estado, cantidad in sorted(estados.items()):
        lineas.append("  %-13s %d" % (estado, cantidad))
    bloqueadas = [c for c in resultado.candidatos if c.bloqueado]
    lineas.append("bloqueadas          : %d" % len(bloqueadas))
    lineas.append("issues a revision   : %d" % len(resultado.issues))
    problemas = {}
    for issue in resultado.issues:
        problemas[issue["problema"]] = problemas.get(issue["problema"], 0) + 1
    for problema, cantidad in sorted(problemas.items()):
        lineas.append("  [%d] %s" % (cantidad, problema))
    return "\n".join(lineas)
