"""Carga de los archivos de origen a MySQL.

No se usa LOAD DATA LOCAL INFILE: exige que el servidor lo tenga
habilitado, y los servicios gestionados suelen traerlo desactivado. La
inserción por lotes desde Python es algo más lenta pero funciona sin
tocar la configuración del servidor, y permite resolver de paso la
codificación y los separadores distintos de cada fuente.

usuario_id y el aislamiento entre cuentas
---------------------------------------------------------------------
Antes de que el panel web permitiera varias cuentas, cada carga hacía
TRUNCATE TABLE sobre la tabla completa: había un solo dueño de los datos,
así que borrar todo antes de insertar era correcto. Con registro
público, cada tabla (salvo el catálogo de documentos, ver fuentes.py)
tiene filas de muchas cuentas a la vez. Truncar la tabla completa
borraría los datos de ejemplo de todo el mundo cada vez que UNA persona
genera los suyos — por eso ahora se borra solo lo de ESE usuario
(DELETE ... WHERE usuario_id = %s) antes de insertar sus filas nuevas,
y cada fila insertada lleva su usuario_id.
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


def cargar_fuente(conexion, fuente: dict, carpeta: Path, usuario_id: int) -> dict:
    """Carga un archivo. Devuelve el resumen de lo ocurrido.

    Para una fuente "usuario_scoped" (todas salvo el catálogo), primero
    borra únicamente las filas de `usuario_id` en esa tabla, y cada fila
    insertada lleva ese mismo usuario_id en su propia columna. Para el
    catálogo compartido, se comporta igual que antes: TRUNCATE completo.
    """
    ruta = carpeta / fuente["archivo"]

    if not ruta.exists():
        return {"archivo": fuente["archivo"], "estado": "ausente", "filas": 0}

    cursor = conexion.cursor()
    destino = columnas_de_tabla(cursor, fuente["tabla"])
    if fuente["usuario_scoped"]:
        # usuario_id es una columna técnica, no un campo del archivo de
        # origen: se excluye de las columnas "de negocio" contra las que
        # se valida el encabezado del CSV.
        destino = [c for c in destino if c != "usuario_id"]

    manejador, codificacion = _abrir(ruta)

    with manejador as f:
        lector = csv.reader(f, delimiter=fuente["separador"])

        try:
            encabezado = [c.strip().lstrip("﻿") for c in next(lector)]
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

        if fuente["usuario_scoped"]:
            columnas_sql = ", ".join(f"`{c}`" for c in ["usuario_id", *comunes])
            marcadores = ", ".join(["%s"] * (len(comunes) + 1))
            cursor.execute(
                f"DELETE FROM `{fuente['tabla']}` WHERE usuario_id = %s", (usuario_id,)
            )
        else:
            columnas_sql = ", ".join(f"`{c}`" for c in comunes)
            marcadores = ", ".join(["%s"] * len(comunes))
            cursor.execute(f"TRUNCATE TABLE `{fuente['tabla']}`")

        sentencia = (
            f"INSERT INTO `{fuente['tabla']}` ({columnas_sql}) VALUES ({marcadores})"
        )

        lote, total, descartadas = [], 0, 0

        for fila in lector:
            if len(fila) < len(encabezado):
                descartadas += 1
                continue

            valores = tuple((fila[p].strip() or None) for p in posiciones)
            if fuente["usuario_scoped"]:
                valores = (usuario_id, *valores)
            lote.append(valores)

            if len(lote) >= LOTE:
                columnas_error = ["usuario_id", *comunes] if fuente["usuario_scoped"] else comunes
                total += _insertar_lote(conexion, cursor, sentencia, lote, columnas_error, fuente)
                lote = []
                print(f"    {total:>7,} filas", end="\r")

        if lote:
            columnas_error = ["usuario_id", *comunes] if fuente["usuario_scoped"] else comunes
            total += _insertar_lote(conexion, cursor, sentencia, lote, columnas_error, fuente)

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


def cargar_todo(conexion, carpeta: Path, usuario_id: int) -> list[dict]:
    resultados = []

    for fuente in FUENTES:
        print(f"  {fuente['archivo']:<32} {fuente['descripcion']}")
        resumen = cargar_fuente(conexion, fuente, carpeta, usuario_id)
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
