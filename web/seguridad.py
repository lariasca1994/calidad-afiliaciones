import datetime
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


def crear_token(email: str) -> str:
    payload = {
        "sub": email,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=JWT_HORAS_VALIDEZ),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITMO)


def _decodificar_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITMO])
        return payload["sub"]
    except jwt.PyJWTError:
        return None


def email_opcional(request: Request) -> str | None:
    """Para páginas públicas: da el email si hay sesión, o None sin fallar."""
    token = request.cookies.get(NOMBRE_COOKIE)
    if not token:
        return None
    return _decodificar_token(token)


def requiere_sesion(email: str | None = Depends(email_opcional)) -> str:
    """Para el tablero: exige sesión válida o corta con 401."""
    if email is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No autenticado")
    return email
