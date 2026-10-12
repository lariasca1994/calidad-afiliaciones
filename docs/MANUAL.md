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
| 1 | 🎲 Generar datos de ejemplo | Crea un conjunto sintético nuevo **solo para tu cuenta** (cambia en cada clic) y recalcula los indicadores en segundos |
| 2 | 📁 Subir mis archivos | Abre el formulario para cargar tus propios archivos (ver 3.5) |
| — | ⬇️ Exportar CSV | Descarga `consolidado.csv` con el consolidado de tu cuenta |

### 3.5 Subir tus propios archivos

![Formulario para subir los seis archivos](img/manual/05-subir-archivos.png)

| # | Campo | Qué escribir | Reglas |
|:-:|---|---|---|
| 1 | Seleccionar archivos | Los **6 archivos** de origen a la vez | Nombres exactos: `AFILIACIONES.csv`, `DIGITAL.csv`, `SAT.csv`, `PROCESO_IRL.csv`, `XML.csv` y `HOMOLOGACION_DOCUMENTOS.csv`. Máximo **50 MB** por archivo. No se acepta una carga parcial |
| 2 | Subir y procesar | Botón | Reemplaza los datos que tuviera tu cuenta y corre el mismo proceso de depuración |

### 3.6 Leer los resultados

![Tablero completo con todos los bloques de indicadores](img/manual/06-tablero-completo.png)

| Bloque | Qué responde |
|---|---|
| Cifras principales | Cuántas afiliaciones reales hubo (producción consolidada), cuántos registros llegaron en bruto y cuántos problemas de calidad hay |
| Clasificación del trámite | Cuántas son reinscripciones, traslados o afiliaciones nuevas |
| Aporte y depuración por fuente | Cuántos registros aportó cada canal y cuántos se descartaron por duplicados |
| Calidad por fuente | Porcentaje de registros con documento homologado, territorio y fecha válidos |
| Tipos de documento fuera de catálogo | Tipos de documento que llegaron y no existen en el catálogo |

El recuadro **Cómo leer estos indicadores** explica, en la misma página, las diferencias que más se
confunden (duplicidad multicanal frente a interna, por ejemplo).

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
  afiliados.

## 6. Límites y recomendaciones

Es una demo de portafolio, no un sistema certificado para datos personales de salud:

- **No subas datos reales de afiliados** a la instancia pública. Para datos reales, corre el
  proyecto en tu equipo (ver [Instalación](../README.md#6-instalación-para-pruebas)).
- No hay verificación del correo ni recuperación de contraseña: si la olvidas, crea otra cuenta.
- No hay longitud mínima de contraseña ni bloqueo por intentos fallidos: elige una contraseña
  larga y que no uses en otros sitios.
- Si guardas en Excel un libro conectado a la base, recuerda que el `.xlsx` guarda una copia de los
  datos consultados.

## 7. Preguntas frecuentes

**¿Por qué a veces aparece "En mantenimiento"?** La base se apaga sin uso para no generar costos
y tarda unos minutos en volver a encenderse. Espera un momento y vuelve a entrar.

**¿Otra persona puede ver mis datos?** No. Cada cuenta ve solo lo que generó o subió.

**¿Puedo borrar mis datos?** Al generar datos de ejemplo o subir archivos nuevos, se reemplaza
todo lo que tenía tu cuenta.
