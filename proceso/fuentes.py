"""Descripción de cada archivo de origen.

Las tres cosas que varían entre fuentes y que hay que declarar:

  - el separador: XML usa punto y coma, el resto usa barra vertical
  - la codificación: los archivos vienen en latin-1, no en UTF-8
  - el nombre de la tabla destino

Las columnas no se declaran aquí a propósito: se leen del encabezado del
archivo y se validan contra la tabla. Así, si una fuente cambia el orden
de sus campos, la carga sigue funcionando.

"usuario_scoped" decide cómo se limpia la tabla antes de cargar (ver
carga.py). HOMOLOGACION_DOCUMENTOS es el único catálogo compartido por
todas las cuentas —el mismo contenido para cualquiera—, así que se trunca
entero en cada carga sin que eso afecte a nadie más. Las demás tablas
tienen datos propios de cada cuenta (columna usuario_id): ahí no se puede
truncar la tabla completa, solo borrar las filas de ese usuario antes de
insertar las suyas de nuevo.
"""

FUENTES = [
    {
        "archivo": "HOMOLOGACION_DOCUMENTOS.csv",
        "tabla": "HOMOLOGACION_DOCUMENTOS",
        "separador": "|",
        "descripcion": "Catálogo maestro de tipos de documento",
        "usuario_scoped": False,
    },
    {
        "archivo": "AFILIACIONES.csv",
        "tabla": "AFILIACIONES",
        "separador": "|",
        "descripcion": "Canal físico",
        "usuario_scoped": True,
    },
    {
        "archivo": "DIGITAL.csv",
        "tabla": "DIGITAL",
        "separador": "|",
        "descripcion": "Canal digital",
        "usuario_scoped": True,
    },
    {
        "archivo": "SAT.csv",
        "tabla": "SAT",
        "separador": "|",
        "descripcion": "Canal SAT (MinSalud)",
        "usuario_scoped": True,
    },
    {
        "archivo": "PROCESO_IRL.csv",
        "tabla": "PROCESO_IRL",
        "separador": "|",
        "descripcion": "Novedades de relación laboral",
        "usuario_scoped": True,
    },
    {
        "archivo": "XML.csv",
        "tabla": "XML_HISTORICO",
        "separador": ";",
        "descripcion": "Radicación histórica",
        "usuario_scoped": True,
    },
]

# Los archivos vienen de sistemas Windows en español.
CODIFICACIONES = ["latin-1", "cp1252", "utf-8-sig"]
