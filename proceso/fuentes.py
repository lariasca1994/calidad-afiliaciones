"""Descripción de cada archivo de origen.

Las tres cosas que varían entre fuentes y que hay que declarar:

  - el separador: XML usa punto y coma, el resto usa barra vertical
  - la codificación: los archivos vienen en latin-1, no en UTF-8
  - el nombre de la tabla destino

Las columnas no se declaran aquí a propósito: se leen del encabezado del
archivo y se validan contra la tabla. Así, si una fuente cambia el orden
de sus campos, la carga sigue funcionando.
"""

FUENTES = [
    {
        "archivo": "HOMOLOGACION_DOCUMENTOS.csv",
        "tabla": "HOMOLOGACION_DOCUMENTOS",
        "separador": "|",
        "descripcion": "Catálogo maestro de tipos de documento",
    },
    {
        "archivo": "AFILIACIONES.csv",
        "tabla": "AFILIACIONES",
        "separador": "|",
        "descripcion": "Canal físico",
    },
    {
        "archivo": "DIGITAL.csv",
        "tabla": "DIGITAL",
        "separador": "|",
        "descripcion": "Canal digital",
    },
    {
        "archivo": "SAT.csv",
        "tabla": "SAT",
        "separador": "|",
        "descripcion": "Canal SAT (MinSalud)",
    },
    {
        "archivo": "PROCESO_IRL.csv",
        "tabla": "PROCESO_IRL",
        "separador": "|",
        "descripcion": "Novedades de relación laboral",
    },
    {
        "archivo": "XML.csv",
        "tabla": "XML_HISTORICO",
        "separador": ";",
        "descripcion": "Radicación histórica",
    },
]

# Los archivos vienen de sistemas Windows en español.
CODIFICACIONES = ["latin-1", "cp1252", "utf-8-sig"]
