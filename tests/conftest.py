"""Pruebas del acceso (recuperación de contraseña, "Perdí mi autenticador" y nombre
visible) sin base de datos ni correo reales: las cuentas viven en un diccionario
en memoria y los correos se guardan en una lista."""

import copy
import os
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
os.chdir(RAIZ)  # la app monta web/static y web/templates con rutas relativas
os.environ.setdefault("JWT_SECRET", "secreto-solo-para-pruebas")

from fastapi.testclient import TestClient  # noqa: E402

from web import auditoria, correo, main, mfa, seguridad  # noqa: E402


class BaseFalsa:
    def __init__(self):
        self.cuentas: dict[int, dict] = {}
        self.correos: list[dict] = []
        self.eventos: list[str] = []

    def crear(self, email: str, password: str, estado_mfa: dict | None = None) -> dict:
        nuevo_id = len(self.cuentas) + 1
        self.cuentas[nuevo_id] = {"id": nuevo_id, "email": email,
                                  "password_hash": seguridad.hashear_password(password),
                                  "mfa": estado_mfa or {}}
        return self.cuentas[nuevo_id]

    def cargar(self, campo, valor):
        for cuenta in self.cuentas.values():
            if cuenta[campo] == valor:
                return copy.deepcopy(cuenta)
        return None


def _sin_base(*_args, **_kwargs):
    raise AssertionError("Las pruebas no deben conectarse a la base")


@pytest.fixture
def base(monkeypatch):
    falsa = BaseFalsa()

    def guardar(usuario, cambios):
        usuario["mfa"] = {**mfa.estado(usuario), **cambios}
        falsa.cuentas[usuario["id"]]["mfa"] = copy.deepcopy(usuario["mfa"])

    def usuario_tupla(campo, valor):
        cuenta = falsa.cargar(campo, valor)
        return (cuenta["id"], cuenta["email"], cuenta["password_hash"]) if cuenta else None

    def guardar_password(usuario_id, password_hash):
        falsa.cuentas[usuario_id]["password_hash"] = password_hash

    def enviar(destino, nombre, asunto, texto, html):
        falsa.correos.append({"destino": destino, "asunto": asunto, "texto": texto,
                              "html": correo.documento(asunto, html)})
        return True

    monkeypatch.setattr(mfa, "conectar", _sin_base)
    monkeypatch.setattr(main, "conectar", _sin_base)
    monkeypatch.setattr(mfa, "cargar", falsa.cargar)
    monkeypatch.setattr(mfa, "_guardar", guardar)
    monkeypatch.setattr(main, "_usuario", usuario_tupla)
    monkeypatch.setattr(main, "_guardar_password", guardar_password)
    monkeypatch.setattr(seguridad, "hash_actual",
                        lambda i: falsa.cuentas[i]["password_hash"] if i in falsa.cuentas else None)
    monkeypatch.setattr(correo, "enviar", enviar)
    monkeypatch.setattr(auditoria, "registrar", lambda tipo, usuario: falsa.eventos.append(tipo))
    main._ENVIOS.clear()
    return falsa


@pytest.fixture
def cliente(base):
    return TestClient(main.app, follow_redirects=False)
