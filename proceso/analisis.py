"""Indicadores del tablero y exportación del consolidado.

Toda consulta que toca `consolidado`, `vw_universo_tramites` o
PROCESO_IRL lleva un filtro `usuario_id = %(usuario_id)s`: son tablas
compartidas por todas las cuentas del panel (ver sql/01_esquema.sql), y
sin el filtro el tablero de una persona mostraría —y mezclaría— los
datos de ejemplo de cualquier otra. Se usa el estilo "pyformat" de
PyMySQL (`%(nombre)s` + un dict de parámetros) en vez de `%s` posicional
porque varias de estas consultas repiten el filtro muchas veces dentro
de un UNION ALL: con marcadores posicionales tocaría contar a mano
cuántas veces aparece y pasar una tupla del mismo tamaño, algo frágil y
fácil de desincronizar si la consulta cambia. Con pyformat, el mismo
valor se pasa una sola vez sin importar cuántas veces se use.
"""

from pathlib import Path

CONSULTAS = {
    "tablero": """
        SELECT 'Producción consolidada' AS indicador, COUNT(*) AS valor,
               NULL AS porcentaje
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        UNION ALL
        SELECT 'Registros brutos',
               (SELECT COUNT(*) FROM vw_universo_tramites WHERE usuario_id = %(usuario_id)s),
               NULL
        UNION ALL
        SELECT 'Producción efectiva (radicada)', SUM(es_produccion_efectiva),
               ROUND(SUM(es_produccion_efectiva) / COUNT(*) * 100, 2)
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        UNION ALL
        SELECT 'Duplicidad multicanal', SUM(marca_duplicado_multicanal),
               ROUND(SUM(marca_duplicado_multicanal) / COUNT(*) * 100, 2)
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        UNION ALL
        SELECT 'Duplicidad interna (mismo canal)', SUM(marca_duplicado_interno),
               ROUND(SUM(marca_duplicado_interno) / COUNT(*) * 100, 2)
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        UNION ALL
        SELECT 'Documentos no homologados', SUM(marca_no_homologado),
               ROUND(SUM(marca_no_homologado) / COUNT(*) * 100, 2)
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        UNION ALL
        SELECT 'Territorio incompleto', SUM(marca_territorio_incompleto),
               ROUND(SUM(marca_territorio_incompleto) / COUNT(*) * 100, 2)
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        UNION ALL
        SELECT 'Registros críticos', SUM(marca_registro_critico),
               ROUND(SUM(marca_registro_critico) / COUNT(*) * 100, 2)
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        UNION ALL
        SELECT 'Novedades laborales',
               (SELECT COUNT(*) FROM PROCESO_IRL WHERE usuario_id = %(usuario_id)s),
               NULL
        UNION ALL
        SELECT 'Inconsistencia operativa IRL',
               (SELECT COUNT(*) FROM PROCESO_IRL
                 WHERE usuario_id = %(usuario_id)s AND TRIM(LOG_ERRORES) <> 'CARGUE_EXITOSO'),
               (SELECT ROUND(SUM(TRIM(LOG_ERRORES) <> 'CARGUE_EXITOSO') / COUNT(*) * 100, 2)
                FROM PROCESO_IRL WHERE usuario_id = %(usuario_id)s)
    """,
    "clasificacion": """
        SELECT clasificacion_tramite AS clasificacion, COUNT(*) AS tramites,
               ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2) AS pct
        FROM consolidado
        WHERE usuario_id = %(usuario_id)s
        GROUP BY clasificacion_tramite
        ORDER BY tramites DESC
    """,
    "fuentes": """
        SELECT u.canal AS fuente,
               COUNT(*) AS aportados,
               COALESCE(c.n, 0) AS consolidados,
               COUNT(*) - COALESCE(c.n, 0) AS descartados
        FROM vw_universo_tramites u
        LEFT JOIN (SELECT canal_origen, COUNT(*) AS n
                   FROM consolidado
                   WHERE usuario_id = %(usuario_id)s
                   GROUP BY canal_origen) c
               ON u.canal = c.canal_origen
        WHERE u.usuario_id = %(usuario_id)s
        GROUP BY u.canal, c.n
        ORDER BY consolidados DESC
    """,
    "calidad": """
        SELECT canal AS fuente,
               COUNT(*) AS registros,
               ROUND(SUM(tipo_doc <> 'NO_HOMOLOGADO') / COUNT(*) * 100, 2) AS homologacion,
               ROUND(SUM(depto_id IS NOT NULL AND muni_id IS NOT NULL) / COUNT(*) * 100, 2) AS territorio,
               ROUND(SUM(fecha_radicacion IS NOT NULL) / COUNT(*) * 100, 2) AS fecha_valida
        FROM vw_universo_tramites
        WHERE usuario_id = %(usuario_id)s
        GROUP BY canal
        ORDER BY registros DESC
    """,
    "sin_homologar": """
        SELECT canal AS fuente, tipo_doc_origen AS recibido, COUNT(*) AS registros
        FROM vw_universo_tramites
        WHERE usuario_id = %(usuario_id)s
          AND tipo_doc = 'NO_HOMOLOGADO'
        GROUP BY canal, tipo_doc_origen
        ORDER BY registros DESC
        LIMIT 10
    """,
}


def _tabla(cursor, titulo: str, consulta: str, params: dict) -> None:
    """Imprime el resultado de una consulta en forma de tabla."""
    cursor.execute(consulta, params)
    filas = cursor.fetchall()

    if not filas:
        print(f"\n  {titulo}: sin resultados")
        return

    columnas = [d[0] for d in cursor.description]

    def formatear(valor):
        if valor is None:
            return "—"
        if isinstance(valor, (int,)) and not isinstance(valor, bool):
            return f"{valor:,}"
        return str(valor)

    tabla = [columnas] + [[formatear(v) for v in fila] for fila in filas]
    anchos = [max(len(f[i]) for f in tabla) for i in range(len(columnas))]

    print(f"\n  {titulo}")
    print("  " + "  ".join(c.ljust(anchos[i]) for i, c in enumerate(columnas)))
    print("  " + "  ".join("─" * a for a in anchos))

    for fila in tabla[1:]:
        print("  " + "  ".join(
            v.rjust(anchos[i]) if i > 0 else v.ljust(anchos[i])
            for i, v in enumerate(fila)
        ))


def mostrar_tablero(conexion, usuario_id: int) -> None:
    cursor = conexion.cursor()
    params = {"usuario_id": usuario_id}

    _tabla(cursor, "Cifras principales", CONSULTAS["tablero"], params)
    _tabla(cursor, "Clasificación del trámite", CONSULTAS["clasificacion"], params)
    _tabla(cursor, "Aporte y depuración por fuente", CONSULTAS["fuentes"], params)
    _tabla(cursor, "Calidad por fuente (%)", CONSULTAS["calidad"], params)
    _tabla(cursor, "Tipos de documento fuera de catálogo", CONSULTAS["sin_homologar"], params)

    cursor.close()


def exportar(conexion, carpeta: Path, usuario_id: int) -> None:
    """Exporta el consolidado de UN usuario a CSV, para Power Query o Excel."""
    import csv

    carpeta.mkdir(parents=True, exist_ok=True)
    destino = carpeta / "consolidado.csv"

    cursor = conexion.cursor()
    cursor.execute(
        "SELECT * FROM consolidado WHERE usuario_id = %(usuario_id)s",
        {"usuario_id": usuario_id},
    )
    columnas = [d[0] for d in cursor.description]

    total = 0
    with open(destino, "w", encoding="utf-8-sig", newline="") as f:
        escritor = csv.writer(f, delimiter=";")
        escritor.writerow(columnas)

        while True:
            lote = cursor.fetchmany(5000)
            if not lote:
                break
            escritor.writerows(lote)
            total += len(lote)

    cursor.close()

    # utf-8-sig y punto y coma: es lo que Excel en español abre sin
    # pedir nada al usuario.
    print(f"  {total:,} filas en {destino}")
