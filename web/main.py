import html
import random
import threading
import time
import sys
from pathlib import Path
from urllib.parse import quote

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymysql
from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from generador import datos_demo
from proceso import analisis, esquema, pipeline
from proceso.conexion import BaseNoDisponible, conectar
from proceso.fuentes import FUENTES
from web import correo, exportar_excel, tablero_datos
from web.seguridad import (
    NOMBRE_COOKIE,
    RECUPERAR_MINUTOS,
    crear_token,
    crear_token_recuperacion,
    hashear_password,
    huella_coincide,
    leer_token_recuperacion,
    requiere_sesion,
    sesion_opcional,
    verificar_password,
)

app = FastAPI(title="Calidad de Afiliaciones")
app.mount("/static", StaticFiles(directory="web/static"), name="static")
plantillas = Jinja2Templates(directory="web/templates")


@app.exception_handler(BaseNoDisponible)
def base_no_disponible(request: Request, _error: BaseNoDisponible):
    """Base apagada o sin conexión: página de mantenimiento (503), no un error genérico."""
    return plantillas.TemplateResponse(
        request, "mantenimiento.html", status_code=503, headers={"Retry-After": "3600"}
    )

RAIZ = Path(__file__).resolve().parent.parent

# Misma carpeta que usa `python setup.py` al exportar — la mantiene el
# uso por consola (usuario_id=0). El panel web exporta a una subcarpeta
# POR CUENTA (ver CARPETA_SALIDA_USUARIOS) para no mezclar descargas de
# dos personas que exportan casi al mismo tiempo.
CARPETA_SALIDA = RAIZ / "datos" / "salida"

# Misma carpeta que lee `python setup.py` al cargar — la mantiene el uso
# por consola. El botón "Generar datos de ejemplo" del panel web escribe
# en CARPETA_ENTRADA_USUARIOS, no aquí.
CARPETA_ENTRADA = RAIZ / "datos" / "entrada"

# Con registro público, cada cuenta genera y ve SU PROPIO conjunto de
# datos de ejemplo (no uno compartido): cada usuario_id tiene su propia
# subcarpeta, tanto para lo que sube el botón "Generar datos de ejemplo"
# como para lo que produce "Exportar CSV". Evita además que dos personas
# generando datos casi al mismo tiempo (Starlette corre las rutas
# síncronas en threads distintos) se pisen escribiendo el mismo archivo.
CARPETA_ENTRADA_USUARIOS = RAIZ / "datos" / "entrada_usuarios"
CARPETA_SALIDA_USUARIOS = RAIZ / "datos" / "salida_usuarios"

# El botón genera una versión reducida (no la escala completa que usa
# `python generador/datos_demo.py` por defecto): en Azure, cada inserción
# es un viaje de red hacia Aiven (otra nube, otra región), y con la
# escala completa la generación tarda varios minutos. A esta escala se
# ven los mismos problemas de calidad (los genera el generador de forma
# proporcional a cualquier tamaño), pero en segundos en vez de minutos.
ESCALA_DEMO_WEB = 0.2

# Nombres de archivo exactos que espera el pipeline (ver proceso/fuentes.py).
# La carga de archivos propios exige los 6 completos: es más simple de
# razonar y de validar que una carga parcial, y evita al usuario
# preguntarse por qué el tablero salió "incompleto" sin avisarle por qué.
ARCHIVOS_ESPERADOS = {fuente["archivo"] for fuente in FUENTES}

# Tope por archivo para la carga propia: es un endpoint público (cualquier
# cuenta registrada puede usarlo), así que conviene un límite explícito en
# vez de confiar solo en el disco efímero del contenedor. 50 MB (subido
# desde 25 MB) para que quepan los archivos generados con
# datos_demo.py a una escala más alta que la que usa el botón de datos
# de ejemplo (ESCALA_DEMO_WEB, arriba) sin acercarse al límite real de
# memoria del contenedor: en el peor caso son 6 archivos a la vez
# (~300 MB), que sigue siendo holgado para el tamaño de instancia con el
# que corre este proyecto.
TAMANO_MAXIMO_ARCHIVO_BYTES = 50 * 1024 * 1024


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    # Los navegadores lo piden en la raíz aunque la página declare otro ícono.
    return FileResponse(RAIZ / "web" / "static" / "iconos" / "favicon.ico")


@app.get("/")
def inicio(request: Request, sesion: dict | None = Depends(sesion_opcional)):
    # La portada de acceso es la primera pantalla; con sesión abierta se
    # va directo al tablero.
    if sesion:
        return RedirectResponse(url="/tablero", status_code=303)
    return plantillas.TemplateResponse(request, "login.html", {"error": None})


@app.get("/registro")
def formulario_registro(request: Request, error: str | None = None):
    return plantillas.TemplateResponse(request, "registro.html", {"error": error})


@app.post("/registro")
def procesar_registro(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    confirmar: str = Form(...),
):
    """Registro público y libre: cualquiera puede crear una cuenta, sin
    aprobación previa. Queda logueado de una vez (mismo patrón que
    /login), con una cuenta nueva y vacía — su propio usuario_id, sin
    ningún dato de ejemplo generado todavía."""
    email_normalizado = email.strip().lower()

    if password != confirmar:
        return plantillas.TemplateResponse(
            request,
            "registro.html",
            {"error": "Las contraseñas no coinciden"},
            status_code=400,
        )

    try:
        password_hash = hashear_password(password)
    except ValueError as error:
        return plantillas.TemplateResponse(
            request,
            "registro.html",
            {"error": str(error)},
            status_code=400,
        )

    conexion = conectar(salir=False)
    try:
        # La tabla `usuarios` la crea normalmente scripts/crear_admin.py,
        # pero con registro público el primer visitante puede llegar antes
        # de que alguien la haya corrido a mano. CREATE TABLE IF NOT
        # EXISTS: no hace nada si ya existe. A propósito NO se hace esto
        # en un evento de arranque de la app: eso bloquearía el arranque
        # entero a que la base responda (Aiven puede tardar en despertar
        # si estaba dormida), y Azure Container Apps mata la revisión por
        # no volverse "Ready" a tiempo. Aquí, en cambio, ya hay una
        # conexión abierta para la propia solicitud de registro.
        esquema.crear(conexion, RAIZ / "sql" / "05_usuarios.sql")

        cursor = conexion.cursor()
        try:
            cursor.execute(
                "INSERT INTO usuarios (email, password_hash) VALUES (%s, %s)",
                (email_normalizado, password_hash),
            )
            conexion.commit()
            usuario_id = cursor.lastrowid
        except pymysql.err.IntegrityError:
            # email UNIQUE: ya existe una cuenta con ese correo.
            return plantillas.TemplateResponse(
                request,
                "registro.html",
                {"error": "Ya existe una cuenta con ese correo"},
                status_code=409,
            )
        finally:
            cursor.close()
    finally:
        conexion.close()

    token = crear_token(usuario_id, email_normalizado)
    respuesta = RedirectResponse(url="/tablero", status_code=303)
    respuesta.set_cookie(NOMBRE_COOKIE, token, httponly=True, samesite="lax", max_age=8 * 3600)
    return respuesta


@app.get("/login")
def formulario_login(request: Request, error: str | None = None):
    return plantillas.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
def procesar_login(request: Request, email: str = Form(...), password: str = Form(...)):
    email_normalizado = email.strip().lower()

    conexion = conectar(salir=False)
    try:
        cursor = conexion.cursor()
        cursor.execute(
            "SELECT id, password_hash FROM usuarios WHERE email = %s", (email_normalizado,)
        )
        fila = cursor.fetchone()
        cursor.close()
    finally:
        conexion.close()

    if fila is None or not verificar_password(password, fila[1]):
        return plantillas.TemplateResponse(
            request,
            "login.html",
            {"error": "Correo o contraseña incorrectos"},
            status_code=401,
        )

    usuario_id = fila[0]
    token = crear_token(usuario_id, email_normalizado)
    respuesta = RedirectResponse(url="/tablero", status_code=303)
    respuesta.set_cookie(NOMBRE_COOKIE, token, httponly=True, samesite="lax", max_age=8 * 3600)
    return respuesta


@app.post("/logout")
def logout():
    respuesta = RedirectResponse(url="/", status_code=303)
    respuesta.delete_cookie(NOMBRE_COOKIE)
    return respuesta


@app.get("/tablero")
def tablero(request: Request, sesion: dict = Depends(requiere_sesion), error: str | None = None):
    usuario_id = sesion["usuario_id"]
    conexion = conectar(salir=False)
    try:
        datos = tablero_datos.consultar(conexion, usuario_id)
    finally:
        conexion.close()

    return plantillas.TemplateResponse(
        request,
        "tablero.html",
        {
            "email": sesion["email"],
            "datos": datos,
            "hay_datos": tablero_datos.hay_datos(datos),
            "escenario": tablero_datos.leer_escenario(CARPETA_ENTRADA_USUARIOS / str(usuario_id)),
            "error": error,
        },
    )


@app.post("/tablero/generar-demo")
def generar_demo(sesion: dict = Depends(requiere_sesion)):
    """Un clic: genera un conjunto nuevo de datos sintéticos SOLO para
    esta cuenta, en su propia subcarpeta de datos/entrada_usuarios/, y
    encadena el mismo pipeline de `setup.py` (esquema, carga,
    homologación y consolidado) acotado a su usuario_id. Pensado para
    explorar el proyecto sin depender de archivos reales ni de la
    terminal, y sin tocar los datos de ninguna otra cuenta.

    Cada clic sortea semilla y escenario (volumen por canal, periodo,
    duplicidad, rechazos y calidad), para que cada generación cuente una
    historia distinta — a diferencia de `python generador/datos_demo.py`,
    que por defecto es reproducible.
    """
    usuario_id = sesion["usuario_id"]
    carpeta = CARPETA_ENTRADA_USUARIOS / str(usuario_id)

    semilla = random.randint(1, 1_000_000)
    escenario = datos_demo.escenario_aleatorio(random.Random(semilla))
    datos_demo.generar(escala=ESCALA_DEMO_WEB, semilla=semilla, carpeta=carpeta, escenario=escenario)
    tablero_datos.guardar_escenario(carpeta, escenario.resumen())

    conexion = conectar(salir=False)
    try:
        pipeline.ejecutar(conexion, carpeta, usuario_id)
    finally:
        conexion.close()

    return RedirectResponse(url="/tablero", status_code=303)


@app.post("/tablero/cargar-propios")
async def cargar_propios(
    sesion: dict = Depends(requiere_sesion),
    archivos: list[UploadFile] = File(...),
):
    """Alternativa al botón de datos de ejemplo: si el usuario ya tiene
    sus propios archivos de origen, los sube directamente en vez de usar
    datos sintéticos, y se les aplica el mismo pipeline (esquema, carga,
    homologación, consolidado) acotado a su cuenta.

    Exige los 6 archivos completos con sus nombres exactos (ver
    proceso/fuentes.py) — no se admite una carga parcial: es más simple
    de razonar y evita que el usuario vea un tablero "incompleto" sin
    entender por qué. Cada archivo tiene además un tope de tamaño: es un
    endpoint público, cualquier cuenta registrada puede usarlo.
    """
    usuario_id = sesion["usuario_id"]
    carpeta = CARPETA_ENTRADA_USUARIOS / str(usuario_id)

    recibidos = {archivo.filename for archivo in archivos if archivo.filename}
    faltantes = ARCHIVOS_ESPERADOS - recibidos
    sobrantes = recibidos - ARCHIVOS_ESPERADOS

    if faltantes or sobrantes:
        partes = []
        if faltantes:
            partes.append("faltan: " + ", ".join(sorted(faltantes)))
        if sobrantes:
            partes.append("no se esperaban: " + ", ".join(sorted(sobrantes)))
        mensaje = (
            "Sube los 6 archivos exactos que pide el proyecto ("
            + ", ".join(sorted(ARCHIVOS_ESPERADOS))
            + "). " + "; ".join(partes) + "."
        )
        return RedirectResponse(url=f"/tablero?error={quote(mensaje)}", status_code=303)

    contenidos: dict[str, bytes] = {}
    for archivo in archivos:
        cuerpo = await archivo.read()
        if len(cuerpo) > TAMANO_MAXIMO_ARCHIVO_BYTES:
            mensaje = (
                f"{archivo.filename} pesa más del máximo permitido "
                f"({TAMANO_MAXIMO_ARCHIVO_BYTES // (1024 * 1024)} MB)."
            )
            return RedirectResponse(url=f"/tablero?error={quote(mensaje)}", status_code=303)
        contenidos[archivo.filename] = cuerpo

    carpeta.mkdir(parents=True, exist_ok=True)
    for nombre, cuerpo in contenidos.items():
        (carpeta / nombre).write_bytes(cuerpo)
    # Datos propios: el tablero ya no debe contar un escenario de ejemplo.
    tablero_datos.borrar_escenario(carpeta)

    conexion = conectar(salir=False)
    try:
        pipeline.ejecutar(conexion, carpeta, usuario_id)
    finally:
        conexion.close()

    return RedirectResponse(url="/tablero", status_code=303)


@app.get("/tablero/exportar-excel")
def exportar_excel_dinamico(sesion: dict = Depends(requiere_sesion)):
    """Libro de Excel con el consolidado de ESTA cuenta en el modelo de
    datos, medidas DAX y tablas dinámicas (ver web/exportar_excel.py)."""
    conexion = conectar(salir=False)
    try:
        contenido = exportar_excel.exportar(conexion, sesion["usuario_id"])
    finally:
        conexion.close()

    return Response(
        contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="calidad_afiliaciones.xlsx"'},
    )


@app.get("/tablero/exportar")
def exportar_consolidado(sesion: dict = Depends(requiere_sesion)):
    """Reexporta el consolidado de ESTA cuenta a CSV (misma lógica que
    `python setup.py --exportar`, acotada a su usuario_id) y lo entrega
    para descarga directa desde el navegador."""
    usuario_id = sesion["usuario_id"]
    carpeta = CARPETA_SALIDA_USUARIOS / str(usuario_id)

    conexion = conectar(salir=False)
    try:
        analisis.exportar(conexion, carpeta, usuario_id)
    finally:
        conexion.close()

    return FileResponse(
        carpeta / "consolidado.csv",
        media_type="text/csv",
        filename="consolidado.csv",
    )


# ── Recuperar y cambiar la contraseña ──────────────────────────────────────

_RESPUESTA_RECUPERAR = (
    "Si el correo pertenece a una cuenta, te enviamos un enlace para crear una contraseña nueva. "
    "Revisa tu bandeja (y la carpeta de spam)."
)
_ENVIOS: dict[str, list[float]] = {}
_CANDADO = threading.Lock()
LARGO_MINIMO = 8


def _puede_enviar(email: str) -> bool:
    """Máximo 3 enlaces cada 15 minutos por correo (no bloquea el ingreso)."""
    ahora = time.time()
    with _CANDADO:
        recientes = [t for t in _ENVIOS.get(email, []) if ahora - t < 15 * 60]
        _ENVIOS[email] = recientes if len(recientes) >= 3 else recientes + [ahora]
        return len(recientes) < 3


def _usuario(campo: str, valor) -> tuple | None:
    conexion = conectar(salir=False)
    try:
        cursor = conexion.cursor()
        cursor.execute(f"SELECT id, email, password_hash FROM usuarios WHERE {campo} = %s", (valor,))
        fila = cursor.fetchone()
        cursor.close()
        return fila
    finally:
        conexion.close()


def _guardar_password(usuario_id: int, password_hash: str) -> None:
    conexion = conectar(salir=False)
    try:
        cursor = conexion.cursor()
        cursor.execute("UPDATE usuarios SET password_hash = %s WHERE id = %s", (password_hash, usuario_id))
        conexion.commit()
        cursor.close()
    finally:
        conexion.close()


def _validar_nueva(password: str, confirmacion: str) -> tuple[str | None, str | None]:
    if password != confirmacion:
        return "La confirmación no coincide", None
    if len(password) < LARGO_MINIMO:
        return f"La contraseña debe tener al menos {LARGO_MINIMO} caracteres", None
    try:
        return None, hashear_password(password)
    except ValueError as error:
        return str(error), None


@app.get("/recuperar")
def formulario_recuperar(request: Request):
    return plantillas.TemplateResponse(request, "recuperar.html", {})


@app.post("/recuperar")
def procesar_recuperar(request: Request, email: str = Form(...)):
    email = email.strip().lower()
    fila = _usuario("email", email)
    if fila is not None and _puede_enviar(email):
        enlace = f"{correo.URL_PUBLICA}/restablecer?token={crear_token_recuperacion(fila[0], fila[2])}"
        correo.enviar(
            fila[1], "", "Restablece tu contraseña · Calidad de Afiliaciones",
            f"Hola,\n\nPara crear una contraseña nueva abre este enlace (vence en {RECUPERAR_MINUTOS} "
            f"minutos y sirve una vez):\n\n{enlace}\n\nSi no fuiste tú, ignora este correo: tu contraseña no cambia.",
            "<p>Hola,</p><p>Para crear una contraseña nueva en <strong>Calidad de Afiliaciones</strong>:</p>"
            f'<p><a href="{html.escape(enlace)}" style="background:#F29111;color:#1a1a1a;padding:10px 18px;border-radius:6px;'
            f'text-decoration:none">Crear contraseña nueva</a></p><p>El enlace vence en {RECUPERAR_MINUTOS} '
            "minutos y sirve una sola vez. Si no fuiste tú, ignora este correo.</p>",
        )
    return plantillas.TemplateResponse(request, "recuperar.html", {"exito": _RESPUESTA_RECUPERAR})


@app.get("/restablecer")
def formulario_restablecer(request: Request, token: str = ""):
    error = None if leer_token_recuperacion(token) else "El enlace no es válido o ya venció. Pide uno nuevo."
    return plantillas.TemplateResponse(request, "restablecer.html", {"token": token, "error": error})


@app.post("/restablecer")
def procesar_restablecer(
    request: Request, token: str = Form(...), password: str = Form(...), confirmacion: str = Form(...)
):
    leido = leer_token_recuperacion(token)
    fila = _usuario("id", leido[0]) if leido else None
    if fila is None or not huella_coincide(fila[2], leido[1]):
        error, nuevo = "El enlace no es válido o ya venció. Pide uno nuevo.", None
    else:
        error, nuevo = _validar_nueva(password, confirmacion)
    if error:
        return plantillas.TemplateResponse(
            request, "restablecer.html", {"token": token, "error": error}, status_code=400
        )
    _guardar_password(fila[0], nuevo)
    return plantillas.TemplateResponse(
        request, "login.html", {"exito": "Tu contraseña quedó actualizada. Ya puedes ingresar."}
    )


@app.get("/cuenta/contrasena")
def formulario_cambiar_contrasena(request: Request, sesion: dict | None = Depends(sesion_opcional)):
    if sesion is None:
        return RedirectResponse(url="/login", status_code=303)
    return plantillas.TemplateResponse(request, "cuenta_contrasena.html", {"sesion": sesion, "email": sesion["email"]})


@app.post("/cuenta/contrasena")
def cambiar_contrasena(
    request: Request,
    actual: str = Form(...),
    password: str = Form(...),
    confirmacion: str = Form(...),
    sesion: dict | None = Depends(sesion_opcional),
):
    if sesion is None:
        return RedirectResponse(url="/login", status_code=303)
    fila = _usuario("id", sesion["usuario_id"])
    if fila is None or not verificar_password(actual, fila[2]):
        error, nuevo = "La contraseña actual no es correcta", None
    elif password == actual:
        error, nuevo = "La contraseña nueva debe ser distinta de la actual", None
    else:
        error, nuevo = _validar_nueva(password, confirmacion)
    if error:
        return plantillas.TemplateResponse(
            request, "cuenta_contrasena.html", {"sesion": sesion, "email": sesion["email"], "error": error}, status_code=400
        )
    _guardar_password(fila[0], nuevo)
    return plantillas.TemplateResponse(
        request, "cuenta_contrasena.html", {"sesion": sesion, "email": sesion["email"], "exito": "Tu contraseña quedó actualizada."}
    )
