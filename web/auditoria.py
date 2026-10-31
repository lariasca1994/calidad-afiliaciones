"""Registro de eventos de seguridad de las cuentas.

Guarda qué pasó, a qué cuenta y cuándo; nunca contraseñas, códigos ni datos
del equipo. Cada registro borra los eventos de más de 15 días.
Si la base no responde, el evento se pierde pero el ingreso sigue: la
auditoría nunca bloquea al usuario.
"""

import logging

from proceso.conexion import conectar

INGRESO = "ingreso"
CLAVE_ERRADA = "clave_errada"
CODIGO_ERRADO = "codigo_errado"
CUENTA_BLOQUEADA = "cuenta_bloqueada"
CLAVE_CAMBIADA = "clave_cambiada"
RECUPERACION = "recuperacion_solicitada"
METODO_ACTIVADO = "metodo_activado"

RETENCION_DIAS = 15

_CREAR_TABLA = """
CREATE TABLE IF NOT EXISTS eventos_seguridad (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    tipo VARCHAR(40) NOT NULL,
    usuario_id INT NOT NULL,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX ix_eventos_fecha (fecha),
    INDEX ix_eventos_usuario (usuario_id)
)
"""

_log = logging.getLogger(__name__)
_tabla_lista = False


def registrar(tipo: str, usuario) -> None:
    global _tabla_lista
    try:
        conexion = conectar(salir=False)
    except Exception:  # noqa: BLE001 - la auditoría no debe tumbar el ingreso
        _log.warning("No se pudo registrar el evento de seguridad %s", tipo)
        return
    try:
        cursor = conexion.cursor()
        if not _tabla_lista:
            cursor.execute(_CREAR_TABLA)
            _tabla_lista = True
        cursor.execute(
            "DELETE FROM eventos_seguridad WHERE fecha < NOW() - INTERVAL %s DAY",
            (RETENCION_DIAS,),
        )
        cursor.execute(
            "INSERT INTO eventos_seguridad (tipo, usuario_id) VALUES (%s, %s)",
            (tipo, usuario["id"]),
        )
        conexion.commit()
    except Exception:  # noqa: BLE001
        _log.warning("No se pudo registrar el evento de seguridad %s", tipo)
    finally:
        conexion.close()
