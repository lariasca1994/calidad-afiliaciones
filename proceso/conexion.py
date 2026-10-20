"""Conexión con MySQL.

Se usa PyMySQL y no mysql-connector-python porque el servicio de Aiven
corre MariaDB, cuyo protocolo el conector oficial de MySQL no admite
(falla con "Protocol mismatch"). PyMySQL habla ambos protocolos.

Toda la configuración viene del .env. No hay valores por defecto para
credenciales: si falta alguno, el script se detiene con un mensaje claro
en lugar de intentar conectarse a un servidor inexistente.
"""

import os
import queue
import sys
import time
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


class BaseNoDisponible(Exception):
    """La base no respondió (apagada, sin red o credenciales inválidas)."""


# Conexiones libres para reutilizar: abrir una conexión TLS hasta la base
# (en otra nube) cuesta varios viajes de ida y vuelta. Ver ConexionPrestada.
POOL_MAX_LIBRES = 4
# Una conexión libre por más de este tiempo se verifica (ping) antes de
# reutilizarla; si se usó hace poco se entrega directo (el ping es otro viaje).
VERIFICAR_TRAS_SEGUNDOS = 30
_libres: "queue.LifoQueue[tuple[pymysql.connections.Connection, float]]" = queue.LifoQueue(
    maxsize=POOL_MAX_LIBRES
)


class ConexionPrestada:
    """Una conexión del pool. Se usa igual que la de PyMySQL; close() no la
    cierra: deshace lo que haya quedado sin confirmar y la devuelve al pool
    para la siguiente petición."""

    def __init__(self, conexion: pymysql.connections.Connection):
        self._conexion = conexion

    def __getattr__(self, nombre):
        return getattr(self._conexion, nombre)

    def close(self) -> None:
        conexion, self._conexion = self._conexion, None
        if conexion is None:
            return
        try:
            conexion.rollback()
            _libres.put_nowait((conexion, time.monotonic()))
        except (pymysql.Error, queue.Full):
            _cerrar(conexion)


def _cerrar(conexion: pymysql.connections.Connection) -> None:
    try:
        conexion.close()
    except pymysql.Error:
        pass


def _libre_sana() -> pymysql.connections.Connection | None:
    """Una conexión libre que siga viva, o None."""
    while True:
        try:
            conexion, devuelta = _libres.get_nowait()
        except queue.Empty:
            return None
        if time.monotonic() - devuelta < VERIFICAR_TRAS_SEGUNDOS:
            return conexion
        try:
            conexion.ping(reconnect=False)
            return conexion
        except pymysql.Error:
            _cerrar(conexion)


def conectar(salir: bool = True):
    """Devuelve una conexión abierta, o termina con un mensaje útil.

    Con salir=False (uso desde la web) no termina el proceso: lanza
    BaseNoDisponible y el panel muestra la página de mantenimiento.

    Primero reutiliza una conexión libre; si no hay, abre una. Solo si la
    base no responde y el .env tiene configurado el encendido automático
    (ver aiven_control.py), consulta a Aiven, enciende el servicio si está
    apagado y reintenta una vez. Antes se consultaba a Aiven en cada
    petición, lo que sumaba segundos a cada página.
    """
    libre = _libre_sana()
    if libre is not None:
        return ConexionPrestada(libre)

    from proceso import aiven_control

    config = _leer_configuracion()

    try:
        try:
            conexion = pymysql.connect(**config)
        except pymysql.Error:
            if not aiven_control.configurado():
                raise
            aiven_control.asegurar_encendido()
            conexion = pymysql.connect(**config)
    except pymysql.Error as error:
        print(f"No se pudo conectar a {config['host']}:{config['port']}")
        print(f"  {error}")
        print("\nRevisa en este orden:")
        print("  1. Que el servicio esté encendido en el panel del proveedor")
        print("  2. Que tu IP esté autorizada en las reglas de red")
        print("  3. Que usuario y contraseña del .env sean correctos")
        if not salir:
            raise BaseNoDisponible(str(error)) from error
        sys.exit(1)

    return ConexionPrestada(conexion)


def describir() -> str:
    """Host y base, sin exponer credenciales. Para los mensajes en pantalla."""
    return f"{os.getenv('DB_HOST')}/{os.getenv('DB_NAME')}"


LOTE = int(os.getenv("LOTE_INSERCION", "5000"))
