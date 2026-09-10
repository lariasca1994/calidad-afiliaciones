"""Carga de los archivos de origen a MySQL.

No se usa LOAD DATA LOCAL INFILE: exige que el servidor lo tenga
habilitado, y los servicios gestionados suelen traerlo desactivado. La
inserción por lotes desde Python es algo más lenta pero funciona sin
tocar la configuración del servidor, y permite resolver de paso la
codificación y los separadores distintos de cada fuente.
"""

import csv
import sys
from pathlib import Path

from proceso.conexion import LOTE
from proceso.fuentes import CODIFICACIONES, FUENTES

# Los CSV traen campos largos (POBLACIONESPECIAL supera los 300
# caracteres); sin esto el lector de Python los rechaza.
csv.field_size_limit(min(sys.maxsize, 2**31 - 1))


def _abrir(ruta: Path):
    """Abre el archivo probando las codificaciones habituales."""
    for codificacion in CODIFICACIONES:
        try:
            manejador = open(ruta, encoding=codificacion, newline="")
            manejador.read(8192)
            manejador.seek(0)
            return manejador, codificacion
        except UnicodeDecodeError:
            manejador.close()

    # Último recurso: sustituir lo que no se pueda decodificar. Es
    # preferible perder un acento a perder el archivo entero.
    return open(ruta, encoding="latin-1", errors="replace", newline=""), "latin-1 (con reemplazos)"


def columnas_de_tabla(cursor, tabla: str) -> list[str]:
    cursor.execute(f"SHOW COLUMNS FROM `{tabla}`")
    return [fila[0] for fila in cursor.fetchall()]


def _insertar_lote(conexion, cursor, sentencia, lote, columnas, fuente) -> int:
    """Inserta un lote. Si falla, reintenta fila a fila para señalar
    exactamente cual columna y valor causaron el problema."""
    try:
        cursor.executemany(sentencia, lote)
        conexion.commit()
        return len(lote)
    except Exception as error:
        conexion.rollback()
        for fila_valores in lote:
            try:
                cursor.execute(sentencia, fila_valores)
            except Exception:
                pares = list(zip(columnas, fila_valores))
                culpable = max(pares, key=lambda p: len(str(p[1] or "")))
                raise RuntimeError(
                    f"{fuente['archivo']}: no cabe el valor en la columna "
                    f"'{culpable[0]}' ({len(str(culpable[1]))} caracteres): "
                    f"{str(culpable[1])[:60]!r}\n"
                    f"  Amplía esa columna en sql/01_esquema.sql"
                ) from error
        conexion.commit()
        return len(lote)


def cargar_fuente(conexion, fuente: dict, carpeta: Path) -> dict:
    """Carga un archivo. Devuelve el resumen de lo ocurrido."""
    ruta = carpeta / fuente["archivo"]

    if not ruta.exists():
        return {"archivo": fuente["archivo"], "estado": "ausente", "filas": 0}

    cursor = conexion.cursor()
    destino = columnas_de_tabla(cursor, fuente["tabla"])

    manejador, codificacion = _abrir(ruta)

    with manejador as f:
        lector = csv.reader(f, delimiter=fuente["separador"])

        try:
            encabezado = [c.strip().lstrip("\ufeff") for c in next(lector)]
        except StopIteration:
            cursor.close()
            return {"archivo": fuente["archivo"], "estado": "vacío", "filas": 0}

        # Se cargan solo las columnas que existen en ambos lados. Una
        # columna nueva en el archivo se ignora; una que falte queda nula.
        comunes = [c for c in encabezado if c in destino]
        ignoradas = [c for c in encabezado if c not in destino]
        posiciones = [encabezado.index(c) for c in comunes]

        if not comunes:
            cursor.close()
            raise RuntimeError(
                f"{fuente['archivo']}: ninguna columna del archivo coincide "
                f"con la tabla {fuente['tabla']}.\n"
                f"  Archivo: {', '.join(encabezado[:6])}...\n"
                f"  Tabla:   {', '.join(destino[:6])}..."
            )

        columnas_sql = ", ".join(f"`{c}`" for c in comunes)
        marcadores = ", ".join(["%s"] * len(comunes))
        sentencia = (
            f"INSERT INTO `{fuente['tabla']}` ({columnas_sql}) VALUES ({marcadores})"
        )

        cursor.execute(f"TRUNCATE TABLE `{fuente['tabla']}`")

        lote, total, descartadas = [], 0, 0

        for fila in lector:
            if len(fila) < len(encabezado):
                descartadas += 1
                continue

            lote.append(tuple(
                (fila[p].strip() or None) for p in posiciones
            ))

            if len(lote) >= LOTE:
                total += _insertar_lote(conexion, cursor, sentencia, lote, comunes, fuente)
                lote = []
                print(f"    {total:>7,} filas", end="\r")

        if lote:
            total += _insertar_lote(conexion, cursor, sentencia, lote, comunes, fuente)

    cursor.close()

    return {
        "archivo": fuente["archivo"],
        "tabla": fuente["tabla"],
        "estado": "cargado",
        "filas": total,
        "descartadas": descartadas,
        "ignoradas": ignoradas,
        "codificacion": codificacion,
    }


def cargar_todo(conexion, carpeta: Path) -> list[dict]:
    resultados = []

    for fuente in FUENTES:
        print(f"  {fuente['archivo']:<32} {fuente['descripcion']}")
        resumen = cargar_fuente(conexion, fuente, carpeta)
        resultados.append(resumen)

        if resumen["estado"] == "ausente":
            print(f"    no encontrado en {carpeta}")
        elif resumen["estado"] == "vacío":
            print("    el archivo está vacío")
        else:
            detalle = f"    {resumen['filas']:,} filas"
            if resumen["descartadas"]:
                detalle += f" · {resumen['descartadas']} descartadas por formato"
            if resumen["ignoradas"]:
                detalle += f" · columnas ignoradas: {', '.join(resumen['ignoradas'][:3])}"
            print(detalle)

    return resultados
