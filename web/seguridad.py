import datetime
import hashlib
import hmac
import os
from pathlib import Path

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext

# Se carga acá explícitamente, sin depender de que algún otro módulo
# (como proceso/conexion.py) se haya importado antes en el mismo
# proceso y ya lo haya hecho por su cuenta — evita un fallo silencioso
# si el orden de imports cambia en el futuro.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("Falta JWT_SECRET en el archivo .env")

JWT_ALGORITMO = "HS256"
JWT_HORAS_VALIDEZ = 8
NOMBRE_COOKIE = "sesion"

_contexto_password = CryptContext(schemes=["bcrypt"], deprecated="auto")

# bcrypt trunca (o rechaza, según versión) cualquier contraseña de más de
# 72 BYTES, no caracteres — una tilde, la ñ o un emoji ocupan 2 a 4 bytes
# en UTF-8. Se valida acá para un mensaje claro en vez de un traceback.
LARGO_MAXIMO_PASSWORD_BYTES = 72


def hashear_password(password: str) -> str:
    if len(password.encode("utf-8")) > LARGO_MAXIMO_PASSWORD_BYTES:
        raise ValueError(
            f"La contraseña no puede pesar más de {LARGO_MAXIMO_PASSWORD_BYTES} bytes "
            "(límite de bcrypt). Si usa tildes, ñ o emojis cuentan doble o más — "
            "prueba con una más corta."
        )
    return _contexto_password.hash(password)


def verificar_password(password: str, password_hash: str) -> bool:
    if len(password.encode("utf-8")) > LARGO_MAXIMO_PASSWORD_BYTES:
        return False
    return _contexto_password.verify(password, password_hash)


def crear_token(usuario_id: int, email: str, password_hash: str) -> str:
    """Con registro público de cuentas, el tablero y el pipeline necesitan
    saber DE QUIÉN son los datos que se consultan o generan (columna
    usuario_id en cada tabla — ver sql/01_esquema.sql), no solo si hay
    sesión. Por eso el token ahora lleva el id de la cuenta como `sub`
    (convertido a texto: el estándar JWT exige que `sub` sea un string) y
    el correo aparte, solo para mostrarlo en pantalla.

    Lleva además la huella de la contraseña: al cambiarla (o restablecerla)
    todas las sesiones abiertas con la anterior dejan de valer.
    """
    payload = {
        "sub": str(usuario_id),
        "email": email,
        "h": _huella(password_hash),
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_HORAS_VALIDEZ),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITMO)


# ── Recuperación de cuenta ─────────────────────────────────────────────────
# Enlace firmado, con vencimiento y de un solo uso: lleva la huella de la
# contraseña actual (al cambiarla deja de servir) y una audiencia propia, así
# que _decodificar_token (sesiones) lo rechaza.
_AUDIENCIA_RECUPERAR = "recuperar"
RECUPERAR_MINUTOS = 30


def _huella(password_hash: str) -> str:
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:24]


def crear_token_recuperacion(usuario_id: int, password_hash: str) -> str:
    return jwt.encode(
        {"sub": str(usuario_id), "h": _huella(password_hash), "aud": _AUDIENCIA_RECUPERAR,
         "exp": datetime.datetime.utcnow() + datetime.timedelta(minutes=RECUPERAR_MINUTOS)},
        JWT_SECRET, algorithm=JWT_ALGORITMO,
    )


def leer_token_recuperacion(token: str) -> tuple[int, str] | None:
    try:
        carga = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITMO], audience=_AUDIENCIA_RECUPERAR)
        return int(carga["sub"]), str(carga["h"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


_AUDIENCIA_MFA = "mfa"
COOKIE_MFA = "calidad_mfa"
MFA_MINUTOS = 10


def crear_token_mfa(usuario_id: int, password_hash: str, recuperacion: bool = False) -> str:
    """Pase de 10 minutos entre la contraseña y el código de la verificación en dos
    pasos. No sirve como sesión: _decodificar_token lo rechaza por llevar audiencia.
    Lleva la huella de la contraseña (si cambia, el pase muere) y, tras validar el
    código de "Perdí mi autenticador", la marca de recuperación: con ella solo se
    puede configurar la app autenticadora nueva."""
    carga = {"sub": str(usuario_id), "h": _huella(password_hash), "aud": _AUDIENCIA_MFA,
             "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=MFA_MINUTOS)}
    if recuperacion:
        carga["rec"] = True
    return jwt.encode(carga, JWT_SECRET, algorithm=JWT_ALGORITMO)


def leer_token_mfa(token: str | None) -> dict | None:
    """{"id", "h", "rec"} del pase, o None si no es válido o venció."""
    if not token:
        return None
    try:
        carga = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITMO], audience=_AUDIENCIA_MFA)
        return {"id": int(carga["sub"]), "h": str(carga["h"]), "rec": bool(carga.get("rec"))}
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def huella_coincide(password_hash: str, huella: str) -> bool:
    return hmac.compare_digest(_huella(password_hash), huella)


def _decodificar_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITMO])
        return {"usuario_id": int(payload["sub"]), "email": payload["email"], "h": str(payload["h"])}
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        # Cubre también tokens viejos (de antes del registro público) que
        # solo llevaban `sub` = email: no calzan con int(), y se tratan
        # como sesión inválida en vez de reventar con un 500. Las de antes de
        # la huella de contraseña ("h") también se rechazan: piden ingresar de nuevo.
        return None


def hash_actual(usuario_id: int) -> str | None:
    """Huella guardada hoy de la contraseña de la cuenta (None si no existe)."""
    from proceso.conexion import conectar  # aquí: evita cargar la base al importar

    conexion = conectar(salir=False)
    try:
        cursor = conexion.cursor()
        cursor.execute("SELECT password_hash FROM usuarios WHERE id = %s", (usuario_id,))
        fila = cursor.fetchone()
        cursor.close()
    finally:
        conexion.close()
    return fila[0] if fila else None


def sesion_opcional(request: Request) -> dict | None:
    """Para páginas públicas: da {"usuario_id", "email"} si hay sesión
    válida, o None sin fallar."""
    token = request.cookies.get(NOMBRE_COOKIE)
    if not token:
        return None
    sesion = _decodificar_token(token)
    if sesion is None:
        return None
    # Contraseña cambiada después de abrir la sesión: la sesión quedó cerrada.
    password_hash = hash_actual(sesion["usuario_id"])
    if password_hash is None or not huella_coincide(password_hash, sesion.pop("h")):
        return None
    return sesion


def requiere_sesion(sesion: dict | None = Depends(sesion_opcional)) -> dict:
    """Para el tablero y sus acciones: exige sesión válida o corta con 401."""
    if sesion is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    return sesion
