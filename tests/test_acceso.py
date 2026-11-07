import re
import time

import jwt
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from web import correo, mfa, seguridad
from web.seguridad import COOKIE_MFA, NOMBRE_COOKIE

EMAIL = "usuario@ejemplo.com"
CLAVE = "clave-original-123"
SECRETO_VIEJO = "JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"


def _cuenta_con_app(base):
    return base.crear(EMAIL, CLAVE, {"totp": mfa._cifrar(SECRETO_VIEJO), "preferido": "totp"})


def _codigo(secreto: str) -> str:
    return mfa._totp(secreto, int(time.time()) // 30)


def _entrar_hasta_segundo_paso(cliente):
    respuesta = cliente.post("/login", data={"email": EMAIL, "password": CLAVE})
    assert respuesta.status_code == 303 and respuesta.headers["location"] == "/verificacion"


def _ultimo_codigo(base) -> str:
    return re.search(r"\b(\d{6})\b", base.correos[-1]["texto"]).group(1)


def _enlace(base) -> str:
    return re.search(r"token=([\w.-]+)", base.correos[-1]["texto"]).group(1)


# ── Olvidé mi contraseña ───────────────────────────────────────────────────


def test_recuperar_responde_igual_exista_o_no_la_cuenta(cliente, base):
    _cuenta_con_app(base)
    existe = cliente.post("/recuperar", data={"email": EMAIL})
    no_existe = cliente.post("/recuperar", data={"email": "nadie@ejemplo.com"})
    assert existe.status_code == no_existe.status_code == 200
    mensaje = "Si el correo pertenece a una cuenta"
    assert mensaje in existe.text and mensaje in no_existe.text
    assert [c["destino"] for c in base.correos] == [EMAIL]


def test_enlace_sirve_una_sola_vez_y_solo_pide_nueva_y_confirmacion(cliente, base):
    _cuenta_con_app(base)
    cliente.post("/recuperar", data={"email": EMAIL})
    token = _enlace(base)

    formulario = cliente.get(f"/restablecer?token={token}")
    assert formulario.status_code == 200
    campos = set(re.findall(r'<input[^>]*name="(\w+)"', formulario.text))
    assert campos == {"token", "password", "confirmacion"}

    nueva = {"token": token, "password": "clave-nueva-456", "confirmacion": "clave-nueva-456"}
    assert cliente.post("/restablecer", data=nueva).status_code == 200
    # Segunda vez con el mismo enlace: ya no sirve, ni para abrir el formulario.
    assert cliente.post("/restablecer", data={**nueva, "password": "otra-clave-789",
                                              "confirmacion": "otra-clave-789"}).status_code == 400
    usado = cliente.get(f"/restablecer?token={token}")
    assert usado.status_code == 400 and 'name="password"' not in usado.text
    assert seguridad.verificar_password("clave-nueva-456", base.cuentas[1]["password_hash"])


def test_enlace_vencido_no_sirve(cliente, base):
    cuenta = _cuenta_con_app(base)
    vencido = jwt.encode(
        {"sub": "1", "h": seguridad._huella(cuenta["password_hash"]), "aud": "recuperar",
         "exp": int(time.time()) - 60},
        seguridad.JWT_SECRET, algorithm="HS256",
    )
    assert cliente.get(f"/restablecer?token={vencido}").status_code == 400
    respuesta = cliente.post("/restablecer", data={"token": vencido, "password": "clave-nueva-456",
                                                   "confirmacion": "clave-nueva-456"})
    assert respuesta.status_code == 400


def test_restablecer_cierra_sesiones_y_mantiene_la_verificacion(cliente, base):
    cuenta = _cuenta_con_app(base)
    estado_mfa = dict(cuenta["mfa"])
    sesion_vieja = seguridad.crear_token(1, EMAIL, cuenta["password_hash"])
    cliente.cookies.set(NOMBRE_COOKIE, sesion_vieja)
    assert cliente.get("/cuenta/contrasena").status_code == 200

    cliente.post("/recuperar", data={"email": EMAIL})
    cliente.post("/restablecer", data={"token": _enlace(base), "password": "clave-nueva-456",
                                       "confirmacion": "clave-nueva-456"})

    cliente.cookies.clear()
    cliente.cookies.set(NOMBRE_COOKIE, sesion_vieja)
    assert cliente.get("/cuenta/contrasena").headers.get("location") == "/login"
    assert base.cuentas[1]["mfa"]["totp"] == estado_mfa["totp"]
    # Con la clave nueva vuelve a pedir el segundo paso de siempre.
    respuesta = cliente.post("/login", data={"email": EMAIL, "password": "clave-nueva-456"})
    assert respuesta.headers["location"] == "/verificacion"
    assert "Escribe tu código" in cliente.get("/verificacion").text


def test_cambiar_contrasena_cierra_las_demas_sesiones(cliente, base):
    cuenta = _cuenta_con_app(base)
    otra_sesion = seguridad.crear_token(1, EMAIL, cuenta["password_hash"])
    cliente.cookies.set(NOMBRE_COOKIE, otra_sesion)
    respuesta = cliente.post("/cuenta/contrasena", data={"actual": CLAVE, "password": "clave-nueva-456",
                                                         "confirmacion": "clave-nueva-456"})
    assert respuesta.status_code == 200
    assert cliente.get("/cuenta/contrasena").status_code == 200  # esta sesión sigue
    cliente.cookies.clear()
    cliente.cookies.set(NOMBRE_COOKIE, otra_sesion)
    assert cliente.get("/cuenta/contrasena").status_code == 303  # la otra quedó cerrada


def test_pase_del_segundo_paso_muere_si_cambia_la_contrasena(cliente, base):
    _cuenta_con_app(base)
    _entrar_hasta_segundo_paso(cliente)
    base.cuentas[1]["password_hash"] = seguridad.hashear_password("clave-nueva-456")
    assert cliente.get("/verificacion").headers.get("location") == "/login"


# ── Perdí mi autenticador ──────────────────────────────────────────────────


def test_enlace_perdi_mi_autenticador_siempre_visible(cliente, base):
    _cuenta_con_app(base)
    _entrar_hasta_segundo_paso(cliente)
    assert "Perdí mi autenticador" in cliente.get("/verificacion").text
    assert "Perdí mi autenticador" in cliente.get("/verificacion?metodo=correo").text


def test_codigo_llega_al_correo_aunque_el_metodo_correo_no_este_activo(cliente, base):
    _cuenta_con_app(base)
    _entrar_hasta_segundo_paso(cliente)
    assert "correo" not in mfa.metodos_activos(base.cuentas[1])
    respuesta = cliente.post("/verificacion/perdi-autenticador")
    assert respuesta.status_code == 200 and "Revisa tu correo" in respuesta.text
    assert base.correos[-1]["destino"] == EMAIL
    assert "15 minutos" in base.correos[-1]["texto"]


def test_recuperar_autenticador_obliga_a_configurar_la_app_nueva(cliente, base):
    _cuenta_con_app(base)
    _entrar_hasta_segundo_paso(cliente)
    cliente.post("/verificacion/perdi-autenticador")
    respuesta = cliente.post("/verificacion/perdi-autenticador/verificar", data={"codigo": _ultimo_codigo(base)})
    assert respuesta.status_code == 303 and respuesta.headers["location"] == "/verificacion"
    assert NOMBRE_COOKIE not in cliente.cookies  # todavía no hay sesión

    pantalla = cliente.get("/verificacion")
    assert "Configura tu nueva app autenticadora" in pantalla.text and "<svg" in pantalla.text
    secreto_nuevo = re.search(r'class="mfa-clave">(\w+)<', pantalla.text).group(1)

    # Con el pase de recuperación no se puede saltar la app nueva.
    saltar = cliente.post("/verificacion", data={"metodo": "totp", "codigo": _codigo(SECRETO_VIEJO)})
    assert saltar.headers["location"] == "/verificacion" and NOMBRE_COOKIE not in cliente.cookies
    otro = cliente.post("/verificacion/configurar", data={"metodo": "correo"})
    assert otro.headers["location"] == "/verificacion"

    entrar = cliente.post("/verificacion/activar", data={"metodo": "totp", "codigo": _codigo(secreto_nuevo)})
    assert entrar.status_code == 303 and entrar.headers["location"] == "/tablero"
    assert NOMBRE_COOKIE in cliente.cookies and COOKIE_MFA not in cliente.cookies
    guardado = base.cuentas[1]["mfa"]
    assert mfa._descifrar(guardado["totp"]) == secreto_nuevo and guardado["preferido"] == "totp"


def test_codigo_de_recuperacion_vence_en_15_minutos(cliente, base, monkeypatch):
    _cuenta_con_app(base)
    _entrar_hasta_segundo_paso(cliente)
    cliente.post("/verificacion/perdi-autenticador")
    codigo = _ultimo_codigo(base)
    ahora = time.time()
    monkeypatch.setattr(mfa.time, "time", lambda: ahora + 15 * 60 + 1)
    assert not mfa.verificar_recuperacion(base.cargar("id", 1), codigo)


def test_limite_de_envios(cliente, base):
    _cuenta_con_app(base)
    _entrar_hasta_segundo_paso(cliente)
    for _ in range(3):
        assert cliente.post("/verificacion/perdi-autenticador").status_code == 200
    cuarto = cliente.post("/verificacion/perdi-autenticador")
    assert cuarto.status_code == 429 and len(base.correos) == 3


def test_cinco_codigos_errados_bloquean_15_minutos(cliente, base):
    _cuenta_con_app(base)
    _entrar_hasta_segundo_paso(cliente)
    cliente.post("/verificacion/perdi-autenticador")
    bueno = _ultimo_codigo(base)
    malo = "000000" if bueno != "000000" else "111111"
    for _ in range(5):
        respuesta = cliente.post("/verificacion/perdi-autenticador/verificar", data={"codigo": malo})
        assert respuesta.status_code == 401
    assert "Demasiados códigos errados" in respuesta.text
    # Bloqueado: ni el código correcto ni un envío nuevo.
    assert cliente.post("/verificacion/perdi-autenticador/verificar", data={"codigo": bueno}).status_code == 401
    assert cliente.post("/verificacion/perdi-autenticador").status_code == 429

    bloqueo = base.cuentas[1]["mfa"]["recup_bloqueo_hasta"] - time.time()
    assert 14 * 60 < bloqueo <= 15 * 60
    base.cuentas[1]["mfa"]["recup_bloqueo_hasta"] = time.time() - 1  # pasaron los 15 minutos
    assert cliente.post("/verificacion/perdi-autenticador").status_code == 200


def test_sin_contrasena_no_hay_recuperacion_del_autenticador(cliente, base):
    _cuenta_con_app(base)
    assert cliente.post("/verificacion/perdi-autenticador").headers["location"] == "/login"
    assert base.correos == []


# ── Nombre visible ─────────────────────────────────────────────────────────

NOMBRE = "Calidad de afiliaciones"


def test_nombre_en_correos_y_emisor_del_qr(cliente, base):
    assert mfa.EMISOR == NOMBRE
    _cuenta_con_app(base)
    cliente.post("/recuperar", data={"email": EMAIL})
    _entrar_hasta_segundo_paso(cliente)
    cliente.post("/verificacion/perdi-autenticador")
    mfa.enviar_codigo(base.cargar("id", 1))
    for mensaje in base.correos:
        assert NOMBRE in mensaje["asunto"]
        assert NOMBRE in mensaje["html"] and "Calidad de Afiliaciones" not in mensaje["html"]
    assert "issuer=Calidad%20de%20afiliaciones" in _uri_qr(base)


def _uri_qr(base):
    capturado = {}
    original = mfa.segno.make

    def make(uri, **kwargs):
        capturado["uri"] = uri
        return original(uri, **kwargs)

    mfa.segno.make = make
    try:
        mfa.iniciar_totp(base.cargar("id", 1))
    finally:
        mfa.segno.make = original
    return capturado["uri"]


def test_remitente_con_el_nombre_visible(monkeypatch):
    enviado = {}

    class Respuesta:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def urlopen(pedido, timeout):
        enviado["cuerpo"] = pedido.data.decode()
        return Respuesta()

    monkeypatch.setattr(correo, "BREVO_API_KEY", "x")
    monkeypatch.setattr(correo, "BREVO_REMITENTE", "remitente@ejemplo.com")
    monkeypatch.setattr(correo.urllib.request, "urlopen", urlopen)
    assert correo.enviar("usuario@ejemplo.com", "", "Asunto", "texto", "<p>x</p>")
    assert f'"name": "{NOMBRE}"' in enviado["cuerpo"]


def test_paginas_con_el_nombre_visible(cliente, base):
    for ruta in ("/login", "/registro", "/recuperar"):
        texto = cliente.get(ruta).text
        assert NOMBRE in texto and "Calidad de Afiliaciones" not in texto


def test_clave_de_cifrado_totp_sin_cambios():
    # Los secretos ya guardados siguen descifrándose: la etiqueta interna no cambia.
    clave = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                 info=b"CalidadAfiliaciones.MFA.v1").derive(seguridad.JWT_SECRET.encode("utf-8"))
    assert mfa._clave == clave
