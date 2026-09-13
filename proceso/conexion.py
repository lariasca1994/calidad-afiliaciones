"""Conexión con MySQL.

Se usa PyMySQL y no mysql-connector-python porque el servicio de Aiven
corre MariaDB, cuyo protocolo el conector oficial de MySQL no admite
(falla con "Protocol mismatch"). PyMySQL habla ambos protocolos.

Toda la configuración viene del .env. No hay valores por defecto para
credenciales: si falta alguno, el script se detiene con un mensaje claro
en lugar de intentar conectarse a un servidor inexistente.
"""

import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

OBLIGATORIAS = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]


def _leer_configuracion() -> dict:
    faltantes = [v for v in OBLIGATORIAS if not os.getenv(v)]

    if faltantes:
        print("Falta configuración en el archivo .env:")
        for v in faltantes:
            print(f"  - {v}")
        print("\nCopia .env.example como .env y complétalo.")
        sys.exit(1)

    config = {
        "host": os.getenv("DB_HOST"),
        "port": int(os.getenv("DB_PORT")),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "database": os.getenv("DB_NAME"),
        "charset": "utf8mb4",
        "connect_timeout": 30,
        # Sin esto, una consulta que se queda a medias por un corte de
        # red (frecuente cuando el servidor de la app y el de la base
        # están en nubes/regiones distintas, como Azure y Aiven aquí) se
        # queda esperando una respuesta que nunca llega — sin error, sin
        # log, indefinidamente. connect_timeout solo cubre el saludo
        # inicial de la conexión; read/write_timeout cubren cada
        # operación posterior, para que un corte a medio camino termine
        # en una excepción clara en vez de una solicitud colgada para
        # siempre.
        "read_timeout": 60,
        "write_timeout": 60,
        "autocommit": False,
    }

    if os.getenv("DB_SSL", "true").lower() == "true":
        certificado = os.getenv("DB_SSL_CA", "").strip()

        if certificado and Path(certificado).exists():
            config["ssl"] = {"ca": certificado}
        else:
            # Cifrado sin verificar la identidad del servidor: suficiente
            # para desarrollo. Con el certificado del proveedor se
            # verifica tambien la identidad.
            config["ssl"] = {"ssl": {}}

    return config


def conectar():
    """Devuelve una conexión abierta, o termina con un mensaje útil.

    Si el .env tiene configurado el encendido automático (ver
    aiven_control.py), primero verifica que el servicio esté activo. Es
    opcional: sin esa configuración se salta el paso y se intenta
    conectar directamente.
    """
    from proceso import aiven_control

    if aiven_control.configurado():
        aiven_control.asegurar_encendido()

    config = _leer_configuracion()

    try:
        conexion = pymysql.connect(**config)
    except pymysql.Error as error:
        print(f"No se pudo conectar a {config['host']}:{config['port']}")
        print(f"  {error}")
        print("\nRevisa en este orden:")
        print("  1. Que el servicio esté encendido en el panel del proveedor")
        print("  2. Que tu IP esté autorizada en las reglas de red")
        print("  3. Que usuario y contraseña del .env sean correctos")
        sys.exit(1)

    return conexion


def describir() -> str:
    """Host y base, sin exponer credenciales. Para los mensajes en pantalla."""
    return f"{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"


LOTE = int(os.getenv("LOTE_INSERCION", "5000"))
