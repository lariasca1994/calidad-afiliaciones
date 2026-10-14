"""Exporta el consolidado de una cuenta a un libro de Excel con modelo de
datos, medidas DAX y tablas dinámicas listas para usar.

Un CSV no lleva ni medidas ni tablas dinámicas: quien lo abría tenía que
armar todo a mano. Este libro parte de una plantilla
(web/plantillas_excel/tablero_calidad.xlsx) construida una sola vez con
Excel por scripts/construir_plantilla_excel.ps1: la tabla "Consolidado"
está en el modelo de datos (Power Pivot), con sus medidas DAX y tablas
dinámicas encima.

Aquí solo se cambian las filas de la hoja "Datos". No se usa openpyxl a
propósito: al guardar descarta las partes que no entiende, entre ellas
el modelo de datos, y el libro perdería las medidas DAX. En cambio se
reescribe directamente el XML de esa hoja y el rango de su tabla, y se
marca el libro con refreshAllConnections: al abrirlo, Excel vuelve a
cargar la tabla en el modelo y recalcula medidas y tablas dinámicas.

Probado con Excel 365: abierto por una persona (o tras "Habilitar
edición" si llega en Vista protegida), las tablas dinámicas muestran las
filas de la cuenta. Abierto por automatización COM, Excel no aplica esa
recarga y hay que llamar a RefreshAll.
"""

import io
import re
import zipfile
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from web.tablero_datos import CANALES, DEPARTAMENTOS

PLANTILLA = Path(__file__).resolve().parent / "plantillas_excel" / "tablero_calidad.xlsx"

# (encabezado en Excel, expresión SQL). El orden y los encabezados deben
# coincidir con la tabla de la plantilla: las medidas DAX los usan.
COLUMNAS = [
    ("Canal", "canal_origen"),
    ("Periodo", "periodo"),
    ("Fecha radicación", "fecha_radicacion"),
    ("Departamento", "codigo_departamento"),
    ("Régimen", "regimen"),
    ("Estado", "estado_registro"),
    ("Clasificación", "clasificacion_tramite"),
    ("Tipo de documento", "tipo_documento_homologado"),
    ("Efectiva", "es_produccion_efectiva"),
    ("Duplicado multicanal", "marca_duplicado_multicanal"),
    ("Duplicado interno", "marca_duplicado_interno"),
    ("No homologado", "marca_no_homologado"),
    ("Territorio incompleto", "marca_territorio_incompleto"),
    ("Fecha inválida", "marca_fecha_invalida"),
    ("Registro crítico", "marca_registro_critico"),
]

_EPOCA_EXCEL = date(1899, 12, 30)


def _letra(indice: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA."""
    letras = ""
    indice += 1
    while indice:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def _valor(encabezado: str, valor):
    """Valor tal como va en la hoja: nombres legibles, fechas como serial."""
    if valor is None:
        return None
    if encabezado == "Canal":
        return CANALES.get(valor, valor)
    if encabezado == "Departamento":
        codigo = str(valor).strip()
        return DEPARTAMENTOS.get(codigo[:2], f"Código {codigo}") if codigo else None
    if isinstance(valor, date):
        return (valor - _EPOCA_EXCEL).days
    return valor


def _celda(ref: str, valor, estilo: str) -> str:
    atributo = f' s="{estilo}"' if estilo else ""
    if valor is None:
        return f'<c r="{ref}"{atributo}/>'
    if isinstance(valor, bool):
        valor = int(valor)
    if isinstance(valor, (int, float)):
        return f'<c r="{ref}"{atributo}><v>{valor}</v></c>'
    texto = escape(str(valor))
    return f'<c r="{ref}"{atributo} t="inlineStr"><is><t xml:space="preserve">{texto}</t></is></c>'


def _ruta_hoja_datos(libro: zipfile.ZipFile) -> str:
    """Archivo XML de la hoja "Datos", según workbook.xml y sus relaciones."""
    workbook = libro.read("xl/workbook.xml").decode("utf-8")
    rid = re.search(r'<sheet[^>]*name="Datos"[^>]*r:id="([^"]+)"', workbook).group(1)
    relaciones = libro.read("xl/_rels/workbook.xml.rels").decode("utf-8")
    destino = re.search(rf'<Relationship[^>]*Id="{rid}"[^>]*Target="([^"]+)"', relaciones)
    if destino is None:  # el orden de atributos puede variar
        destino = re.search(rf'<Relationship[^>]*Target="([^"]+)"[^>]*Id="{rid}"', relaciones)
    objetivo = destino.group(1).lstrip("/")
    return objetivo if objetivo.startswith("xl/") else f"xl/{objetivo}"


def _ruta_tabla(libro: zipfile.ZipFile, ruta_hoja: str) -> str:
    carpeta, nombre = ruta_hoja.rsplit("/", 1)
    relaciones = libro.read(f"{carpeta}/_rels/{nombre}.rels").decode("utf-8")
    objetivo = re.search(r'Target="([^"]*tables/[^"]+)"', relaciones).group(1)
    return "xl/tables/" + objetivo.rsplit("/", 1)[1]


def construir(filas: list[tuple]) -> bytes:
    """Libro de Excel con las filas dadas (en el orden de COLUMNAS)."""
    with zipfile.ZipFile(PLANTILLA) as plantilla:
        ruta_hoja = _ruta_hoja_datos(plantilla)
        ruta_tabla = _ruta_tabla(plantilla, ruta_hoja)
        hoja = plantilla.read(ruta_hoja).decode("utf-8")

        # Estilos de la primera fila de datos de la plantilla (fecha, números).
        fila2 = re.search(r'<row[^>]*r="2"[^>]*>(.*?)</row>', hoja, flags=re.S).group(1)
        estilos = {}
        for ref, estilo in re.findall(r'<c r="([A-Z]+)2"(?:[^>]*?\ss="(\d+)")?', fila2):
            estilos[ref] = estilo
        encabezado = re.search(r'<row[^>]*r="1"[^>]*>.*?</row>', hoja, flags=re.S).group(0)

        nombres = [c[0] for c in COLUMNAS]
        partes = [encabezado]
        for numero, fila in enumerate(filas, start=2):
            celdas = "".join(
                _celda(f"{_letra(i)}{numero}", _valor(nombres[i], v), estilos.get(_letra(i), ""))
                for i, v in enumerate(fila)
            )
            partes.append(f'<row r="{numero}">{celdas}</row>')
        ultima = max(len(filas) + 1, 2)
        rango = f"A1:{_letra(len(COLUMNAS) - 1)}{ultima}"

        hoja = re.sub(r"<sheetData>.*?</sheetData>|<sheetData/>",
                      lambda _: "<sheetData>" + "".join(partes) + "</sheetData>", hoja, flags=re.S)
        hoja = re.sub(r'<dimension ref="[^"]+"/>', f'<dimension ref="{rango}"/>', hoja)

        tabla = plantilla.read(ruta_tabla).decode("utf-8")
        tabla = re.sub(r'(<table\b[^>]*\sref=")[^"]+"', rf'\g<1>{rango}"', tabla, count=1)
        tabla = re.sub(r'(<autoFilter\b[^>]*\sref=")[^"]+"', rf'\g<1>{rango}"', tabla, count=1)

        salida = io.BytesIO()
        with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as libro:
            for item in plantilla.infolist():
                contenido = plantilla.read(item.filename)
                if item.filename == ruta_hoja:
                    contenido = hoja.encode("utf-8")
                elif item.filename == ruta_tabla:
                    contenido = tabla.encode("utf-8")
                elif item.filename == "xl/workbook.xml":
                    contenido = _actualizar_conexiones_al_abrir(contenido.decode("utf-8")).encode("utf-8")
                elif item.filename.startswith("xl/pivotCache/pivotCacheDefinition"):
                    # Solo las tablas dinámicas: marcar también las conexiones
                    # del modelo deja el libro sin poder abrirse.
                    contenido = _actualizar_al_abrir(contenido.decode("utf-8"), "pivotCacheDefinition").encode("utf-8")
                libro.writestr(item, contenido)
        return salida.getvalue()


def _actualizar_conexiones_al_abrir(xml: str) -> str:
    """Marca el libro para actualizar todas las conexiones al abrirlo: es lo
    que recarga el modelo de datos (y sus medidas DAX) desde la hoja Datos."""
    if "refreshAllConnections=" in xml:
        return re.sub(r'refreshAllConnections="[^"]*"', 'refreshAllConnections="1"', xml)
    if "<workbookPr" in xml:
        return re.sub(r"<workbookPr\b", '<workbookPr refreshAllConnections="1"', xml, count=1)
    return re.sub(r"(<workbook\b[^>]*>)", r'\1<workbookPr refreshAllConnections="1"/>', xml, count=1)


def _actualizar_al_abrir(xml: str, etiqueta: str) -> str:
    """Agrega refreshOnLoad="1" a cada <etiqueta ...> que no lo tenga."""
    def marcar(coincidencia):
        apertura = coincidencia.group(0)
        if "refreshOnLoad=" in apertura:
            return re.sub(r'refreshOnLoad="[^"]*"', 'refreshOnLoad="1"', apertura)
        return apertura.replace(f"<{etiqueta} ", f'<{etiqueta} refreshOnLoad="1" ', 1)
    return re.sub(rf"<{etiqueta}\s[^>]*>", marcar, xml)


def exportar(conexion, usuario_id: int) -> bytes:
    columnas = ", ".join(expresion for _, expresion in COLUMNAS)
    cursor = conexion.cursor()
    try:
        cursor.execute(
            f"SELECT {columnas} FROM consolidado WHERE usuario_id = %(usuario_id)s ORDER BY periodo",
            {"usuario_id": usuario_id},
        )
        filas = cursor.fetchall()
    finally:
        cursor.close()
    return construir(list(filas))
