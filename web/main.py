import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pymysql
from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from generador import datos_demo
from proceso import analisis, esquema, pipeline
from proceso.conexion import conectar
from web.seguridad import (
    NOMBRE_COOKIE,
    crear_token,
    hashear_password,
    requiere_sesion,
    sesion_opcional,
    verificar_password,
)

app = FastAPI(title="Calidad de Afiliaciones")
app.mount("/static", StaticFiles(directory="web/static"), name="static")
plantillas = Jinja2Templates(directory="web/templates")

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


@app.on_event("startup")
def _asegurar_tabla_usuarios() -> None:
    """La tabla `usuarios` la crea normalmente scripts/crear_admin.py,
    pero con registro público el primer visitante puede llegar antes de
    que alguien la haya corrido a mano. CREATE TABLE IF NOT EXISTS: no
    hace nada si ya existe, así que es seguro repetirlo en cada arranque."""
    conexion = conectar()
    try:
        esquema.crear(conexion, RAIZ / "sql" / "05_usuarios.sql")
    finally:
        conexion.close()


@app.get("/")
def inicio(request: Request, sesion: dict | None = Depends(sesion_opcional)):
    email = sesion["email"] if sesion else None
    return plantillas.TemplateResponse(request, "inicio.html", {"email": email})


@app.get("/registro")
def formulario_registro(request: Request, error: str | None = None):
    return plantillas.TemplateResponse(request, "registro.html", {"error": error, "centrar": True})


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
            {"error": "Las contraseñas no coinciden", "centrar": True},
            status_code=400,
        )

    try:
        password_hash = hashear_password(password)
    except ValueError as error:
        return plantillas.TemplateResponse(
            request,
            "registro.html",
            {"error": str(error), "centrar": True},
            status_code=400,
        )

    conexion = conectar()
    try:
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
                {"error": "Ya existe una cuenta con ese correo", "centrar": True},
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
    return plantillas.TemplateResponse(request, "login.html", {"error": error, "centrar": True})


@app.post("/login")
def procesar_login(request: Request, email: str = Form(...), password: str = Form(...)):
    email_normalizado = email.strip().lower()

    conexion = conectar()
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
            {"error": "Correo o contraseña incorrectos", "centrar": True},
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
def tablero(request: Request, sesion: dict = Depends(requiere_sesion)):
    conexion = conectar()
    try:
        secciones = {}
        for clave, consulta in analisis.CONSULTAS.items():
            cursor = conexion.cursor()
            cursor.execute(consulta, {"usuario_id": sesion["usuario_id"]})
            columnas = [d[0] for d in cursor.description]
            filas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
            cursor.close()
            secciones[clave] = {"columnas": columnas, "filas": filas}
    finally:
        conexion.close()

    return plantillas.TemplateResponse(
        request, "tablero.html", {"email": sesion["email"], "secciones": secciones}
    )


@app.post("/tablero/generar-demo")
def generar_demo(sesion: dict = Depends(requiere_sesion)):
    """Un clic: genera un conjunto nuevo de datos sintéticos SOLO para
    esta cuenta, en su propia subcarpeta de datos/entrada_usuarios/, y
    encadena el mismo pipeline de `setup.py` (esquema, carga,
    homologación y consolidado) acotado a su usuario_id. Pensado para
    explorar el proyecto sin depender de archivos reales ni de la
    terminal, y sin tocar los datos de ninguna otra cuenta.

    Semilla aleatoria en cada clic (no fija), para que cada generación se
    vea distinta — a diferencia de `python generador/datos_demo.py`, que
    por defecto es reproducible.
    """
    usuario_id = sesion["usuario_id"]
    carpeta = CARPETA_ENTRADA_USUARIOS / str(usuario_id)

    semilla = random.randint(1, 1_000_000)
    datos_demo.generar(escala=1.0, semilla=semilla, carpeta=carpeta)

    conexion = conectar()
    try:
        pipeline.ejecutar(conexion, carpeta, usuario_id)
    finally:
        conexion.close()

    return RedirectResponse(url="/tablero", status_code=303)


@app.get("/tablero/exportar")
def exportar_consolidado(sesion: dict = Depends(requiere_sesion)):
    """Reexporta el consolidado de ESTA cuenta a CSV (misma lógica que
    `python setup.py --exportar`, acotada a su usuario_id) y lo entrega
    para descarga directa desde el navegador."""
    usuario_id = sesion["usuario_id"]
    carpeta = CARPETA_SALIDA_USUARIOS / str(usuario_id)

    conexion = conectar()
    try:
        analisis.exportar(conexion, carpeta, usuario_id)
    finally:
        conexion.close()

    return FileResponse(
        carpeta / "consolidado.csv",
        media_type="text/csv",
        filename="consolidado.csv",
    )
