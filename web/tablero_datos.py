"""Datos del tablero web: consultas agregadas por canal y su armado en JSON.

El tablero de consola (proceso/analisis.py) imprime tablas fijas; el
panel web en cambio dibuja gráficos que se filtran por canal en el
navegador. Por eso aquí cada consulta trae el canal como dimensión: el
filtro "Canal" del tablero suma o separa en el cliente, sin volver a
consultar la base.

Igual que en analisis.py, toda consulta lleva usuario_id: las tablas son
compartidas por todas las cuentas del panel.
"""

import json
from pathlib import Path

from proceso import analisis

# Nombre que ve la gente para cada canal técnico.
CANALES = {
    "DIGITAL": "Digital",
    "AFILIACIONES": "Físico",
    "SAT": "SAT",
}

# Departamentos por código DANE: los canales guardan el código, no el nombre.
DEPARTAMENTOS = {
    "05": "Antioquia", "08": "Atlántico", "11": "Bogotá D.C.", "13": "Bolívar",
    "15": "Boyacá", "17": "Caldas", "18": "Caquetá", "19": "Cauca", "20": "Cesar",
    "23": "Córdoba", "25": "Cundinamarca", "27": "Chocó", "41": "Huila",
    "44": "La Guajira", "47": "Magdalena", "50": "Meta", "52": "Nariño",
    "54": "Norte de Santander", "63": "Quindío", "66": "Risaralda", "68": "Santander",
    "70": "Sucre", "73": "Tolima", "76": "Valle del Cauca", "81": "Arauca",
    "85": "Casanare", "86": "Putumayo", "88": "San Andrés", "91": "Amazonas",
    "94": "Guainía", "95": "Guaviare", "97": "Vaupés", "99": "Vichada",
}

CONSULTAS = {
    # Indicadores del resumen, por canal: el navegador los suma para "Todos".
    "kpis": """
        SELECT canal_origen AS canal,
               COUNT(*) AS consolidados,
               SUM(es_produccion_efectiva) AS efectiva,
               SUM(marca_duplicado_multicanal) AS dup_multicanal,
               SUM(marca_duplicado_interno) AS dup_interna,
               SUM(marca_no_homologado) AS no_homologado,
               SUM(marca_territorio_incompleto) AS territorio_incompleto,
               SUM(marca_fecha_invalida) AS fecha_invalida,
               SUM(marca_registro_critico) AS critico
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        GROUP BY canal_origen
    """,
    # Lo que entró por cada archivo de origen, antes de depurar.
    "origen": """
        SELECT 'AFILIACIONES' AS fuente, COUNT(*) AS filas FROM AFILIACIONES WHERE usuario_id = %(usuario_id)s
        UNION ALL SELECT 'DIGITAL', COUNT(*) FROM DIGITAL WHERE usuario_id = %(usuario_id)s
        UNION ALL SELECT 'SAT', COUNT(*) FROM SAT WHERE usuario_id = %(usuario_id)s
        UNION ALL SELECT 'XML_HISTORICO', COUNT(*) FROM XML_HISTORICO WHERE usuario_id = %(usuario_id)s
        UNION ALL SELECT 'PROCESO_IRL', COUNT(*) FROM PROCESO_IRL WHERE usuario_id = %(usuario_id)s
        UNION ALL SELECT 'HOMOLOGACION_DOCUMENTOS', COUNT(*) FROM HOMOLOGACION_DOCUMENTOS
    """,
    "fuentes": analisis.CONSULTAS["fuentes"],
    "calidad": analisis.CONSULTAS["calidad"],
    "sin_homologar": analisis.CONSULTAS["sin_homologar"],
    "tendencia": """
        SELECT periodo, canal_origen AS canal,
               COUNT(*) AS tramites,
               SUM(es_produccion_efectiva) AS efectiva,
               SUM(marca_duplicado_multicanal + marca_duplicado_interno > 0) AS duplicados
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s AND periodo IS NOT NULL
        GROUP BY periodo, canal_origen
        ORDER BY periodo
    """,
    "clasificacion": """
        SELECT canal_origen AS canal, clasificacion_tramite AS clasificacion, COUNT(*) AS tramites
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        GROUP BY canal_origen, clasificacion_tramite
    """,
    "territorio": """
        SELECT canal_origen AS canal, codigo_departamento AS depto, COUNT(*) AS tramites
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        GROUP BY canal_origen, codigo_departamento
    """,
    "estados": """
        SELECT canal_origen AS canal, COALESCE(estado_registro, 'SIN ESTADO') AS estado,
               COUNT(*) AS tramites
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        GROUP BY canal_origen, estado_registro
    """,
    "regimen": """
        SELECT canal_origen AS canal, COALESCE(regimen, 'SIN DATO') AS regimen, COUNT(*) AS tramites
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        GROUP BY canal_origen, regimen
    """,
}


def _filas(cursor, consulta: str, usuario_id: int) -> list[dict]:
    cursor.execute(consulta, {"usuario_id": usuario_id})
    columnas = [d[0] for d in cursor.description]
    return [dict(zip(columnas, fila)) for fila in cursor.fetchall()]


def _plano(valor):
    """Decimal y similares a tipos que JSON entiende."""
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    try:
        return float(valor)
    except (TypeError, ValueError):
        return str(valor)


def consultar(conexion, usuario_id: int) -> dict:
    cursor = conexion.cursor()
    try:
        datos = {
            clave: [{k: _plano(v) for k, v in fila.items()} for fila in _filas(cursor, consulta, usuario_id)]
            for clave, consulta in CONSULTAS.items()
        }
    finally:
        cursor.close()

    for fila in datos["territorio"]:
        codigo = (fila["depto"] or "").strip()
        fila["depto"] = DEPARTAMENTOS.get(codigo[:2], f"Código {codigo}") if codigo else "Sin dato"
    return datos


def hay_datos(datos: dict) -> bool:
    return any(fila["consolidados"] for fila in datos["kpis"])


# ───── Escenario de la última generación de ejemplo ─────
# Se guarda junto a los archivos de la cuenta para que el tablero cuente
# qué tipo de periodo se generó. Si la cuenta subió archivos propios, se
# borra: esos datos no vienen de ningún escenario.

def guardar_escenario(carpeta: Path, resumen: dict) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / "escenario.json").write_text(json.dumps(resumen, ensure_ascii=False), encoding="utf-8")


def leer_escenario(carpeta: Path) -> dict | None:
    try:
        return json.loads((carpeta / "escenario.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def borrar_escenario(carpeta: Path) -> None:
    (carpeta / "escenario.json").unlink(missing_ok=True)
