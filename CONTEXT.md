# Arbitraje

CLI local para registrar jornadas de arbitraje y analizar ingresos. Unidad mínima: la jornada de un día.

## Language

**Jornada**:
Día registrado con un estado; unidad mínima del sistema. Puede haber más de una por fecha (dos torneos el mismo día).
_Avoid_: registro, entrada, día

**Estado**:
Clasificación estructurada de lo que ocurrió en la jornada: ARBITRADO, NO_DESIGNADO, NO_HUBO, LLUVIA, ELECCIONES, VIAJE, DESCANSO, RECHAZADO, SIN_DATOS, OTRO, FERIADO. Solo ARBITRADO genera dinero.
_Avoid_: motivo, tipo

**Partidos**:
Cantidad física arbitrada en la jornada; admite decimales solo como anotación de pago (el conteo es físico). NULL = desconocido, 0 = cero conocido.
_Avoid_: encuentros, juegos

**Roles detalle**:
Notación original histórica de partidos y roles (`3c+2a`, `1 f, 2.5 m`), preservada verbatim. Abreviaturas: c=central, a=asistente, l=línea, res=residentes, f/fej=FEJUVE, ame=Amerints, m=sin resolver.
_Avoid_: desglose

**Bruto**:
Ingreso pactado antes de descuentos, en Bs enteros. En registros nuevos lo ingresa el usuario; en el histórico se reconstruye sumando descuentos al valor neto anotado.
_Avoid_: total, ingreso

**Neto**:
Lo que queda después de descuentos: `bruto - suma(descuentos)`. Siempre derivado, jamás almacenado ni pedido al usuario.
_Avoid_: líquido, pago

**Descuento**:
Monto restado en la jornada, asociado a un concepto, con nota opcional. Monto siempre conocido (NOT NULL); sin monto no hay descuento.
_Avoid_: deducción, gasto

**Concepto**:
Categoría reutilizable de descuento con default configurable y aliases históricos (`a`→Asesoría, `f`→Fondo). `Otros` recibe lo no clasificado; `Deuda` registra el marcador `*-50*` del histórico.
_Avoid_: categoría, tipo

**Torneo**:
Competición reutilizable, entidad propia. Asignación por jerarquía de marcadores del histórico; los marcadores de final también dejan nota.
_Avoid_: liga, campeonato (como campo)

**Certeza**:
Confianza en un registro importado: CONFIRMADO, PROBABLE (fecha recalculada por rótulo de día), DUDOSO (dato ambiguo). No se pregunta en registros nuevos.
_Avoid_: confianza, validez

**Cola de revisión**:
Registro de líneas del histórico que el importador no resolvió (`import_issues`). Nada entra a la base inventado ni subestimado en silencio.
_Avoid_: errores, log
