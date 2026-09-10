"""Ejecución de los archivos .sql del proyecto.

MySQL no acepta varias sentencias en una sola llamada cuando hay
resultados de por medio, así que el archivo se divide. La división es
por punto y coma, ignorando los que aparecen dentro de comentarios o de
cadenas de t    to: partir a ciegas rompería cualquier consulta que
contenga un punto y coma como dato.
"""

import re
from pathlib import Path


def separar_sentencias(sql: str) -> list[str]:
    """Divide un script en sentencias individuales."""
    # Fuera los comentarios de línea, que pueden contener punto y coma.
    sin_comentarios = re.sub(r"--[^\n]*", "", sql)
    sin_comentarios = re.sub(r"/\*.*?\*/", "", sin_comentarios, flags=re.S)

    sentencias, actual, comilla = [], [], None

    for caracter in sin_comentarios:
        if comilla:
            if caracter == comilla:
                comilla = None
        elif caracter in ("'", '"', "`"):
            comilla = caracter
        elif caracter == ";":
            texto = "".join(actual).strip()
            if texto:
                sentencias.append(texto)
            actual = []
            continue

        actual.append(caracter)

    ultima = "".join(actual).strip()
    if ultima:
        sentencias.append(ultima)

    return sentencias


def crear(conexion, ruta: Path) -> int:
    """Ejecuta un archivo .sql. Devuelve cuántas sentencias corrieron."""
    if not ruta.exists():
        raise FileNotFoundError(f"No existe {ruta}")

    sentencias = separar_sentencias(ruta.read_text(encoding="utf-8"))
    cursor = conexion.cursor()
    ejecutadas = 0

    for sentencia in sentencias:
        try:
            cursor.execute(sentencia)
            # Algunas sentencias devuelven resultados que hay que agotar
            # antes de lanzar la siguiente.
            while cursor.nextset():
                pass
            ejecutadas += 1
        except Exception as error:
            resumen = " ".join(sentencia.split())[:90]
            print(f"\n  Falló: {resumen}...")
            print(f"  {error}")
            raise

    conexion.commit()
    cursor.close()

    return ejecutadas
