"""Crea (o resetea la contraseña de) la cuenta que inicia sesión en el
panel web de este proyecto.

A diferencia de los demás proyectos del portafolio, aquí no hay un
modelo de "dueño de los datos" — el tablero de indicadores es el mismo
para cualquiera que entre. Por eso no existe un rol admin aparte: esta
es simplemente LA cuenta con la que se inicia sesión para ver el panel.

El correo no se escribe en este archivo ni en ningún otro que se suba al
repositorio: se recibe como argumento en la línea de comandos, igual que
la contraseña.

Uso (desde la raíz del proyecto, con el venv activado):
    python -m scripts.crear_admin <email> <password>
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from proceso import esquema
from proceso.conexion import conectar
from web.seguridad import hashear_password

RAIZ = Path(__file__).resolve().parent.parent


def main() -> None:
    if len(sys.argv) != 3:
        print("Uso: python -m scripts.crear_admin <email> <password>")
        sys.exit(1)

    email = sys.argv[1].strip().lower()
    password = sys.argv[2]

    try:
        password_hash = hashear_password(password)
    except ValueError as error:
        print(f"Contraseña rechazada: {error}")
        sys.exit(1)

    conexion = conectar()
    try:
        # CREATE TABLE IF NOT EXISTS — no toca nada si ya existe.
        esquema.crear(conexion, RAIZ / "sql" / "05_usuarios.sql")

        cursor = conexion.cursor()
        cursor.execute(
            """
            INSERT INTO usuarios (email, password_hash)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash)
            """,
            (email, password_hash),
        )
        conexion.commit()
        cursor.close()
        print("Cuenta lista (creada o con la contraseña actualizada).")
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
