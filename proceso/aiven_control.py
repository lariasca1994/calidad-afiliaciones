"""Enciende el servicio de Aiven si está apagado, antes de conectar.

Los planes gratuitos de Aiven apagan el servicio tras un periodo de
inactividad. Encenderlo de nuevo no es instantaneo: Aiven restaura el
ultimo respaldo, lo que segun su propia documentacion puede tardar desde
unos minutos hasta varias horas segun el tamano de los datos.

Esta funcion es opcional a proposito: solo actua si las tres variables
AIVEN_API_TOKEN, AIVEN_PROJECT_NAME y AIVEN_SERVICE_NAME estan definidas
en el .env. Sin ellas, el proyecto sigue funcionando igual; simplemente
hay que encender el servicio a mano desde el panel cuando este apagado.

Usa la CLI oficial de Aiven (aiven-client) y no la API REST directamente,
porque el formato de los comandos de la CLI esta documentado y
confirmado; el nombre exacto de los campos JSON de la API REST no lo
esta con la misma certeza.

Nota sobre "--project": NO es una opcion global de "avn" (no aparece en
su "usage" de nivel superior). Va despues del subcomando, como opcion de
"service list" / "service update", nunca antes.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parent.parent
load_dotenv(RAIZ / ".env")

TOKEN = os.getenv("AIVEN_API_TOKEN", "").strip()
PROYECTO = os.getenv("AIVEN_PROJECT_NAME", "").strip()
SERVICIO = os.getenv("AIVEN_SERVICE_NAME", "").strip()

ESPERA_MAXIMA_SEGUNDOS = int(os.getenv("AIVEN_ESPERA_MAXIMA_SEG", "480"))
INTERVALO_SEGUNDOS = 15


def configurado() -> bool:
    """Indica si hay suficiente configuración para intentar el encendido."""
    return bool(TOKEN and PROYECTO and SERVICIO)


def _ejecutar(*argumentos_subcomando: str, con_json: bool = True) -> dict | list | None:
    """Corre 'avn <argumentos> --project PROYECTO [--json]'.

    --project va despues del subcomando a proposito: colocado antes,
    entre --auth-token y el subcomando, el analizador de avn lo
    interpreta como si fuera el nombre del subcomando y falla con
    "invalid choice".
    """
    comando = ["avn", "--auth-token", TOKEN, *argumentos_subcomando, "--project", PROYECTO]
    if con_json:
        comando.append("--json")

    resultado = subprocess.run(comando, capture_output=True, text=True, timeout=60)

    if resultado.returncode != 0:
        raise RuntimeError(
            f"Falló 'avn {' '.join(argumentos_subcomando)}':\n{resultado.stderr.strip()}"
        )

    salida = resultado.stdout.strip()
    if not salida:
        return None

    try:
        return json.loads(salida)
    except json.JSONDecodeError:
        return None


def _estado_actual() -> str:
    """Estado del servicio: RUNNING, POWEROFF, REBUILDING, etc.

    Se pide el listado completo de servicios del proyecto y se filtra en
    Python, en lugar de asumir que "service list <nombre>" devuelve un
    solo objeto con una forma determinada: es la parte de la API menos
    documentada con certeza, y equivocarse aqui falla en silencio.
    """
    datos = _ejecutar("service", "list")

    if not datos:
        raise RuntimeError("No se pudo obtener el listado de servicios.")

    lista = datos.get("services") if isinstance(datos, dict) else datos

    if not isinstance(lista, list):
        raise RuntimeError(f"Respuesta inesperada de 'avn service list': {datos!r}")

    for servicio in lista:
        if servicio.get("service_name") == SERVICIO:
            return servicio.get("state", "DESCONOCIDO")

    disponibles = [s.get("service_name") for s in lista]
    raise RuntimeError(
        f"No se encontró el servicio '{SERVICIO}' en el proyecto '{PROYECTO}'.\n"
        f"  Servicios disponibles: {disponibles}"
    )


def asegurar_encendido() -> bool:
    """Enciende el servicio si está apagado y espera a que quede listo.

    Devuelve True si el servicio quedó operativo, False si no se pudo
    verificar. No lanza excepción en ese caso: la conexión a MySQL sigue
    intentándose después, y si de verdad está apagada, el error de
    conexión ya es explicativo por sí solo.
    """
    if not configurado():
        return False

    print("Verificando el estado del servicio en Aiven...")

    try:
        estado = _estado_actual()
    except Exception as error:
        print(f"  No se pudo consultar Aiven: {error}")
        print("  Se continúa e intenta conectar directamente.")
        return False

    if estado == "RUNNING":
        print("  El servicio ya está encendido.")
        return True

    if estado not in ("POWEROFF", "REBUILDING"):
        print(f"  Estado inesperado: {estado}. Se intenta conectar de todas formas.")
        return False

    if estado == "POWEROFF":
        print("  El servicio está apagado. Encendiéndolo...")
        try:
            _ejecutar("service", "update", SERVICIO, "--power-on", con_json=False)
        except Exception as error:
            print(f"  No se pudo encender el servicio: {error}")
            print("  Enciéndelo manualmente desde el panel de Aiven.")
            return False

    print("  Esperando a que quede disponible (puede tardar varios minutos)...")

    transcurrido = 0
    while transcurrido < ESPERA_MAXIMA_SEGUNDOS:
        time.sleep(INTERVALO_SEGUNDOS)
        transcurrido += INTERVALO_SEGUNDOS

        try:
            estado = _estado_actual()
        except Exception:
            continue

        print(f"    {transcurrido}s · estado: {estado}", end="\r")

        if estado == "RUNNING":
            print(f"\n  Servicio disponible tras {transcurrido}s.")
            return True

    print(
        f"\n  Pasaron {ESPERA_MAXIMA_SEGUNDOS}s y el servicio sigue en '{estado}'.\n"
        "  Revisa el panel de Aiven; puede que el respaldo sea grande o haya un problema."
    )
    return False


if __name__ == "__main__":
    if not configurado():
        print(
            "Faltan AIVEN_API_TOKEN, AIVEN_PROJECT_NAME o AIVEN_SERVICE_NAME en el .env.\n"
            "Esta función es opcional; sin ellas hay que encender el servicio a mano."
        )
        sys.exit(1)

    listo = asegurar_encendido()
    sys.exit(0 if listo else 1)