"""Pipeline completo de esquema + carga + homologación + consolidado,
por usuario.

Extrae en funciones lo que hace `setup.py` desde la línea de comandos
(crear esquema, cargar los CSV de una carpeta, y recalcular homologación/
consolidado/materializado), para poder invocarlo también desde el panel
web —el botón "Generar datos de ejemplo" en el tablero— sin duplicar la
lógica ni depender de una terminal. `setup.py` usa las mismas funciones
para su modo por defecto, así que el comportamiento es idéntico en los
dos caminos.

Con registro público de cuentas, cada usuario tiene su propio conjunto de
datos dentro de las mismas tablas (columna usuario_id — ver
sql/01_esquema.sql). Por eso todo aquí recibe `usuario_id` explícito: no
hay un "usuario por defecto" salvo el que use `setup.py` (usuario_id=0,
reservado para corridas por consola con datos reales, que no pertenecen
a ninguna cuenta web).
"""

from pathlib import Path

from proceso import carga, esquema

RAIZ = Path(__file__).resolve().parent.parent
SQL = RAIZ / "sql"

_COLUMNAS_CONSOLIDADO = [
    "usuario_id", "llave_afiliado", "canal_origen", "id_radicado",
    "tipo_documento_homologado", "tipo_documento_recibido", "numero_documento",
    "fecha_radicacion", "periodo", "codigo_asesor", "codigo_departamento",
    "codigo_municipio", "nombre_ips", "tipo_afiliado", "estado_registro", "regimen",
    "clasificacion_tramite", "marca_no_homologado", "marca_documento_vacio",
    "marca_territorio_incompleto", "marca_fecha_invalida",
    "marca_duplicado_multicanal", "marca_duplicado_interno",
    "marca_registro_critico", "es_produccion_efectiva",
    "canales_en_que_aparece", "veces_radicado",
]


def materializar_consolidado(conexion, usuario_id: int) -> int:
    """Reemplaza las filas de `consolidado` de UN usuario con lo que haya
    ahora mismo en vw_consolidado para ese usuario. Separada de
    `ejecutar()` porque `setup.py --solo-analisis` también la necesita
    sin volver a cargar archivos.

    No usa un DROP TABLE + INSERT global (como antes de tener varias
    cuentas): eso borraría el consolidado de todo el mundo. En su lugar,
    DELETE + INSERT acotados con usuario_id — ver sql/03b_materializar.sql
    para el porqué completo.
    """
    columnas_sql = ", ".join(_COLUMNAS_CONSOLIDADO)

    cursor = conexion.cursor()
    cursor.execute(
        "DELETE FROM consolidado WHERE usuario_id = %(usuario_id)s",
        {"usuario_id": usuario_id},
    )
    cursor.execute(
        f"""
        INSERT INTO consolidado ({columnas_sql})
        SELECT {columnas_sql}
        FROM vw_consolidado
        WHERE usuario_id = %(usuario_id)s
        """,
        {"usuario_id": usuario_id},
    )
    conexion.commit()

    cursor.execute(
        "SELECT COUNT(*) FROM consolidado WHERE usuario_id = %(usuario_id)s",
        {"usuario_id": usuario_id},
    )
    total = cursor.fetchone()[0]
    cursor.close()
    return total


def ejecutar(conexion, carpeta_entrada: Path, usuario_id: int) -> dict:
    """Crea el esquema, carga los CSV de `carpeta_entrada` para
    `usuario_id` y recalcula su consolidado. Devuelve un resumen.

    Lanza RuntimeError si no hay ningún CSV en carpeta_entrada — mismo
    caso que ya maneja `setup.py` al no encontrar archivos.
    """
    esquema.crear(conexion, SQL / "01_esquema.sql")

    archivos = list(carpeta_entrada.glob("*.csv"))
    if not archivos:
        raise RuntimeError(f"No hay archivos en {carpeta_entrada}")

    resultados = carga.cargar_todo(conexion, carpeta_entrada, usuario_id)
    total_cargado = sum(r["filas"] for r in resultados)

    esquema.crear(conexion, SQL / "02_homologacion.sql")
    esquema.crear(conexion, SQL / "03_consolidado.sql")
    esquema.crear(conexion, SQL / "03b_materializar.sql")

    total_consolidado = materializar_consolidado(conexion, usuario_id)

    return {
        "archivos": resultados,
        "total_cargado": total_cargado,
        "total_consolidado": total_consolidado,
    }
