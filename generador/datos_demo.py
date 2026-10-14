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
from dataclasses import dataclass, field
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

FUENTES_VOLUMEN = ("afiliaciones", "digital", "sat", "irl", "xml")


def _sumar_meses(inicio: date, meses: int) -> date:
    anio, mes = divmod(inicio.month - 1 + meses, 12)
    return date(inicio.year + anio, mes + 1, 1)


@dataclass
class Escenario:
    """Perfil de una generación: cuánto aporta cada canal, en qué periodo
    y qué tan sucios llegan los datos.

    Con la semilla sola, cada generación cambiaba los documentos pero no
    el panorama: mismos volúmenes por canal, misma duplicidad y misma
    calidad, así que el tablero salía prácticamente igual en cada clic.
    El panel web sortea un escenario por generación (escenario_aleatorio)
    para que se note la diferencia; la consola usa el escenario base y
    sigue siendo reproducible con --semilla.
    """

    nombre: str = "Operación base"
    descripcion: str = "Volúmenes y tasas de referencia, calibrados con los datos reales."
    volumen: dict = field(default_factory=lambda: {f: 1.0 for f in FUENTES_VOLUMEN})
    tasa_multicanal: float = 0.012
    tasa_interna: float = 0.06
    factor_rechazos: float = 1.0
    tasa_fuera_catalogo: float = 0.0008
    tasa_territorio_vacio: float = 0.0
    peso_contributivo: float = 65.0
    pesos_territorio: list | None = None
    desde: date = date(2025, 1, 1)
    meses: int = 19
    pesos_mes: list | None = None

    def fecha(self, rng: random.Random) -> date:
        """Fecha dentro del periodo, más probable en los meses de mayor peso."""
        mes = (rng.choices(range(self.meses), weights=self.pesos_mes, k=1)[0]
               if self.pesos_mes else rng.randrange(self.meses))
        inicio = _sumar_meses(self.desde, mes)
        fin = _sumar_meses(self.desde, mes + 1) - timedelta(days=1)
        return inicio + timedelta(days=rng.randint(0, (fin - inicio).days))

    def estados_digital(self) -> list[tuple]:
        return [(e, p if e == "RADICADO" else p * self.factor_rechazos) for e, p in ESTADOS_DIGITAL]

    def regimen(self, rng: random.Random) -> str:
        return rng.choices(["CONTRIBUTIVO", "SUBSIDIADO"],
                           weights=[self.peso_contributivo, 100 - self.peso_contributivo])[0]

    def territorio_vacio(self, rng: random.Random) -> bool:
        return rng.random() < self.tasa_territorio_vacio

    def resumen(self) -> dict:
        """Lo que el tablero muestra del escenario, en palabras sencillas."""
        hasta = _sumar_meses(self.desde, self.meses) - timedelta(days=1)
        return {
            "nombre": self.nombre,
            "descripcion": self.descripcion,
            "periodo": f"{self.desde:%m/%Y} a {hasta:%m/%Y} ({self.meses} meses)",
            "volumen": {f: round(v, 2) for f, v in self.volumen.items()},
            "duplicidad_multicanal_pct": round(self.tasa_multicanal * 100, 1),
            "duplicidad_interna_pct": round(self.tasa_interna * 100, 1),
            "factor_rechazos": round(self.factor_rechazos, 1),
            "fuera_catalogo_pct": round(self.tasa_fuera_catalogo * 100, 2),
            "territorio_vacio_pct": round(self.tasa_territorio_vacio * 100, 1),
        }


# Perfiles de operación: le dan una historia reconocible a cada
# generación (no solo números al azar) y el tablero la cuenta.
# Cada valor es el centro; escenario_aleatorio() le agrega variación.
PERFILES = [
    {"nombre": "Operación estable",
     "descripcion": "Un periodo sin sobresaltos: los tres canales en su proporción habitual.",
     "volumen": {"afiliaciones": 1.0, "digital": 1.0, "sat": 1.0},
     "multicanal": 0.010, "interna": 0.05, "rechazos": 1.0, "fuera": 0.001, "territorio": 0.01},
    {"nombre": "Campaña de afiliación",
     "descripcion": "Un mes de campaña dispara el canal digital y, con él, las radicaciones repetidas.",
     "volumen": {"afiliaciones": 1.1, "digital": 1.9, "sat": 0.9},
     "multicanal": 0.025, "interna": 0.10, "rechazos": 1.6, "fuera": 0.002, "territorio": 0.02,
     "pico": True},
    {"nombre": "Canal presencial fuerte",
     "descripcion": "Los puntos de atención presencial pesan más que el portal; SAT crece con ellos.",
     "volumen": {"afiliaciones": 2.2, "digital": 0.6, "sat": 1.5},
     "multicanal": 0.015, "interna": 0.04, "rechazos": 0.8, "fuera": 0.001, "territorio": 0.04},
    {"nombre": "Cierre con rechazos",
     "descripcion": "Un cierre de periodo con muchos trámites anulados, rechazados o sin prerradicar.",
     "volumen": {"afiliaciones": 0.9, "digital": 1.2, "sat": 1.0},
     "multicanal": 0.012, "interna": 0.06, "rechazos": 4.5, "fuera": 0.002, "territorio": 0.02},
    {"nombre": "Migración de sistema",
     "descripcion": "Tras un cambio de sistema llegan documentos fuera de catálogo y territorios sin dato.",
     "volumen": {"afiliaciones": 0.8, "digital": 1.0, "sat": 1.3},
     "multicanal": 0.008, "interna": 0.08, "rechazos": 1.3, "fuera": 0.03, "territorio": 0.12},
]


def escenario_aleatorio(rng: random.Random) -> Escenario:
    """Sortea un perfil y lo varía: volumen, tasas, periodo y territorio."""
    perfil = rng.choice(PERFILES)

    def variar(valor: float, amplitud: float = 0.3) -> float:
        return valor * rng.uniform(1 - amplitud, 1 + amplitud)

    volumen = {f: variar(perfil["volumen"].get(f, 1.0)) for f in FUENTES_VOLUMEN}
    # El tamaño general también cambia: un periodo puede ser el doble de otro.
    tamano = rng.choice([0.6, 0.85, 1.0, 1.3, 1.7])
    volumen = {f: v * tamano for f, v in volumen.items()}

    meses = rng.randint(8, 18)
    desde = _sumar_meses(date(2026, 8, 1), -meses)

    # Estacionalidad: un recorrido aleatorio mes a mes, y en campaña un pico.
    pesos_mes, peso = [], 1.0
    for _ in range(meses):
        peso *= rng.uniform(0.8, 1.25)
        pesos_mes.append(peso)
    if perfil.get("pico"):
        pico = rng.randrange(meses)
        pesos_mes[pico] *= rng.uniform(2.5, 4.0)

    return Escenario(
        nombre=perfil["nombre"],
        descripcion=perfil["descripcion"],
        volumen=volumen,
        tasa_multicanal=variar(perfil["multicanal"]),
        tasa_interna=variar(perfil["interna"]),
        factor_rechazos=variar(perfil["rechazos"]),
        tasa_fuera_catalogo=variar(perfil["fuera"]),
        tasa_territorio_vacio=variar(perfil["territorio"]),
        peso_contributivo=rng.uniform(50, 80),
        pesos_territorio=[rng.uniform(0.3, 3.0) for _ in TERRITORIOS],
        desde=desde,
        meses=meses,
        pesos_mes=pesos_mes,
    )


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

    def __init__(self, rng: random.Random, cantidad_pool: int, pesos_territorio: list | None = None):
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
                "territorio": rng.choices(TERRITORIOS, weights=pesos_territorio, k=1)[0],
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


def generar_afiliaciones(rng: random.Random, asignados: list[dict], carpeta: Path,
                         esc: Escenario) -> None:
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
        fecha = esc.fecha(rng)
        sin_territorio = esc.territorio_vacio(rng)

        filas.append({
            "ID": i + 1,
            "CODIGOASESOR": f"A{rng.randint(100, 199)}",
            "SOLICITUD": f"SOL-{rng.randint(100000, 999999)}",
            "TIPODOCUMENTO": p["tipo_doc"],
            "NUMERODOCUMENTO": p["num_doc"],
            "DEPARTAMENTOID": "" if sin_territorio else depto,
            "MUNICIPIOID": "" if sin_territorio else muni[0],
            "CODIGOAFILIACION": f"AF{rng.randint(10000, 99999)}",
            "NOMBREIPS": f"IPS {rng.choice(['Central', 'Norte', 'Sur', 'del Barrio'])}",
            "CANTBENEFICIARIO": rng.randint(0, 4),
            "TIPODOCUMENTOEMPLEADOR": "NI",
            "NUMERODOCUMENTOEMPLEADOR": _doc(rng),
            "FECHARADICACION": fecha.strftime("%d/%m/%y"),
            "REGIMEN": esc.regimen(rng),
            "TIPOAFILIACION": "Afiliación",
            "SISBEN": "",
            "POBLACIONESPECIAL": "",
            "EXCEPCIONTRASLADO": "N",
            "CAUSALEXCEPCION": "",
        })
    escribir_csv(carpeta / "AFILIACIONES.csv", columnas, filas, "|")


def generar_digital(rng: random.Random, asignados: list[dict], carpeta: Path,
                    esc: Escenario) -> None:
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
        dane = "" if esc.territorio_vacio(rng) else depto + muni[0]

        estado = _elegir_ponderado(rng, esc.estados_digital())
        dia = esc.fecha(rng)
        solicitud = datetime(dia.year, dia.month, dia.day) + timedelta(minutes=rng.randint(0, 1439))

        # Solo lo radicado tiene fecha de radicacion; el resto solo
        # solicitud, reproduciendo lo encontrado en los datos reales.
        radicacion = solicitud + timedelta(hours=rng.randint(1, 72)) if estado == "RADICADO" else None

        # Tipo de documento fuera de catalogo, en proporcion baja: es el
        # hallazgo de calidad que el proyecto debe poder mostrar.
        tipo_doc = "PS" if rng.random() < esc.tasa_fuera_catalogo else p["tipo_doc"]

        filas.append({
            "IDPRODUCCION": i + 1,
            "ESTADOAFILIACION": estado,
            "DESCRIPCIONESTADO": estado.title(),
            "FECHASOLICITUD": solicitud.strftime("%Y-%m-%d %H:%M:%S"),
            "FECHARADICACION": radicacion.strftime("%Y-%m-%d %H:%M:%S") if radicacion else "",
            "TIPOREGIMEN": esc.regimen(rng),
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


def generar_sat(rng: random.Random, asignados: list[dict], carpeta: Path,
                esc: Escenario) -> None:
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
        fecha = esc.fecha(rng)
        sin_territorio = esc.territorio_vacio(rng)

        filas.append({
            "ID": i + 1,
            "NORADICADOSAT": f"SAT{rng.randint(1000000, 9999999)}",
            "CODIGOASESOR": f"A{rng.randint(100, 199)}",
            "TIPODOCUMENTO": str(codigo_por_abrev.get(p["tipo_doc"], 3)),
            "NUMERODOCUMENTOAFILIADO": p["num_doc"],
            "SOLICITUD": f"SOL-{rng.randint(100000, 999999)}",
            "FECHARADICACION": fecha.strftime("%d/%m/%y"),
            "REGIMEN": esc.regimen(rng),
            "TIPODOCUMENTOEMPLEADOR": "4",
            "NUMERODOCUMENTOEMPLEADOR": _doc(rng),
            "TIPOCOTIZANTE": rng.choice(["DEPENDIENTE", "INDEPENDIENTE"]),
            "CANTBENEFICIARIO": rng.randint(0, 4),
            "DEPARTAMENTOID": "" if sin_territorio else depto,
            "MUNICIPIOID": "" if sin_territorio else muni[0],
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


def generar(escala: float, semilla: int, carpeta: Path | None = None,
            escenario: Escenario | None = None) -> Escenario:
    """Escribe las seis fuentes y devuelve el escenario usado. Sin
    escenario se usa el base: mismos volúmenes y tasas de siempre."""
    destino = carpeta if carpeta is not None else ENTRADA
    rng = random.Random(semilla)
    esc = escenario or Escenario()

    # Volumen base a escala 1.0 (subido un poco desde 900/3200/900/5000/9000):
    # sigue corriendo en segundos y muy por debajo del tope de carga
    # (TAMANO_MAXIMO_ARCHIVO_BYTES en web/main.py), pero deja un dataset de
    # ejemplo algo más parecido en volumen al real sin tener que pasar
    # --escala a mano.
    base = {"afiliaciones": 1200, "digital": 4200, "sat": 1200,
            "irl": 6500, "xml": 12000}
    n = {k: max(1, int(v * escala * esc.volumen.get(k, 1.0))) for k, v in base.items()}

    # El pool operativo cubre exactamente los tres canales que participan
    # en la deduplicacion, sin excedente: asi el reparto sin reemplazo no
    # deja personas sueltas. El pool para IRL/XML es aparte y mas grande,
    # con reemplazo, porque esas fuentes no entran en el calculo de
    # duplicidad y conviene que cubran un universo de personas más amplio.
    total_operativo = n["afiliaciones"] + n["digital"] + n["sat"]

    destino.mkdir(parents=True, exist_ok=True)

    print("Generando datos sintéticos")
    print(f"  Escala: {escala}x · Semilla: {semilla} · Escenario: {esc.nombre}\n")

    generar_homologacion(destino)
    print(f"  HOMOLOGACION_DOCUMENTOS.csv   {len(CATALOGO_DOCUMENTOS)} filas")

    operativo = GeneradorAfiliados(rng, total_operativo, esc.pesos_territorio)
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
    }, tasa_multicanal=esc.tasa_multicanal, tasa_interna=esc.tasa_interna)

    generar_afiliaciones(rng, asig_afiliaciones, destino, esc)
    print(f"  AFILIACIONES.csv              {n['afiliaciones']} filas")

    generar_digital(rng, asig_digital, destino, esc)
    print(f"  DIGITAL.csv                   {n['digital']} filas")

    generar_sat(rng, asig_sat, destino, esc)
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
    return esc


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
