# Calidad de afiliaciones multicanal

Consolidación y análisis de calidad de la producción de afiliaciones de una EPS
que recibe trámites por tres canales distintos, más un histórico de radicación
y un archivo de novedades laborales.

El problema: cada canal reporta con su propio formato, el mismo afiliado puede
radicar por varias vías, y no existe una cifra única de producción en la que se
pueda confiar.

`MySQL` · `Python` · `pandas` · `Power Query` · `Power Pivot`

---

## Explóralo en tres minutos

No hacen falta datos reales para probar el proyecto. Hay un generador que crea
las seis fuentes con la misma estructura, separadores y codificación que los
archivos originales, reproduciendo a propósito los mismos problemas que
aparecieron al analizar los datos reales.

```bash
git clone https://github.com/lariasca1994/calidad-afiliaciones.git
cd calidad-afiliaciones

python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
source .venv/bin/activate         # Linux o macOS

pip install -r requirements.txt
cp .env.example .env
```

Completa el `.env` con una base MySQL propia (ver [Requisitos](#requisitos) e
[Instalación](#instalación) más abajo), y luego:

```bash
python generador/datos_demo.py
python setup.py
```

Eso deja el tablero de indicadores en pantalla, con los mismos hallazgos que
aparecen al analizar los datos reales —duplicidad multicanal, duplicidad
interna, documentos fuera de catálogo, novedades laborales que no son
afiliaciones— aunque las cifras no sean idénticas, por tratarse de datos
aleatorios.

A partir de ahí, el resto queda a criterio de quien lo explore: revisar el SQL
en `sql/`, leer las decisiones en `docs/decisiones.md`, conectar Excel para
armar tablas dinámicas sobre la tabla `consolidado` (ver
[Power Query y Power Pivot](#power-query-y-power-pivot)), o abrir el
[panel web](#panel-web-opcional).

---

## El problema en concreto

Seis fuentes que no hablan entre sí:

| Fuente | Registros | Qué aporta |
|---|---|---|
| Canal digital | 64.562 | Portal y aplicación, con estado del trámite |
| SAT | 10.013 | Radicación oficial ante el Ministerio |
| Canal físico | 1.332 | Puntos de atención presencial |
| Radicación histórica | 218.416 | Antecedente del afiliado y entidad previa |
| Novedades laborales | 167.274 | Relaciones laborales, no afiliaciones |
| Catálogo de documentos | 15 | Homologación de tipos de identificación |

Tres obstáculos que impiden sumar directamente:

**Los tipos de documento no coinciden.** SAT usa el código numérico del
catálogo; las demás fuentes, la abreviatura. Un `CC` y un `3` son el mismo tipo
de documento, pero ningún sistema lo sabe.

**El mismo afiliado aparece varias veces.** Entre canales y dentro del mismo
canal. Sumar las tres fuentes cuenta a la misma persona hasta tres veces.

**Las novedades laborales parecen afiliaciones.** Son 167.274 registros que, si
se incluyen, multiplican la producción por más de tres.

---

## Cómo funciona

```
Archivos de origen
      ↓
  Carga en MySQL          los campos entran como texto: rechazar filas
      ↓                    impediría medir la calidad
  Homologación            llave única tipo-número, común a todos los canales
      ↓
  Antecedente histórico   determina reinscripción, traslado o afiliación nueva
      ↓
  Depuración              un registro por afiliado, según prioridad de canal
      ↓
  Marcas de calidad       se acumulan; no reemplazan la clasificación
      ↓
  Indicadores             tablero y exportación
```

Las decisiones que sostienen cada paso están en **[docs/decisiones.md](docs/decisiones.md)**,
incluidos los criterios alternativos razonables y qué cambiaría al adoptarlos.

---

## Estructura

```
sql/
├── 01_esquema.sql          Tablas de origen con índices
├── 02_homologacion.sql     Llave única, antecedente y duplicidad
├── 03_consolidado.sql      Clasificación y marcas de calidad
└── 04_indicadores.sql      Once consultas para el tablero

proceso/
├── conexion.py             Conexión con la base
├── fuentes.py              Separador y codificación de cada archivo
├── carga.py                Carga por lotes
├── esquema.py              Ejecución de los .sql
└── analisis.py             Indicadores y exportación

web/                        Panel web opcional (ver más abajo)

datos/entrada/              Archivos de origen · excluidos del repositorio
datos/salida/               Consolidado exportado · excluido
docs/decisiones.md          Criterios adoptados y sus alternativas
excel/                      Ver Power Query y Power Pivot más abajo
setup.py                    Comando único
```

---

## Requisitos

- Python 3.10 o superior
- Una base MySQL 8 accesible

El proyecto se desarrolló contra un servicio gestionado en la nube, pero
funciona con cualquier MySQL 8 cambiando el `.env`.

---

## Instalación

```bash
git clone https://github.com/lariasca1994/calidad-afiliaciones.git
cd calidad-afiliaciones

python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows
source .venv/bin/activate         # Linux o macOS

pip install -r requirements.txt
cp .env.example .env
```

Completa el `.env` con los datos de conexión. La plantilla indica qué es cada
variable.

---

## Uso

### Con datos propios

Coloca los archivos de origen en `datos/entrada/` y ejecuta:

```bash
python setup.py
```

### Con datos sintéticos

Si no tienes los archivos reales a mano, hay un generador que crea las seis
fuentes con la misma estructura, separadores y codificación que los archivos
originales, reproduciendo a propósito los mismos problemas que aparecieron al
analizar los datos reales: un tipo de documento fuera de catálogo, duplicidad
entre canales y dentro del mismo canal, registros sin fecha de radicación por
estar anulados o rechazados, y el territorio del histórico escrito como texto.

```bash
python generador/datos_demo.py
python setup.py
```

`--escala 3` genera el triple de filas; `--semilla 7` cambia la aleatoriedad
manteniendo reproducibilidad. Por seguridad, el generador no sobrescribe
archivos existentes en `datos/entrada/` sin `--forzar`: evita borrar datos
reales por accidente.

El proceso crea el esquema, carga las seis fuentes, construye las vistas y
muestra los indicadores en pantalla.

| Comando | Qué hace |
|---|---|
| `python setup.py` | Todo el proceso |
| `python setup.py --solo-carga` | Recarga los archivos sin recrear el esquema |
| `python setup.py --solo-analisis` | Recalcula vistas e indicadores |
| `python setup.py --exportar` | Exporta el consolidado a `datos/salida/` |

La carga tarda unos minutos: son más de 400.000 filas y se insertan por lotes.

### Sobre los archivos de origen

**No están en el repositorio.** Contienen documentos de identidad, nombres y
fechas de nacimiento. La carpeta `datos/entrada/` está excluida, y el
`.gitignore` bloquea además cualquier CSV suelto como red de seguridad.

Los archivos esperados son `AFILIACIONES.csv`, `DIGITAL.csv`, `SAT.csv`,
`PROCESO_IRL.csv`, `XML.csv` y `HOMOLOGACION_DOCUMENTOS.csv`. La estructura de
cada uno se deduce del esquema en `sql/01_esquema.sql`.

---

## Encendido automático (opcional)

El plan gratuito de Aiven apaga el servicio tras un periodo de inactividad.
Encenderlo de nuevo no es instantáneo: Aiven restaura el último respaldo, lo
que puede tardar desde un par de minutos hasta bastante más, según el tamaño
de los datos.

Completando estas variables en el `.env`, el proyecto verifica el estado antes
de conectar y lo enciende solo si hace falta, esperando a que quede listo:

```
AIVEN_API_TOKEN=
AIVEN_PROJECT_NAME=
AIVEN_SERVICE_NAME=
```

El token se genera en el panel de Aiven, en el menú de tu usuario → *Personal
tokens* → *Generate token*. Sin estas variables, el proyecto funciona igual;
solo hay que encender el servicio a mano cuando esté apagado.

---

## Panel web (opcional)

Además del tablero de consola (`python setup.py`) y de Power Query/Power
Pivot en Excel, hay un panel web mínimo en `web/` que muestra los mismos
cinco bloques de indicadores en una página, con tema claro/oscuro.

```bash
pip install -r requirements.txt   # ya incluye fastapi/uvicorn
uvicorn web.main:app --reload --port 8400
```

Abre `http://localhost:8400` — pide iniciar sesión antes de ver el tablero.
No hay registro público: es un panel de un único usuario, pensado para
revisar el proyecto sin depender de Excel.

## Power Query y Power Pivot

Excel se conecta directamente a la tabla `consolidado` en la base de datos, no
a los CSV: cada vez que se actualiza el libro, trae lo último que haya en
Aiven.

### 1. Instalar el conector

Power Query necesita el **MySQL Connector/NET**, gratuito, de Oracle:
[dev.mysql.com/downloads/connector/net](https://dev.mysql.com/downloads/connector/net/).
Elige la versión Windows (MSI Installer); hay un enlace para descargar sin
crear cuenta ("No thanks, just start my download").

Instálalo con las opciones por defecto y **cierra Excel por completo** antes,
si lo tenías abierto: el conector se registra como complemento del sistema y
Excel necesita reiniciar para detectarlo.

### 2. Verificar que Excel lo reconoce

**Datos → Obtener datos → Desde base de datos → Desde base de datos de
MySQL**. Si aparece en la lista, quedó instalado. Si no aparece, reinicia el
equipo: a veces el registro del driver no se completa hasta el siguiente
arranque.

### 3. Conectar

En la ventana de conexión:

| Campo | Valor |
|---|---|
| Servidor | el host y puerto del `.env` (`DB_HOST:DB_PORT`) |
| Base de datos | el valor de `DB_NAME` |

En la siguiente pantalla aparece un panel a la izquierda con varias pestañas
apiladas: **Windows**, **Base de datos**, **Cuenta Microsoft**. Por defecto
suele quedar seleccionada **Windows**, que intenta autenticar contra el
sistema operativo y nunca va a funcionar contra Aiven, sin importar cuántas
veces se reintente con la contraseña correcta.

**Hay que cambiar explícitamente a la pestaña "Base de datos"** (a veces
aparece como *Basic*). Ahí sí aparecen los campos de usuario y contraseña —los
mismos `DB_USER` y `DB_PASSWORD` del `.env`—, y una opción de nivel de
cifrado, que debe quedar en la que exige SSL/TLS: Aiven no acepta conexiones
sin cifrar.

Si tras cambiar de pestaña Excel sigue mostrando el error de credenciales aun
con los datos correctos, es casi siempre caché: **Datos → Obtener datos →
Configuración del origen de datos**, localizar la entrada del servidor,
**Editar permisos → Borrar permisos**, y volver a intentar la conexión desde
cero.

### 4. Antes de conectar, comprobar que el servicio esté encendido

Excel no tiene el despertador automático que sí tiene `setup.py`. Si el
servicio lleva un rato sin uso, hay que despertarlo antes:

```bash
python setup.py --solo-analisis
```

O entrar un momento al panel de Aiven.

### 5. El modelo

Una vez conectada la consulta, **Agregar al modelo de datos** desde Power
Query la incorpora a Power Pivot. Desde ahí, tabla dinámica con `periodo` en
filas, `clasificacion_tramite` en columnas y recuento de `fila_id` en valores
da la clasificación del trámite (Reinscripción / Traslado / Afiliación Nueva)
por periodo, ya interactiva y filtrable por segmentadores.

### Una advertencia antes de guardar el libro

Un archivo `.xlsx` con la consulta cargada al modelo de datos **guarda una
copia completa de lo consultado dentro del propio binario**, documentos de
identidad incluidos, aunque ninguna hoja los muestre visiblemente. No es un
detalle menor: es la razón por la que este repositorio excluye por completo
cualquier `.xlsx`, sin excepción, en el `.gitignore`.

El archivo de trabajo con datos reales se queda siempre en el equipo local,
nunca en el repositorio.

---

## Nota técnica

La carga no usa `LOAD DATA LOCAL INFILE`. Ese comando exige que el servidor lo
tenga habilitado, y los servicios gestionados suelen traerlo desactivado. La
inserción por lotes desde Python es algo más lenta, pero funciona sin tocar la
configuración del servidor y permite resolver de paso dos particularidades de
los archivos: vienen en codificación latin-1 y usan separadores distintos —barra
vertical en cinco fuentes, punto y coma en la radicación histórica—.

---

## Licencia

MIT