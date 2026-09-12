import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from generador import datos_demo
from proceso import analisis, pipeline
from proceso.conexion import conectar
from web.seguridad import (
    NOMBRE_COOKIE,
    crear_token,
    email_opcional,
    requiere_sesion,
    verificar_password,
)

app = FastAPI(title="Calidad de Afiliaciones")
app.mount("/static", StaticFiles(directory="web/static"), name="static")
plantillas = Jinja2Templates(directory="web/templates")

RAIZ = Path(__file__).resolve().parent.parent

# Misma carpeta que usa `python setup.py` al exportar — así el botón
# "Exportar CSV" del tablero y la exportación por consola producen
# siempre el mismo archivo, en el mismo sitio.
CARPETA_SALIDA = RAIZ / "datos" / "salida"

# Misma carpeta que lee `python setup.py` al cargar — el botón "Generar
# datos de ejemplo" escribe aquí y el pipeline lee de aquí mismo, sin
# pasar por la terminal.
CARPETA_ENTRADA = RAIZ / "datos" / "entrada"


@app.get("/")
def inicio(request: Request, email: str | None = Depends(email_opcional)):
    return plantillas.TemplateResponse(request, "inicio.html", {"email": email})


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
            "SELECT password_hash FROM usuarios WHERE email = %s", (email_normalizado,)
        )
        fila = cursor.fetchone()
        cursor.close()
    finally:
        conexion.close()

    if fila is None or not verificar_password(password, fila[0]):
        return plantillas.TemplateResponse(
            request,
            "login.html",
            {"error": "Correo o contraseña incorrectos", "centrar": True},
            status_code=401,
        )

    token = crear_token(email_normalizado)
    respuesta = RedirectResponse(url="/tablero", status_code=303)
    respuesta.set_cookie(NOMBRE_COOKIE, token, httponly=True, samesite="lax", max_age=8 * 3600)
    return respuesta


@app.post("/logout")
def logout():
    respuesta = RedirectResponse(url="/", status_code=303)
    respuesta.delete_cookie(NOMBRE_COOKIE)
    return respuesta


@app.get("/tablero")
def tablero(request: Request, email: str = Depends(requiere_sesion)):
    conexion = conectar()
    try:
        secciones = {}
        for clave, consulta in analisis.CONSULTAS.items():
            cursor = conexion.cursor()
            cursor.execute(consulta)
            columnas = [d[0] for d in cursor.description]
            filas = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]
            cursor.close()
            secciones[clave] = {"columnas": columnas, "filas": filas}
    finally:
        conexion.close()

    return plantillas.TemplateResponse(
        request, "tablero.html", {"email": email, "secciones": secciones}
    )


@app.post("/tablero/generar-demo")
def generar_demo(email: str = Depends(requiere_sesion)):
    """Un clic: genera un conjunto nuevo de datos sintéticos en
    datos/entrada (reemplazando lo que hubiera ahí), y encadena el mismo
    pipeline de `setup.py` (esquema, carga, homologación y consolidado)
    contra ese contenido. Pensado para explorar el proyecto sin depender
    de archivos reales ni de la terminal.

    Semilla aleatoria en cada clic (no fija), para que cada generación se
    vea distinta — a diferencia de `python generador/datos_demo.py`, que
    por defecto es reproducible.
    """
    semilla = random.randint(1, 1_000_000)
    datos_demo.generar(escala=1.0, semilla=semilla)

    conexion = conectar()
    try:
        pipeline.ejecutar(conexion, CARPETA_ENTRADA)
    finally:
        conexion.close()

    return RedirectResponse(url="/tablero", status_code=303)


@app.get("/tablero/exportar")
def exportar_consolidado(email: str = Depends(requiere_sesion)):
    """Reexporta el consolidado a CSV (misma lógica que `python setup.py`)
    y lo entrega para descarga directa desde el navegador."""
    conexion = conectar()
    try:
        analisis.exportar(conexion, CARPETA_SALIDA)
    finally:
        conexion.close()

    return FileResponse(
        CARPETA_SALIDA / "consolidado.csv",
        media_type="text/csv",
        filename="consolidado.csv",
    )
