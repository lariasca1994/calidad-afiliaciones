# 📘 Manual de usuario · Calidad de afiliaciones

Guía para usar el panel web paso a paso: qué significa cada campo, qué datos se ingresan y qué
protege la plataforma. Para la parte técnica (arquitectura, consola, Power Query) vuelve al
[README](../README.md).

**Demo:** [calidad-afiliaciones (Azure Container Apps)](https://calidad-afiliaciones.blueocean-86680030.eastus.azurecontainerapps.io/)

## Contenido

1. [En pocas palabras](#1-en-pocas-palabras)
2. [Antes de empezar](#2-antes-de-empezar)
3. [Paso a paso](#3-paso-a-paso)
4. [Qué información ingresas y dónde queda](#4-qué-información-ingresas-y-dónde-queda)
5. [Seguridad: qué se garantiza](#5-seguridad-qué-se-garantiza)
6. [Límites y recomendaciones](#6-límites-y-recomendaciones)
7. [Preguntas frecuentes](#7-preguntas-frecuentes)

---

## 1. En pocas palabras

El panel recibe los archivos de afiliación de tres canales (digital, SAT y físico) más los
históricos, deja **un solo registro por afiliado** y muestra una cifra de producción confiable con
sus problemas de calidad. Si no tienes archivos propios, un botón genera datos sintéticos con los
mismos problemas que tienen los reales.

## 2. Antes de empezar

- Solo necesitas un navegador; no hay que instalar nada.
- La base de datos se apaga cuando nadie la usa. Si al entrar aparece la página **En
  mantenimiento**, la base se está encendiendo: espera unos minutos y vuelve a intentarlo.
- **Usa datos de ejemplo.** La demo es pública; no subas archivos con documentos reales de
  afiliados (ver [Límites](#6-límites-y-recomendaciones)).

## 3. Paso a paso

### 3.1 Portada

![Portada del panel](img/manual/01-portada.png)

Desde la portada eliges **Crear cuenta** o **Iniciar sesión**. El botón de la luna, arriba a la
derecha, cambia entre tema claro y oscuro.

### 3.2 Crear una cuenta

![Formulario de registro con sus campos numerados](img/manual/02-registro.png)

| # | Campo | Qué escribir | Reglas |
|:-:|---|---|---|
| 1 | Correo | El correo con el que vas a entrar | Formato de correo válido; se guarda en minúsculas. No se envía ningún mensaje a ese correo |
| 2 | Contraseña | Tu contraseña | Máximo 72 bytes (las tildes, la ñ y los emojis cuentan doble o más) |
| 3 | Confirmar contraseña | La misma contraseña | Debe coincidir con el campo 2 |
| 4 | Crear cuenta | Botón | Crea la cuenta vacía y te deja con la sesión iniciada |

El registro es libre y no requiere aprobación. Si el correo ya existe, el panel lo avisa.

### 3.3 Iniciar sesión

![Formulario de inicio de sesión](img/manual/03-login.png)

| # | Campo | Qué escribir |
|:-:|---|---|
| 1 | Correo | El correo de tu cuenta |
| 2 | Contraseña | Tu contraseña |
| 3 | Entrar | Abre tu tablero de indicadores |

Si el correo o la contraseña no coinciden, el mensaje es el mismo en ambos casos, para no revelar
qué correos están registrados.

### 3.4 Tablero de indicadores

![Tablero con los botones de carga](img/manual/04-tablero.png)

| # | Botón | Qué hace |
|:-:|---|---|
| 1 | 🎲 Generar datos de ejemplo | Crea un conjunto sintético nuevo **solo para tu cuenta** y recalcula los indicadores en unos segundos. Cada clic simula un periodo distinto (ver abajo) |
| 2 | 📁 Subir mis archivos | Abre el formulario para cargar tus propios archivos (ver 3.5) |
| 3 | 📊 Excel con tablas dinámicas | Descarga un libro con tu consolidado, medidas DAX y tablas dinámicas listas (ver 3.7) |
| 4 | ⬇️ CSV | Descarga `consolidado.csv`, un archivo plano sin medidas ni tablas dinámicas |

**Cada generación es distinta.** Además de cambiar las personas, cada clic sortea un *escenario*:
cuánto aporta cada canal, el periodo (de 8 a 18 meses), la duplicidad, los rechazos y la calidad de
los datos. El recuadro 🧪 arriba del tablero dice cuál salió, por ejemplo *«Campaña de afiliación»*
(el canal digital se dispara y con él las radicaciones repetidas) o *«Migración de sistema»*
(llegan documentos fuera de catálogo y territorios sin dato).

| Escenario | Qué cambia |
|---|---|
| Operación estable | Los tres canales en su proporción habitual |
| Campaña de afiliación | Mucho más volumen digital, un mes pico y más duplicados |
| Canal presencial fuerte | El canal físico y SAT pesan más que el portal |
| Cierre con rechazos | Muchos trámites anulados, rechazados o sin prerradicar |
| Migración de sistema | Documentos fuera de catálogo y territorios sin dato |

### 3.5 Subir tus propios archivos

![Formulario para subir los seis archivos](img/manual/05-subir-archivos.png)

| # | Campo | Qué escribir | Reglas |
|:-:|---|---|---|
| 1 | Seleccionar archivos | Los **6 archivos** de origen a la vez | Nombres exactos: `AFILIACIONES.csv`, `DIGITAL.csv`, `SAT.csv`, `PROCESO_IRL.csv`, `XML.csv` y `HOMOLOGACION_DOCUMENTOS.csv`. Máximo **50 MB** por archivo. No se acepta una carga parcial |
| 2 | Subir y procesar | Botón | Reemplaza los datos que tuviera tu cuenta y corre el mismo proceso de depuración |

### 3.6 Leer los resultados

![Tablero completo con todos los bloques de indicadores](img/manual/06-tablero-completo.png)

Arriba hay una barra fija con las secciones del tablero y el filtro **Ver canal** (Todos, Digital,
Físico o SAT): al elegir un canal se recalculan los indicadores, los hallazgos, el embudo, la
tendencia, el tipo de trámite, el estado, el régimen y el territorio, sin recargar la página.

| Sección | Qué responde |
|---|---|
| Resumen ejecutivo | Seis indicadores con semáforo (verde, ámbar o rojo): producción consolidada, producción efectiva, duplicidad multicanal e interna, calidad del dato y registros críticos. El botón **?** de cada uno explica qué mide y cuál es la referencia |
| Lo más importante | Hallazgos escritos en frases sencillas: qué canal pesa más, cuánto se descartó, el mes pico, la fuente con más problemas |
| De dónde salen los datos | Los seis archivos de origen con sus filas, los pasos del proceso y el embudo: recibidos → descartados por repetidos → consolidado → producción efectiva |
| Producción en el tiempo | Trámites, producción efectiva y duplicados por mes. Si el último mes está incompleto, el tablero lo avisa |
| Canales y tipo de trámite | Aporte y depuración por canal, reinscripción/traslado/afiliación nueva, estado del trámite y régimen |
| Calidad por fuente | Semáforo de homologación, territorio y fecha válida por canal, y los tipos de documento fuera de catálogo |
| Distribución territorial | Los departamentos con más trámites; "Sin dato" en rojo cuando falta el territorio |
| Glosario | Qué significa cada término, en palabras sencillas |

Cada sección tiene un **¿Cómo leer esto?** que se despliega con la explicación, y en los gráficos
puedes pasar el cursor (o tocar) para ver el valor exacto, o tocar la leyenda para ocultar una serie.

### 3.7 Descargar el Excel con tablas dinámicas

El botón **📊 Excel con tablas dinámicas** descarga `calidad_afiliaciones.xlsx`, con tres hojas:

| Hoja | Qué tiene |
|---|---|
| Inicio | Cómo usar el libro y la fórmula DAX de cada medida |
| Tablero | Cuatro tablas dinámicas sobre el modelo de datos (resumen por canal, trámites por periodo y canal, tipo de trámite, departamento) con segmentaciones de **Canal** y **Régimen** |
| Datos | Tu consolidado, una fila por afiliado, como tabla de Excel |

La tabla entra al **modelo de datos** (Power Pivot) con 11 medidas DAX, por ejemplo
`% Efectiva = DIVIDE([Producción efectiva], [Trámites])`. Al abrir el libro, Excel recarga el modelo
y las tablas dinámicas con tus datos. Si llega en **Vista protegida**, pulsa **Habilitar edición**;
si las tablas dinámicas siguen mostrando otras cifras, usa **Datos → Actualizar todo**. Para tus
propios análisis: **Insertar → Tabla dinámica → Desde el modelo de datos** y arrastra las medidas.

## 4. Qué información ingresas y dónde queda

| Dato | Para qué se usa | Dónde se guarda | Cómo se protege |
|---|---|---|---|
| Correo | Identificar tu cuenta | Tabla `usuarios` en MySQL (Aiven) | Solo lo ves tú; no se muestra a otras cuentas |
| Contraseña | Iniciar sesión | Tabla `usuarios`, **solo su huella bcrypt** | Nunca se guarda en texto plano ni se puede recuperar |
| Archivos CSV que subes | Calcular tus indicadores | Carpeta de tu cuenta en el contenedor y tablas de MySQL marcadas con tu `usuario_id` | Cada consulta filtra por tu cuenta |
| Datos de ejemplo | Probar el panel | Igual que los archivos, marcados con tu `usuario_id` | Son sintéticos: no corresponden a personas reales |
| Sesión | Mantenerte conectado | Cookie `sesion` en tu navegador | Firmada (JWT HS256), invisible para JavaScript (`HttpOnly`), vence a las 8 horas |

## 5. Seguridad: qué se garantiza

Comprobado en el código del proyecto (`web/seguridad.py`, `web/main.py`, `proceso/conexion.py`):

- **Contraseñas con bcrypt.** Solo se guarda la huella; ni el administrador puede ver tu
  contraseña.
- **Sesión en cookie `HttpOnly` y `SameSite=Lax`**, firmada con una clave secreta del servidor y
  válida por 8 horas. **Salir** la borra.
- **Aislamiento por cuenta.** Todas las tablas llevan `usuario_id` y cada consulta, carga o
  exportación se limita a tu cuenta: dos cuentas nunca ven ni mezclan sus datos, aunque generen
  datos al mismo tiempo.
- **Consultas parametrizadas** contra MySQL (sin concatenar texto del usuario en el SQL), lo que
  evita la inyección SQL.
- **Plantillas con escape automático** (Jinja2): lo que escribes se muestra como texto, no como
  código.
- **Conexión cifrada a la base.** La conexión a MySQL usa TLS por defecto, y Aiven rechaza
  conexiones sin cifrar.
- **Carga controlada.** Solo se aceptan los 6 nombres de archivo esperados, con un máximo de 50 MB
  cada uno.
- **Secretos fuera del repositorio.** La clave JWT y los datos de conexión viven en variables de
  entorno; el `.gitignore` bloquea cualquier CSV o `.xlsx` para que nunca se publiquen datos de
  afiliados. La única excepción es la plantilla del Excel descargable, que solo trae 3 filas
  inventadas: tus datos se escriben en el libro en memoria al descargarlo, nunca en el repositorio.

## 6. Límites y recomendaciones

Es una demo de portafolio, no un sistema certificado para datos personales de salud:

- **No subas datos reales de afiliados** a la instancia pública. Para datos reales, corre el
  proyecto en tu equipo (ver [Instalación](../README.md#6-instalación-para-pruebas)).
- No hay verificación del correo ni recuperación de contraseña: si la olvidas, crea otra cuenta.
- No hay longitud mínima de contraseña ni bloqueo por intentos fallidos: elige una contraseña
  larga y que no uses en otros sitios.
- El Excel que descargas del tablero (y cualquier libro conectado a la base) guarda una copia de
  los datos dentro del `.xlsx`, también en su modelo de datos. Trátalo como un archivo con datos.

## 7. Preguntas frecuentes

**¿Por qué a veces aparece "En mantenimiento"?** La base se apaga sin uso para no generar costos
y tarda unos minutos en volver a encenderse. Espera un momento y vuelve a entrar.

**¿Otra persona puede ver mis datos?** No. Cada cuenta ve solo lo que generó o subió.

**¿Puedo borrar mis datos?** Al generar datos de ejemplo o subir archivos nuevos, se reemplaza
todo lo que tenía tu cuenta.

**¿Por qué cada vez que genero datos salen cifras distintas?** A propósito: cada generación simula
un periodo diferente (ver el recuadro 🧪 del tablero), para que puedas ver cómo cambia el informe
cuando cambian el volumen, la duplicidad o la calidad de los datos.

**El Excel abre con las tablas dinámicas vacías o con otras cifras.** Pulsa **Habilitar edición**
si aparece la Vista protegida y, si hace falta, **Datos → Actualizar todo**. El libro necesita Excel
de escritorio para Windows 2016 o posterior (Microsoft 365 incluido): Excel en la web y Excel para
Mac no editan modelos de datos de Power Pivot.
