#!/usr/bin/env python3
"""Consolidación y análisis de calidad de afiliaciones multicanal.

    python setup.py                Ejecuta todo: esquema, carga y análisis
    python setup.py --solo-carga   Carga los archivos sin recrear el esquema
    python setup.py --solo-analisis  Solo recalcula vistas e indicadores
    python setup.py --exportar     Exporta el consolidado a datos/salida/

Los archivos de origen se buscan en datos/entrada/. Esa carpeta está
excluida del repositorio: contiene documentos, nombres y fechas de
nacimiento.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from proceso import analisis, carga, esquema
from proceso.conexion import conectar, describir

RAIZ = Path(__file__).resolve().parent
ENTRADA = RAIZ / "datos" / "entrada"
SALIDA = RAIZ / "datos" / "salida"


def titulo(texto: str) -> None:
    print(f"\n{texto}")
    print("─" * max(46, len(texto)))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Consolidación de afiliaciones multicanal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--solo-carga", action="store_true",
                        help="carga los archivos sin recrear el esquema")
    parser.add_argument("--solo-analisis", action="store_true",
                        help="recalcula vistas e indicadores con lo ya cargado")
    parser.add_argument("--exportar", action="store_true",
                        help="exporta el consolidado a datos/salida/")

    args = parser.parse_args()

    inicio = time.time()

    print(f"\nConsolidación de afiliaciones multicanal")
    print(f"Base de datos: {describir()}")

    conexion = conectar()
    print("Conexión establecida")

    try:
        # --- Esquema ---------------------------------------------------
        if not args.solo_carga and not args.solo_analisis:
            titulo("1 · Esquema")
            esquema.crear(conexion, RAIZ / "sql" / "01_esquema.sql")

        # --- Carga -----------------------------------------------------
        if not args.solo_analisis:
            titulo("2 · Carga de archivos")

            archivos = list(ENTRADA.glob("*.csv"))
            if not archivos:
                print(f"  No hay archivos en {ENTRADA}")
                print("  Coloca ahí los CSV de origen y vuelve a ejecutar.")
                return 1

            resultados = carga.cargar_todo(conexion, ENTRADA)

            total = sum(r["filas"] for r in resultados)
            print(f"\n  Total cargado: {total:,} filas")

        # --- Vistas y materializacion ------------------------------------
        titulo("3 · Homologación y consolidado")
        esquema.crear(conexion, RAIZ / "sql" / "02_homologacion.sql")
        esquema.crear(conexion, RAIZ / "sql" / "03_consolidado.sql")
        print("  Vistas creadas")

        print("  Materializando el consolidado...")
        esquema.crear(conexion, RAIZ / "sql" / "03b_materializar.sql")

        cursor = conexion.cursor()
        cursor.execute("SELECT COUNT(*) FROM consolidado")
        print(f"  {cursor.fetchone()[0]:,} registros consolidados")
        cursor.close()

        # --- Indicadores -----------------------------------------------
        titulo("4 · Indicadores")
        analisis.mostrar_tablero(conexion)

        # --- Exportación -----------------------------------------------
        if args.exportar:
            titulo("5 · Exportación")
            analisis.exportar(conexion, SALIDA)

    finally:
        conexion.close()

    print(f"\nTerminado en {time.time() - inicio:.1f} s\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
