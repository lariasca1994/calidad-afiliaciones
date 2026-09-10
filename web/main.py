import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from proceso import analisis
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

# Misma carpeta que usa `python setup.py` al exportar — así el botón
# "Exportar CSV" del tablero y la exportación por consola producen
# siempre el mismo archivo, en el mismo sitio.
CARPETA_SALIDA = Path(__file__).resolve().parent.parent / "datos" / "salida"


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
