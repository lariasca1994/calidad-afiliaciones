"""Migra las tablas creadas ANTES del registro público de cuentas,
agregándoles la columna usuario_id que sql/01_esquema.sql y
sql/03b_materializar.sql ya declaran para instalaciones nuevas.

Por qué hace falta: esos archivos usan CREATE TABLE IF NOT EXISTS (ver su
propio comentario) — no tocan una tabla que ya existe. En una base de
datos que ya tenía estas tablas de antes del registro público (como la
de este proyecto en producción), la columna simplemente nunca se agrega
sola, y cualquier consulta que la use falla con
"Unknown column 'usuario_id'".

Las filas que ya estaban ahí no pertenecen a ninguna cuenta del panel
—existían antes de que existiera el concepto de cuenta—, así que quedan
con el usuario_id reservado (0), el mismo que usa `setup.py` por consola
(ver USUARIO_ID_CLI en setup.py). Ninguna cuenta real del panel web
recibe jamás el id 0 (la tabla `usuarios` empieza su AUTO_INCREMENT en
1), así que esas filas nunca aparecen en el tablero de nadie.

Es seguro correrlo más de una vez: revisa INFORMATION_SCHEMA antes de
cada ALTER en vez de asumir que la columna o el índice no existen
todavía.

Uso (desde la raíz del proyecto, con el venv activado):
    python -m scripts.migrar_usuario_id
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proceso.conexion import conectar

TABLAS = ["AFILIACIONES", "DIGITAL", "SAT", "PROCESO_IRL", "XML_HISTORICO", "consolidado"]


def _columna_existe(cursor, tabla: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = 'usuario_id'
        """,
        (tabla,),
    )
    return cursor.fetchone()[0] > 0


def _indice_existe(cursor, tabla: str, indice: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND INDEX_NAME = %s
        """,
        (tabla, indice),
    )
    return cursor.fetchone()[0] > 0


def main() -> None:
    conexion = conectar()
    try:
        cursor = conexion.cursor()

        for tabla in TABLAS:
            indice = f"idx_{tabla.lower()}_usuario"

            if not _columna_existe(cursor, tabla):
                print(f"  {tabla}: agregando columna usuario_id...")
                cursor.execute(
                    f"ALTER TABLE `{tabla}` ADD COLUMN usuario_id INT NOT NULL DEFAULT 0"
                )
                conexion.commit()
            else:
                print(f"  {tabla}: ya tiene usuario_id")

            if not _indice_existe(cursor, tabla, indice):
                print(f"  {tabla}: agregando índice {indice}...")
                cursor.execute(f"ALTER TABLE `{tabla}` ADD INDEX `{indice}` (usuario_id)")
                conexion.commit()
            else:
                print(f"  {tabla}: ya tiene el índice {indice}")

        cursor.close()
        print("\nMigración completa.")
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
