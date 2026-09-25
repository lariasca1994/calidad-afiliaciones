#!/usr/bin/env python3
"""Genera datos sintéticos para probar el proyecto sin información real.

    python generador/datos_demo.py
    python generador/datos_demo.py --escala 3
    python generador/datos_demo.py --semilla 99

Escribe las seis fuentes en datos/entrada/, con la misma estructura,
separadores y codificación que los archivos reales: cinco con barra
vertical y codificación latin-1, y XML con punto y coma.

No usa ninguna identidad real. Los nombres se arman combinando listas de
nombres y apellidos comunes en español, y los documentos son números
aleatorios dentro de rangos plausibles.

Reproduce a propósito los mismos problemas que aparecieron al analizar
los datos reales, porque son justamente lo que da sentido al proyecto:

  - un tipo de documento fuera de catálogo (PS)
  - duplicidad del mismo afiliado entre canales
  - duplicidad dentro del mismo canal
  - registros DIGITAL sin fecha de radicación por estar anulados,
    rechazados o sin prerradicar
  - el tipo NIT repetido en el catálogo con dos abreviaturas
  - departamentos y municipios en el histórico escritos como texto,
    no como código, a diferencia de los canales operativos

Por qué `carpeta` es un parámetro y no solo una constante global
---------------------------------------------------------------------
El botón "Generar datos de ejemplo" del panel web llama a `generar()`
directamente (sin pasar por esta terminal), y con registro público de
cuentas puede haber varias personas generando datos AL MISMO TIEMPO. Si
todas escribieran siempre en la misma carpeta fija, dos generaciones
simultáneas correrían el riesgo de mezclar o pisar los archivos de la
otra a mitad de escritura. Por eso cada función de generación recibe la
carpeta de destino como argumento — el panel web le pasa una carpeta
propia por cuenta (datos/entrada_usuarios/<id>/); esta terminal, cuando
se usa sin argumentos, sigue escribiendo en la carpeta compartida de
siempre (datos/entrada/), porque ahí no hay concurrencia que resolver.
"""

import argparse
import csv
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
ENTRADA = RAIZ / "datos" / "entrada"

NOMBRES = [
    "Carlos", "María", "José", "Ana", "Luis", "Laura", "Andrés", "Diana",
    "Camilo", "Paula", "Jorge", "Sandra", "Felipe", "Carolina", "Julián",
    "Natalia", "Sergio", "Valentina", "Óscar", "Daniela", "Ricardo", "Lina",
]
APELLIDOS = [
    "Gómez", "Rodríguez", "Martínez", "López", "García", "Pérez", "Sánchez",
    "Ramírez", "Torres", "Díaz", "Vargas", "Castro", "Rojas", "Moreno",
    "Muñoz", "Ortiz", "Herrera", "Jiménez", "Ruiz", "Álvarez",
]

# (código depto, nombre depto, [(código municipio, nombre municipio)])
TERRITORIOS = [
    ("11", "BOGOTA D.C.", [("001", "BOGOTA D.C.")]),
    ("05", "ANTIOQUIA", [("001", "MEDELLIN"), ("088", "BELLO"), ("360", "ITAGUI")]),
    ("76", "VALLE DEL CAUCA", [("001", "CALI"), ("520", "PALMIRA")]),
    ("08", "ATLANTICO", [("001", "BARRANQUILLA"), ("758", "SOLEDAD")]),
    ("54", "NORTE DE SANTANDER", [("001", "CUCUTA")]),
    ("20", "CESAR", [("045", "AGUACHICA"), ("400", "MANAURE BALCON DEL CESAR")]),
    ("13", "BOLIVAR", [("001", "CARTAGENA")]),
    ("68", "SANTANDER", [("001", "BUCARAMANGA"), ("276", "GIRON")]),
]

# Catalogo con la misma irregularidad que el real: NIT figura dos veces.
CATALOGO_DOCUMENTOS = [
    ("Cédula de Ciudadanía", 3, "CC"),
    ("Cédula de Extranjería", 2, "CE"),
    ("Tarjeta de Identidad", 15, "TI"),
    ("Registro Civil", 1, "RC"),
    ("Pasaporte", 5, "PA"),
    ("Permiso Especial de Permanencia", 12, "PE"),
    ("NIT", 4, "NI"),
    ("NIT", 4, "NT"),  # duplicado intencional: mismo codigo, otra abreviatura
    ("Carné Diplomático", 6, "CD"),
    ("Adulto sin Identificación", 9, "AS"),
    ("Menor sin Identificación", 10, "MS"),
]

ENTIDADES_XML = [
    "NUEVA EPS S.A.", "NUEVA EPS S.A. -CM", "COOSALUD EPS S.A.",
    "PROTEGER EPS S.A.S.", "SALUD TOTAL EPS S.A.", "SANITAS EPS S.A.S.",
    "COMPENSAR EPS",
]

LOG_ERRORES_IRL = [
    ("CARGUE_EXITOSO", 92),
    ("BENEFICIARIO", 5),
    ("RELACION LABORAL CREADA CON ANTERIORIDAD", 1.3),
    ("IRL-DUPLICADO", 0.7),
    ("NO EXISTE EMPLEADOR", 0.2),
    ("ARCHIVO CON ERRORES DE FORMATO", 0.8),
]

ESTADOS_DIGITAL = [
    ("RADICADO", 93.5), ("ANULADO", 2.4), ("SIN-PRERADICAR", 2.1),
    ("RECHAZADO", 1.9), ("DEVOLUCIÓN", 0.1),
]


def _doc(rng: random.Random) -> str:
    return str(rng.randint(10_000_000, 1_299_999_999))


def _nombre(rng: random.Random) -> tuple[str, str]:
    return rng.choice(NOMBRES), rng.choice(APELLIDOS)


def _fecha_en_rango(rng: random.Random, desde: date, hasta: date) -> date:
    dias = (hasta - desde).days
    return desde + timedelta(days=rng.randint(0, max(dias, 1)))


def _elegir_ponderado(rng: random.Random, opciones: list[tuple]) -> str:
    valores = [o[0] for o in opciones]
    pesos = [o[1] for o in opciones]
    return rng.choices(valores, weights=pesos, k=1)[0]


class GeneradorAfiliados:
    """Genera un conjunto de personas y las reparte SIN colisiones
    accidentales entre los tres canales operativos.

    La version anterior elegia cada persona con random.choice() sobre un
    pool compartido, lo que produce el problema del cumpleanos: con 5.000
    sorteos sobre un pool de 4.000, las colisiones por puro azar superan
    el 30%, muy por encima del 0.56% observado en los datos reales. Un
    pool chico con reemplazo no modela duplicidad real, modela una
    lotizacion mal dimensionada.

    Aqui se reparte el pool sin reemplazo —cada persona cae en un solo
    canal— y la duplicidad se inyecta despues, de forma explicita y en
    la proporcion que se quiere representar. Ver inyectar_duplicados().
    """

    def __init__(self, rng: random.Random, cantidad_pool: int):
        self.rng = rng
        self.pool = []
        catalogo_valido = [c for c in CATALOGO_DOCUMENTOS if c[2] not in ("NI", "NT")]

        for _ in range(cantidad_pool):
            nombre1, apellido1 = _nombre(rng)
            tipo = rng.choices(catalogo_valido, weights=[70, 5, 15, 3, 2, 2, 1, 1, 1], k=1)[0]
            self.pool.append({
                "tipo_doc": tipo[2],
                "num_doc": _doc(rng),
                "nombre1": nombre1,
                "apellido1": apellido1,
                "territorio": rng.choice(TERRITORIOS),
            })

    def repartir(self, *cantidades: int) -> list[list[dict]]:
        """Divide el pool en tantos grupos como cantidades se pidan, sin
        que ninguna persona caiga en dos grupos a la vez."""
        necesarias = sum(cantidades)
        if necesarias > len(self.pool):
            raise ValueError(
                f"El pool tiene {len(self.pool)} personas y se piden {necesarias}."
            )

        barajado = self.rng.sample(self.pool, len(self.pool))
        grupos, inicio = [], 0
        for cantidad in cantidades:
            grupos.append(barajado[inicio:inicio + cantidad])
            inicio += cantidad
        return grupos

    def elegir_del_pool(self) -> dict:
        """Para fuentes que no participan en el calculo de duplicidad
        (novedades laborales, radicacion historica): un sorteo simple
        con reemplazo sobre el pool completo."""
        return self.rng.choice(self.pool)


def escribir_csv(ruta: Path, columnas: list[str], filas: list[dict], separador: str) -> None:
    with open(ruta, "w", encoding="latin-1", errors="replace", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=columnas, delimiter=separador)
        escritor.writeheader()
        escritor.writerows(filas)


def generar_homologacion(carpeta: Path) -> None:
    filas = [
        {"Tipo_Documento_Afiliado": nombre, "CODIGO": codigo, "Abreviatura": abrev}
        for nombre, codigo, abrev in CATALOGO_DOCUMENTOS
    ]
    escribir_csv(
        carpeta / "HOMOLOGACION_DOCUMENTOS.csv",
        ["Tipo_Documento_Afiliado", "CODIGO", "Abreviatura"],
        filas,
        "|",
    )


def inyectar_duplicados(
    rng: random.Random,
    listas: dict[str, list[dict]],
    tasa_multicanal: float = 0.012,
    tasa_interna: float = 0.06,
) -> None:
    """Reemplaza una fraccion de las asignaciones por duplicados, en dos
    tipos que se generan por separado porque tienen causas distintas
    (ver docs/decisiones.md):

      - Multicanal: se sustituye la persona de una fila por una que ya
        esta asignada en OTRO canal. Modela al mismo afiliado radicando
        por dos vias.
      - Interna: se sustituye por una persona ya asignada en el MISMO
        canal. Modela una radicacion repetida por la misma via.

    Las tasas por defecto se calibraron para acercarse a lo observado en
    los datos reales analizados (multicanal ~0.6%, interna ~3-8% segun
    el canal), sin pretender igualarlas de forma exacta: son datos
    sinteticos para practicar el pipeline, no una replica estadistica.

    Modifica las listas en el sitio.
    """
    nombres = list(listas.keys())

    for nombre in nombres:
        lista = listas[nombre]
        n = len(lista)
        if n == 0:
            continue

        otros_canales = [p for k in nombres if k != nombre for p in listas[k]]

        n_multi = int(n * tasa_multicanal)
        if otros_canales and n_multi:
            for i in rng.sample(range(n), min(n_multi, n)):
                lista[i] = rng.choice(otros_canales)

        n_interna = int(n * tasa_interna)
        if n_interna:
            for i in rng.sample(range(n), min(n_interna, n)):
                # Se toma de una copia congelada antes del reemplazo, para
                # que la fuente de la duplicacion sea una persona real de
                # la lista y no una ya sustituida en esta misma pasada.
                origen = lista[:n]
                lista[i] = rng.choice(origen)


def generar_afiliaciones(rng: random.Random, asignados: list[dict], carpeta: Path) -> None:
    columnas = [
        "ID", "CODIGOASESOR", "SOLICITUD", "TIPODOCUMENTO", "NUMERODOCUMENTO",
        "DEPARTAMENTOID", "MUNICIPIOID", "CODIGOAFILIACION", "NOMBREIPS",
        "CANTBENEFICIARIO", "TIPODOCUMENTOEMPLEADOR", "NUMERODOCUMENTOEMPLEADOR",
        "FECHARADICACION", "REGIMEN", "TIPOAFILIACION", "SISBEN",
        "POBLACIONESPECIAL", "EXCEPCIONTRASLADO", "CAUSALEXCEPCION",
    ]
    filas = []
    for i, p in enumerate(asignados):
        depto, _, municipios = p["territorio"]
        muni = rng.choice(municipios)
        fecha = _fecha_en_rango(rng, date(2025, 1, 1), date(2026, 8, 1))

        filas.append({
            "ID": i + 1,
            "CODIGOASESOR": f"A{rng.randint(100, 199)}",
            "SOLICITUD": f"SOL-{rng.randint(100000, 999999)}",
            "TIPODOCUMENTO": p["tipo_doc"],
            "NUMERODOCUMENTO": p["num_doc"],
            "DEPARTAMENTOID": depto,
            "MUNICIPIOID": muni[0],
            "CODIGOAFILIACION": f"AF{rng.randint(10000, 99999)}",
            "NOMBREIPS": f"IPS {rng.choice(['Central', 'Norte', 'Sur', 'del Barrio'])}",
            "CANTBENEFICIARIO": rng.randint(0, 4),
            "TIPODOCUMENTOEMPLEADOR": "NI",
            "NUMERODOCUMENTOEMPLEADOR": _doc(rng),
            "FECHARADICACION": fecha.strftime("%d/%m/%y"),
            "REGIMEN": rng.choices(["CONTRIBUTIVO", "SUBSIDIADO"], weights=[65, 35])[0],
            "TIPOAFILIACION": "Afiliación",
            "SISBEN": "",
            "POBLACIONESPECIAL": "",
            "EXCEPCIONTRASLADO": "N",
            "CAUSALEXCEPCION": "",
        })
    escribir_csv(carpeta / "AFILIACIONES.csv", columnas, filas, "|")


def generar_digital(rng: random.Random, asignados: list[dict], carpeta: Path) -> None:
    columnas = [
        "IDPRODUCCION", "ESTADOAFILIACION", "DESCRIPCIONESTADO", "FECHASOLICITUD",
        "FECHARADICACION", "TIPOREGIMEN", "CODIGOASESOR", "TIPOAFILIACION",
        "CONTRIBUSOLIDARIA", "TIPOCOTIZANTE", "INTERNOMEDICINA", "CARGO",
        "TIPOAFILIADO", "PARENTESCO", "TIPODOCUMENTOAFILIADO", "NUM_AFILIADO",
        "NOMBRE1", "NOMBRE2", "APELLIDO1", "APELLIDO2", "FECHANACIMIENTO",
        "SEXO_IDENTIFICACION", "NACIONALIDAD", "PAISNACIMIENTO", "DANE_NACIMIENTO",
        "DEPARTAMENTONACIMIENTO", "MUNICIPIONACIMIENTO", "ZONA", "DANE_RESIDENCIA",
        "CODIGOIPS", "COMUNIDADINDIGENA", "ENCUESTASISBEN", "NIVELSISBEN",
        "SUBGRUPOSISBEN", "TIPODOCUMENTOEMPLEADOR", "NUMERODOCUMENTOEMPLEADOR",
        "TARIFACONTRIBUCIONSOLIDARIA", "METODOLOGIAGRUPOPOBLACIONAL",
        "TIPOPOBLACIONESPECIAL", "DISCAPACIDAD", "TIPODECONDICION", "FECHANOVEDAD",
        "NOFORMULARIOVIRTUAL", "RUTAARCHIVOS", "CAUSALEXCEPCION",
        "DESCRIPCIONCAUSALEXCEPCION", "CERTIFICACION_GRUPO_FAMILIAR",
        "SOPORTE_QUEJA_SUPER_SALUD", "TRASLADO", "VALOREPSANTERIOR",
    ]
    filas = []
    for i, p in enumerate(asignados):
        depto, _, municipios = p["territorio"]
        muni = rng.choice(municipios)
        dane = depto + muni[0]

        estado = _elegir_ponderado(rng, ESTADOS_DIGITAL)
        solicitud = _fecha_en_rango(rng, datetime(2025, 1, 1), datetime(2026, 8, 1))

        # Solo lo radicado tiene fecha de radicacion; el resto solo
        # solicitud, reproduciendo lo encontrado en los datos reales.
        radicacion = solicitud + timedelta(hours=rng.randint(1, 72)) if estado == "RADICADO" else None

        # Tipo de documento fuera de catalogo, en proporcion baja: es el
        # hallazgo de calidad que el proyecto debe poder mostrar.
        tipo_doc = "PS" if rng.random() < 0.0008 else p["tipo_doc"]

        filas.append({
            "IDPRODUCCION": i + 1,
            "ESTADOAFILIACION": estado,
            "DESCRIPCIONESTADO": estado.title(),
            "FECHASOLICITUD": solicitud.strftime("%Y-%m-%d %H:%M:%S"),
            "FECHARADICACION": radicacion.strftime("%Y-%m-%d %H:%M:%S") if radicacion else "",
            "TIPOREGIMEN": rng.choices(["CONTRIBUTIVO", "SUBSIDIADO"], weights=[65, 35])[0],
            "CODIGOASESOR": f"A{rng.randint(100, 199)}",
            "TIPOAFILIACION": "Afiliación",
            "CONTRIBUSOLIDARIA": "N",
            "TIPOCOTIZANTE": rng.choice(["DEPENDIENTE", "INDEPENDIENTE"]),
            "INTERNOMEDICINA": "",
            "CARGO": "",
            "TIPOAFILIADO": rng.choices(["COTIZANTE", "BENEFICIARIO"], weights=[85, 15])[0],
            "PARENTESCO": "",
            "TIPODOCUMENTOAFILIADO": tipo_doc,
            "NUM_AFILIADO": p["num_doc"],
            "NOMBRE1": p["nombre1"],
            "NOMBRE2": "",
            "APELLIDO1": p["apellido1"],
            "APELLIDO2": "",
            "FECHANACIMIENTO": _fecha_en_rango(rng, date(1950, 1, 1), date(2008, 1, 1)).strftime("%Y-%m-%d %H:%M:%S"),
            "SEXO_IDENTIFICACION": rng.choice(["M", "F"]),
            "NACIONALIDAD": "COLOMBIANA",
            "PAISNACIMIENTO": "COLOMBIA",
            "DANE_NACIMIENTO": dane,
            "DEPARTAMENTONACIMIENTO": "",
            "MUNICIPIONACIMIENTO": "",
            "ZONA": rng.choice(["URBANA", "RURAL"]),
            "DANE_RESIDENCIA": dane,
            "CODIGOIPS": f"IPS{rng.randint(1000, 9999)}",
            "COMUNIDADINDIGENA": "",
            "ENCUESTASISBEN": "",
            "NIVELSISBEN": "",
            "SUBGRUPOSISBEN": "",
            "TIPODOCUMENTOEMPLEADOR": "NI",
            "NUMERODOCUMENTOEMPLEADOR": _doc(rng),
            "TARIFACONTRIBUCIONSOLIDARIA": "",
            "METODOLOGIAGRUPOPOBLACIONAL": "",
            "TIPOPOBLACIONESPECIAL": "",
            "DISCAPACIDAD": "N",
            "TIPODECONDICION": "",
            "FECHANOVEDAD": "",
            "NOFORMULARIOVIRTUAL": f"F{rng.randint(100000, 999999)}",
            "RUTAARCHIVOS": "",
            "CAUSALEXCEPCION": "",
            "DESCRIPCIONCAUSALEXCEPCION": "",
            "CERTIFICACION_GRUPO_FAMILIAR": "N",
            "SOPORTE_QUEJA_SUPER_SALUD": "N",
            "TRASLADO": rng.choices(["S", "N"], weights=[20, 80])[0],
            "VALOREPSANTERIOR": "",
        })
    escribir_csv(carpeta / "DIGITAL.csv", columnas, filas, "|")


def generar_sat(rng: random.Random, asignados: list[dict], carpeta: Path) -> None:
    columnas = [
        "ID", "NORADICADOSAT", "CODIGOASESOR", "TIPODOCUMENTO",
        "NUMERODOCUMENTOAFILIADO", "SOLICITUD", "FECHARADICACION", "REGIMEN",
        "TIPODOCUMENTOEMPLEADOR", "NUMERODOCUMENTOEMPLEADOR", "TIPOCOTIZANTE",
        "CANTBENEFICIARIO", "DEPARTAMENTOID", "MUNICIPIOID", "CODIGOAFILIACION",
        "NOMBREIPS", "CODIGOOCUPACION", "NOMBREOCUPACION",
    ]
    codigo_por_abrev = {abrev: codigo for _, codigo, abrev in CATALOGO_DOCUMENTOS}

    filas = []
    for i, p in enumerate(asignados):
        depto, _, municipios = p["territorio"]
        muni = rng.choice(municipios)
        fecha = _fecha_en_rango(rng, date(2025, 1, 1), date(2026, 8, 1))

        filas.append({
            "ID": i + 1,
            "NORADICADOSAT": f"SAT{rng.randint(1000000, 9999999)}",
            "CODIGOASESOR": f"A{rng.randint(100, 199)}",
            "TIPODOCUMENTO": str(codigo_por_abrev.get(p["tipo_doc"], 3)),
            "NUMERODOCUMENTOAFILIADO": p["num_doc"],
            "SOLICITUD": f"SOL-{rng.randint(100000, 999999)}",
            "FECHARADICACION": fecha.strftime("%d/%m/%y"),
            "REGIMEN": rng.choices(["CONTRIBUTIVO", "SUBSIDIADO"], weights=[65, 35])[0],
            "TIPODOCUMENTOEMPLEADOR": "4",
            "NUMERODOCUMENTOEMPLEADOR": _doc(rng),
            "TIPOCOTIZANTE": rng.choice(["DEPENDIENTE", "INDEPENDIENTE"]),
            "CANTBENEFICIARIO": rng.randint(0, 4),
            "DEPARTAMENTOID": depto,
            "MUNICIPIOID": muni[0],
            "CODIGOAFILIACION": f"AF{rng.randint(10000, 99999)}",
            "NOMBREIPS": f"IPS {rng.choice(['Central', 'Norte', 'Sur'])}",
            "CODIGOOCUPACION": str(rng.randint(1000, 9999)),
            "NOMBREOCUPACION": rng.choice(["INDEPENDIENTE", "EMPLEADO", "PENSIONADO"]),
        })
    escribir_csv(carpeta / "SAT.csv", columnas, filas, "|")


def _persona_externa(rng: random.Random) -> dict:
    """Persona sin relacion con el universo de produccion actual.

    Se usa para una fraccion del historico XML: gente cuyo antecedente
    existe en el sistema pero que no tiene ningun tramite en el periodo
    analizado. No debe compartir documento con nadie del pool operativo;
    con el rango de _doc() la probabilidad de colision es despreciable.
    """
    nombre1, apellido1 = _nombre(rng)
    catalogo_valido = [c for c in CATALOGO_DOCUMENTOS if c[2] not in ("NI", "NT")]
    tipo = rng.choice(catalogo_valido)
    return {
        "tipo_doc": tipo[2],
        "num_doc": _doc(rng),
        "nombre1": nombre1,
        "apellido1": apellido1,
        "territorio": rng.choice(TERRITORIOS),
    }


def preparar_antecedentes(
    rng: random.Random,
    pool_operativo: list[dict],
    tasa_sin_antecedente: float = 0.065,
    tasa_reinscripcion_del_resto: float = 0.73,
) -> dict:
    """Divide el pool operativo en tres grupos, para que el histórico XML
    pueda referenciar a las MISMAS personas que aparecen en producción.

    Es la pieza que hace que la clasificación del trámite tenga sentido:
    sin esto, el XML generaría antecedentes de personas que no existen en
    ningún otro archivo, y todo caería por defecto en "Afiliación Nueva".

    - sin_antecedente: nunca aparecen en el XML. Producen Afiliación Nueva.
    - con_nueva_eps: su antecedente en el XML es Nueva EPS. Reinscripción.
    - con_otra_eps: su antecedente es otra entidad. Traslado.

    Las proporciones por defecto se calibraron sobre la distribución
    observada en los datos reales analizados (68% / 25% / 6%
    aproximadamente).
    """
    barajado = rng.sample(pool_operativo, len(pool_operativo))

    corte_sin = int(len(barajado) * tasa_sin_antecedente)
    resto = barajado[corte_sin:]
    corte_nueva = int(len(resto) * tasa_reinscripcion_del_resto)

    return {
        "sin_antecedente": barajado[:corte_sin],
        "con_nueva_eps": resto[:corte_nueva],
        "con_otra_eps": resto[corte_nueva:],
    }


def generar_irl(rng: random.Random, pool_operativo: list[dict], cantidad: int, carpeta: Path) -> None:
    columnas = [
        "TIPO_DOC", "NUMDOC", "CARGO", "TIPO_DOC_EMP", "NUMEMP", "FECHADEINGRESO",
        "ASESOR", "TIPO_DE_EMPLEADOR", "TIPO_DE_RESPUESTA", "N_ARCHIVO",
        "F_RECIBIDO", "F_PROCESO", "ORIGEN", "LOG_ERRORES", "ID_TRAMITE",
    ]
    filas = []
    for i in range(cantidad):
        # Se toma del pool operativo: representa novedades laborales de
        # gente que SI esta afiliada, que es el caso real.
        p = rng.choice(pool_operativo)
        recibido = _fecha_en_rango(rng, date(2025, 1, 1), date(2026, 8, 1))

        filas.append({
            "TIPO_DOC": p["tipo_doc"],
            "NUMDOC": p["num_doc"],
            "CARGO": rng.choice(["OPERARIO", "ADMINISTRATIVO", "INDEPENDIENTE"]),
            "TIPO_DOC_EMP": "NI",
            "NUMEMP": _doc(rng),
            "FECHADEINGRESO": recibido.strftime("%d/%m/%Y"),
            "ASESOR": f"A{rng.randint(100, 199)}",
            "TIPO_DE_EMPLEADOR": rng.choice(["PERSONA JURIDICA", "PERSONA NATURAL"]),
            "TIPO_DE_RESPUESTA": "AUTOMATICA",
            "N_ARCHIVO": f"IRL_{recibido.strftime('%Y%m%d')}.txt",
            "F_RECIBIDO": recibido.strftime("%d/%m/%Y"),
            "F_PROCESO": (recibido + timedelta(days=1)).strftime("%d/%m/%Y"),
            "ORIGEN": "PILA",
            "LOG_ERRORES": _elegir_ponderado(rng, LOG_ERRORES_IRL),
            "ID_TRAMITE": f"IRL{i + 1:08d}",
        })
    escribir_csv(carpeta / "PROCESO_IRL.csv", columnas, filas, "|")


def generar_xml(
    rng: random.Random,
    antecedentes: dict,
    cantidad: int,
    carpeta: Path,
    proporcion_externa: float = 0.10,
) -> None:
    """Genera el histórico. antecedentes trae los tres grupos que deciden
    qué clasificación tendrá cada persona del universo de producción:
    con antecedente en Nueva EPS, en otra entidad, o sin ninguno.

    La cobertura de con_nueva_eps y con_otra_eps se GARANTIZA, no se deja
    al azar: cada persona de esos dos grupos recibe primero una fila
    obligatoria con la entidad que le corresponde, y solo despues se
    reparte el resto del volumen para variedad.

    Confiar en el sobremuestreo aleatorio no alcanza: con un promedio de
    ~1.7 filas por persona, la probabilidad de que alguien quede en cero
    por pura mala suerte ronda el 18% (ley de Poisson), lo que dejaba mal
    clasificada a una fraccion grande del grupo. Garantizar la primera
    fila elimina ese azar; el resto del volumen sí puede repartirse
    libremente porque ya no compromete la clasificacion.

    sin_antecedente nunca se toca: por eso su clasificacion queda en
    Afiliacion Nueva de forma garantizada, no probable.
    """
    columnas = [
        "IDENTIFICADOR", "SERIAL", "TIPO_IDENTIFICACION", "NUMERO_IDENTIFICACION",
        "PRIMER_NOMBRE", "SEGUNDO_NOMBRE", "PRIMER_APELLIDO", "SEGUNDO_APELLIDO",
        "NACIMIENTO_FECHA", "DEPTO", "MUNI", "ESTADO", "ENT_ID", "ENTIDAD",
        "REGIMEN", "FECHA_CONTRATO", "FECHA_FIN_CONTRATO",
        "AFILIACION_ENTIDAD_FECHA", "ESTADO_FECHA", "TIPO_AFILIADO",
        "FECHA_AFILIACION_EFECTIVA", "cantidad_grp_fml", "cruce_bdex_rnec",
        "fecha_novedad", "CANAL", "ID_TRAMITE_RADICADO", "FECHA_CONSULTA",
    ]

    entidades_nueva_eps = ["NUEVA EPS S.A.", "NUEVA EPS S.A. -CM"]
    entidades_otras = [e for e in ENTIDADES_XML if not e.startswith("NUEVA EPS")]

    con_nueva = antecedentes["con_nueva_eps"]
    con_otra = antecedentes["con_otra_eps"]

    # (persona, entidad) de cada fila a generar. Primero las obligatorias.
    pendientes: list[tuple[dict, str]] = []
    pendientes += [(p, rng.choice(entidades_nueva_eps)) for p in con_nueva]
    pendientes += [(p, rng.choice(entidades_otras)) for p in con_otra]

    obligatorias = len(pendientes)
    if cantidad < obligatorias:
        # No hay volumen suficiente para cubrir a todos una sola vez:
        # se amplia para no dejar a nadie sin su fila garantizada, y se
        # avisa, porque significa que --escala quedo demasiado bajo.
        print(
            f"    (ajustando XML.csv de {cantidad} a {obligatorias} filas: "
            "es el mínimo para que cada persona con antecedente tenga su fila)"
        )
        cantidad = obligatorias

    libres = cantidad - obligatorias
    n_externas = int(libres * proporcion_externa)
    n_extra_cubiertos = libres - n_externas

    for _ in range(n_extra_cubiertos):
        if rng.random() < len(con_nueva) / max(len(con_nueva) + len(con_otra), 1):
            p = rng.choice(con_nueva) if con_nueva else rng.choice(con_otra)
            entidad = rng.choice(entidades_nueva_eps)
        else:
            p = rng.choice(con_otra) if con_otra else rng.choice(con_nueva)
            entidad = rng.choice(entidades_otras)
        pendientes.append((p, entidad))

    for _ in range(n_externas):
        pendientes.append((_persona_externa(rng), rng.choice(ENTIDADES_XML)))

    rng.shuffle(pendientes)

    filas = []
    for i, (p, entidad) in enumerate(pendientes):
        depto, nombre_depto, municipios = p["territorio"]
        muni = rng.choice(municipios)
        fecha = _fecha_en_rango(rng, date(2018, 1, 1), date(2025, 12, 1))

        filas.append({
            "IDENTIFICADOR": str(i + 1),
            "SERIAL": f"S{rng.randint(100000, 999999)}",
            "TIPO_IDENTIFICACION": p["tipo_doc"],
            "NUMERO_IDENTIFICACION": p["num_doc"],
            "PRIMER_NOMBRE": p["nombre1"],
            "SEGUNDO_NOMBRE": "",
            "PRIMER_APELLIDO": p["apellido1"],
            "SEGUNDO_APELLIDO": "",
            "NACIMIENTO_FECHA": _fecha_en_rango(rng, date(1950, 1, 1), date(2008, 1, 1)).strftime("%d/%m/%Y"),
            # Nombres, no codigos: asi vienen en el archivo real.
            "DEPTO": nombre_depto,
            "MUNI": muni[1],
            "ESTADO": rng.choice(["ACTIVO", "RETIRADO"]),
            "ENT_ID": str(rng.randint(1000, 9999)),
            "ENTIDAD": entidad,
            "REGIMEN": rng.choices(["CONTRIBUTIVO", "SUBSIDIADO"], weights=[65, 35])[0],
            "FECHA_CONTRATO": fecha.strftime("%d/%m/%Y"),
            "FECHA_FIN_CONTRATO": "",
            "AFILIACION_ENTIDAD_FECHA": fecha.strftime("%d/%m/%Y"),
            "ESTADO_FECHA": fecha.strftime("%d/%m/%Y"),
            "TIPO_AFILIADO": rng.choices(["COTIZANTE", "BENEFICIARIO"], weights=[85, 15])[0],
            "FECHA_AFILIACION_EFECTIVA": fecha.strftime("%d/%m/%Y"),
            "cantidad_grp_fml": rng.randint(0, 4),
            "cruce_bdex_rnec": "SI",
            "fecha_novedad": "",
            "CANAL": rng.choice(["WEB", "PRESENCIAL"]),
            "ID_TRAMITE_RADICADO": f"XML{i + 1:08d}",
            "FECHA_CONSULTA": date(2026, 8, 1).strftime("%d/%m/%Y"),
        })
    escribir_csv(carpeta / "XML.csv", columnas, filas, ";")


def generar(escala: float, semilla: int, carpeta: Path | None = None) -> None:
    destino = carpeta if carpeta is not None else ENTRADA
    rng = random.Random(semilla)

    # Volumen base a escala 1.0 (subido un poco desde 900/3200/900/5000/9000):
    # sigue corriendo en segundos y muy por debajo del tope de carga
    # (TAMANO_MAXIMO_ARCHIVO_BYTES en web/main.py), pero deja un dataset de
    # ejemplo algo más parecido en volumen al real sin tener que pasar
    # --escala a mano.
    base = {"afiliaciones": 1200, "digital": 4200, "sat": 1200,
            "irl": 6500, "xml": 12000}
    n = {k: max(1, int(v * escala)) for k, v in base.items()}

    # El pool operativo cubre exactamente los tres canales que participan
    # en la deduplicacion, sin excedente: asi el reparto sin reemplazo no
    # deja personas sueltas. El pool para IRL/XML es aparte y mas grande,
    # con reemplazo, porque esas fuentes no entran en el calculo de
    # duplicidad y conviene que cubran un universo de personas más amplio.
    total_operativo = n["afiliaciones"] + n["digital"] + n["sat"]

    destino.mkdir(parents=True, exist_ok=True)

    print("Generando datos sintéticos")
    print(f"  Escala: {escala}x · Semilla: {semilla}\n")

    generar_homologacion(destino)
    print(f"  HOMOLOGACION_DOCUMENTOS.csv   {len(CATALOGO_DOCUMENTOS)} filas")

    operativo = GeneradorAfiliados(rng, total_operativo)
    asig_afiliaciones, asig_digital, asig_sat = operativo.repartir(
        n["afiliaciones"], n["digital"], n["sat"]
    )

    # La duplicidad se agrega aqui, de forma explicita y medible, en vez
    # de dejar que surja como efecto secundario de un sorteo con
    # reemplazo sobre un pool chico (lo que produce el problema del
    # cumpleanos: colisiones muy por encima de lo que se querria modelar).
    inyectar_duplicados(rng, {
        "AFILIACIONES": asig_afiliaciones,
        "DIGITAL": asig_digital,
        "SAT": asig_sat,
    })

    generar_afiliaciones(rng, asig_afiliaciones, destino)
    print(f"  AFILIACIONES.csv              {n['afiliaciones']} filas")

    generar_digital(rng, asig_digital, destino)
    print(f"  DIGITAL.csv                   {n['digital']} filas")

    generar_sat(rng, asig_sat, destino)
    print(f"  SAT.csv                       {n['sat']} filas")

    generar_irl(rng, operativo.pool, n["irl"], destino)
    print(f"  PROCESO_IRL.csv               {n['irl']} filas")

    # El XML debe referenciar a las MISMAS personas del pool operativo:
    # es lo que permite que la clasificacion del tramite (Reinscripcion,
    # Traslado, Afiliacion Nueva) tenga sentido en lugar de caer siempre
    # en un solo valor por defecto.
    antecedentes = preparar_antecedentes(rng, operativo.pool)
    generar_xml(rng, antecedentes, n["xml"], destino)
    print(f"  XML.csv                       {n['xml']} filas")

    print(f"\nArchivos escritos en {destino}")
    print("Ejecuta 'python setup.py' para cargarlos.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Genera datos sintéticos de afiliaciones para probar el proyecto"
    )
    parser.add_argument("--escala", type=float, default=1.0,
                        help="multiplica la cantidad base de filas (por defecto 1.0)")
    parser.add_argument("--semilla", type=int, default=42,
                        help="semilla aleatoria, para resultados reproducibles")
    parser.add_argument("--forzar", action="store_true",
                        help="sobrescribe sin preguntar si ya hay archivos en datos/entrada")

    args = parser.parse_args()

    existentes = list(ENTRADA.glob("*.csv")) if ENTRADA.exists() else []

    if existentes and not args.forzar:
        print(f"Ya hay {len(existentes)} archivo(s) CSV en {ENTRADA}:")
        for archivo in existentes:
            print(f"  - {archivo.name}")
        print(
            "\nSi son datos reales, no los sobrescribas por accidente.\n"
            "Para generar datos sintéticos de todas formas, ejecuta con --forzar."
        )
        return 1

    generar(args.escala, args.semilla)
    return 0


if __name__ == "__main__":
    sys.exit(main())
