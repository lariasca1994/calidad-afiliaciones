"""Pipeline completo de esquema + carga + homologación + consolidado.

Extrae en una sola función lo que hace `setup.py` sin argumentos desde la
línea de comandos (crear esquema, cargar los CSV de datos/entrada, y
recalcular homologación/consolidado/materializado), para poder invocarlo
también desde el panel web —el botón "Generar datos de ejemplo" en el
tablero— sin duplicar la lógica ni depender de una terminal.

No reemplaza a `setup.py`: los modos --solo-carga/--solo-analisis/
--exportar de la CLI siguen viviendo ahí tal cual, porque combinan los
pasos de otra manera. Esto cubre únicamente el camino "todo de una vez",
que es el que tiene sentido disparar con un clic.
"""

from pathlib import Path

from proceso import carga, esquema

RAIZ = Path(__file__).resolve().parent.parent
SQL = RAIZ / "sql"


def ejecutar(conexion, carpeta_entrada: Path) -> dict:
    """Crea el esquema, carga los CSV de `carpeta_entrada` y recalcula el
    consolidado. Devuelve un resumen para mostrarlo o registrarlo.

    Lanza RuntimeError si no hay ningún CSV en carpeta_entrada — mismo
    caso que ya maneja `setup.py` al no encontrar archivos.
    """
    esquema.crear(conexion, SQL / "01_esquema.sql")

    archivos = list(carpeta_entrada.glob("*.csv"))
    if not archivos:
        raise RuntimeError(f"No hay archivos en {carpeta_entrada}")

    resultados = carga.cargar_todo(conexion, carpeta_entrada)
    total_cargado = sum(r["filas"] for r in resultados)

    esquema.crear(conexion, SQL / "02_homologacion.sql")
    esquema.crear(conexion, SQL / "03_consolidado.sql")
    esquema.crear(conexion, SQL / "03b_materializar.sql")

    cursor = conexion.cursor()
    cursor.execute("SELECT COUNT(*) FROM consolidado")
    total_consolidado = cursor.fetchone()[0]
    cursor.close()

    return {
        "archivos": resultados,
        "total_cargado": total_cargado,
        "total_consolidado": total_consolidado,
    }
