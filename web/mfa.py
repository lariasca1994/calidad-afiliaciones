"""Verificacion en dos pasos (obligatoria).

Cada cuenta usa al menos uno de dos metodos y puede tener ambos:

  - App autenticadora (TOTP, RFC 6238): codigo de 6 digitos que cambia cada
    30 s. El secreto se guarda cifrado con AES-GCM; la clave se deriva del
    JWT_SECRET con HKDF, asi que un volcado de la base no basta para
    generar codigos. Un mismo codigo no se acepta dos veces.
  - Codigo por correo: 6 digitos de un solo uso que vencen en 10 minutos.
    Solo se guarda su huella (HMAC) y admite 5 intentos; se pueden pedir
    hasta 3 envios cada 10 minutos. Tras 5 codigos de la app errados, la app
    queda bloqueada 15 minutos.

Todo vive en la columna JSON "mfa" de la tabla usuarios (MySQL); el usuario se
maneja como diccionario con id, email y mfa.
"""

import base64
import hashlib
import hmac
import html
import json
import secrets
import struct
import time
from urllib.parse import quote

import segno
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from proceso.conexion import conectar
from web import correo
from web.seguridad import JWT_SECRET

EMISOR = "Calidad de Afiliaciones"
METODOS = {"totp": "App autenticadora", "correo": "Código por correo"}
_PASO = 30
_CODIGO_MINUTOS = 10
_MAX_INTENTOS = 5
_MAX_ENVIOS = 3
_BLOQUEO_SEG = 15 * 60  # tras 5 códigos de la app errados

_clave = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"CalidadAfiliaciones.MFA.v1").derive(
    JWT_SECRET.encode("utf-8")
)


# ─────────────────────────────── utilidades ───────────────────────────────


def _cifrar(texto: str) -> str:
    nonce = secrets.token_bytes(12)
    return base64.b64encode(nonce + AESGCM(_clave).encrypt(nonce, texto.encode(), None)).decode()


def _descifrar(valor: str) -> str:
    datos = base64.b64decode(valor)
    return AESGCM(_clave).decrypt(datos[:12], datos[12:], None).decode()


def _huella(codigo: str) -> str:
    return hmac.new(_clave, codigo.encode(), hashlib.sha256).hexdigest()


def _totp(secreto: str, paso: int) -> str:
    clave = base64.b32decode(secreto + "=" * (-len(secreto) % 8))
    resumen = hmac.new(clave, struct.pack(">Q", paso), hashlib.sha1).digest()
    desfase = resumen[-1] & 0x0F
    numero = struct.unpack(">I", resumen[desfase:desfase + 4])[0] & 0x7FFFFFFF
    return f"{numero % 1_000_000:06d}"


def _limpiar(codigo: str) -> str:
    return "".join(c for c in (codigo or "") if c.isdigit())


def estado(usuario) -> dict:
    return dict(usuario.get("mfa") or {})


def metodos_activos(usuario) -> list[str]:
    m = estado(usuario)
    return [x for x in ("totp", "correo") if (x == "totp" and m.get("totp")) or (x == "correo" and m.get("correo"))]


def configurado(usuario) -> bool:
    return bool(metodos_activos(usuario))


def preferido(usuario) -> str | None:
    activos = metodos_activos(usuario)
    elegido = estado(usuario).get("preferido")
    return elegido if elegido in activos else (activos[0] if activos else None)


def _guardar(usuario, cambios: dict) -> None:
    usuario["mfa"] = {**estado(usuario), **cambios}
    conexion = conectar(salir=False)
    try:
        cursor = conexion.cursor()
        cursor.execute("UPDATE usuarios SET mfa = %s WHERE id = %s", (json.dumps(usuario["mfa"]), usuario["id"]))
        conexion.commit()
        cursor.close()
    finally:
        conexion.close()


def asegurar_columna(conexion) -> None:
    """Agrega la columna mfa si falta (una vez por proceso). No se hace al arrancar
    para no bloquear el arranque si la base está dormida."""
    global _columna_lista
    if _columna_lista:
        return
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s", ("usuarios", "mfa")
    )
    if cursor.fetchone()[0] == 0:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN mfa JSON NULL")
        conexion.commit()
    cursor.close()
    _columna_lista = True


_columna_lista = False


def cargar(campo: str, valor) -> dict | None:
    """Usuario como diccionario {id, email, password_hash, mfa} buscado por id o email."""
    conexion = conectar(salir=False)
    try:
        asegurar_columna(conexion)
        cursor = conexion.cursor()
        cursor.execute(f"SELECT id, email, password_hash, mfa FROM usuarios WHERE {campo} = %s", (valor,))
        fila = cursor.fetchone()
        cursor.close()
    finally:
        conexion.close()
    if fila is None:
        return None
    mfa = fila[3]
    return {"id": fila[0], "email": fila[1], "password_hash": fila[2],
            "mfa": json.loads(mfa) if isinstance(mfa, (str, bytes)) else (mfa or {})}


# ──────────────────────────── app autenticadora ───────────────────────────


def iniciar_totp(usuario) -> dict:
    """Genera un secreto pendiente y devuelve lo necesario para escanearlo."""
    secreto = base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")
    _guardar(usuario, {"totp_pendiente": _cifrar(secreto)})
    uri = (
        f"otpauth://totp/{quote(EMISOR)}:{quote(usuario["email"])}"
        f"?secret={secreto}&issuer={quote(EMISOR)}&digits=6&period={_PASO}"
    )
    return {"qr": segno.make(uri, error="m").svg_inline(scale=5, dark="#0f172a", light="#ffffff"), "secreto": secreto}


def _verificar_totp(usuario, secreto_cifrado: str | None, codigo: str) -> bool:
    if not secreto_cifrado or len(codigo) != 6:
        return False
    secreto = _descifrar(secreto_cifrado)
    actual = int(time.time()) // _PASO
    ultimo = estado(usuario).get("ultimo_paso", 0)
    for paso in (actual - 1, actual, actual + 1):
        if paso > ultimo and hmac.compare_digest(_totp(secreto, paso), codigo):
            _guardar(usuario, {"ultimo_paso": paso})
            return True
    return False


def activar_totp(usuario, codigo: str) -> bool:
    pendiente = estado(usuario).get("totp_pendiente")
    if not _verificar_totp(usuario, pendiente, _limpiar(codigo)):
        return False
    cambios = {"totp": pendiente, "totp_pendiente": None}
    if not configurado(usuario):
        cambios["preferido"] = "totp"
    _guardar(usuario, cambios)
    return True


# ──────────────────────────── codigo por correo ───────────────────────────


def enviar_codigo(usuario) -> bool:
    """Envia un codigo nuevo. False si ya se pidieron demasiados."""
    ahora = time.time()
    envios = [t for t in estado(usuario).get("envios", []) if ahora - t < _CODIGO_MINUTOS * 60]
    if len(envios) >= _MAX_ENVIOS:
        return False
    codigo = f"{secrets.randbelow(1_000_000):06d}"
    _guardar(usuario, {
        "codigo": {
            "huella": _huella(codigo),
            "expira": ahora + _CODIGO_MINUTOS * 60,
            "intentos": 0,
        },
        "envios": envios + [ahora],
    })
    nombre = ""
    correo.enviar(
        usuario["email"], nombre, f"Tu código de acceso · {EMISOR}",
        f"Hola,\n\nTu código de verificación de {EMISOR} es: {codigo}\n\n"
        f"Vence en {_CODIGO_MINUTOS} minutos y sirve una sola vez. Si no intentaste ingresar, "
        "cambia tu contraseña.",
        f"<p>Hola,</p><p>Tu código de verificación de <strong>{EMISOR}</strong> es:</p>"
        f'<p style="font-size:28px;font-weight:700;letter-spacing:6px">{codigo}</p>'
        f"<p>Vence en {_CODIGO_MINUTOS} minutos y sirve una sola vez. Si no intentaste ingresar, "
        "cambia tu contraseña.</p>",
    )
    return True


def _verificar_correo(usuario, codigo: str) -> bool:
    guardado = estado(usuario).get("codigo")
    if not guardado or guardado.get("intentos", 0) >= _MAX_INTENTOS:
        return False
    if guardado["expira"] < time.time():
        return False
    if not hmac.compare_digest(guardado["huella"], _huella(codigo)):
        _guardar(usuario, {"codigo": {**guardado, "intentos": guardado.get("intentos", 0) + 1}})
        return False
    _guardar(usuario, {"codigo": None})
    return True


def activar_correo(usuario, codigo: str) -> bool:
    if not _verificar_correo(usuario, _limpiar(codigo)):
        return False
    cambios = {"correo": True}
    if not configurado(usuario):
        cambios["preferido"] = "correo"
    _guardar(usuario, cambios)
    return True


# ─────────────────────────────── verificacion ──────────────────────────────


def verificar(usuario, metodo: str, codigo: str) -> bool:
    """Comprueba el codigo de un metodo ya activo."""
    codigo = _limpiar(codigo)
    if metodo not in metodos_activos(usuario):
        return False
    if metodo == "totp":
        # Sin este freno, con la contraseña bastaría probar códigos hasta acertar.
        if estado(usuario).get("bloqueo_hasta", 0) > time.time():
            return False
        if _verificar_totp(usuario, estado(usuario).get("totp"), codigo):
            if estado(usuario).get("fallos"):
                _guardar(usuario, {"fallos": 0})
            return True
        fallos = estado(usuario).get("fallos", 0) + 1
        _guardar(usuario, {"fallos": 0, "bloqueo_hasta": time.time() + _BLOQUEO_SEG}
                 if fallos >= _MAX_INTENTOS else {"fallos": fallos})
        return False
    return _verificar_correo(usuario, codigo)


def elegir_preferido(usuario, metodo: str) -> bool:
    if metodo not in metodos_activos(usuario):
        return False
    _guardar(usuario, {"preferido": metodo})
    return True
