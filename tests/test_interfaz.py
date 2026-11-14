"""Interfaz: menú lateral, aplicación instalable (PWA) y página 404 propia."""

from web import mfa, seguridad
from web.seguridad import NOMBRE_COOKIE

EMAIL = "usuario@ejemplo.com"
CLAVE = "clave-original-123"


def _sesion(cliente, base):
    cuenta = base.crear(EMAIL, CLAVE, {"totp": mfa._cifrar("JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP"), "preferido": "totp"})
    cliente.cookies.set(NOMBRE_COOKIE, seguridad.crear_token(cuenta["id"], EMAIL, cuenta["password_hash"]))


def test_menu_lateral_con_las_mismas_opciones(cliente, base):
    _sesion(cliente, base)
    html = cliente.get("/cuenta/contrasena").text
    assert 'class="menu-nav"' in html and 'href="/tablero"' in html
    assert 'href="/cuenta/seguridad"' in html
    assert html.count('action="/logout" method="post"') == 2  # menú y hoja "Más"
    assert 'class="hoja-mas"' in html
    assert 'class="menu-cuenta activo" data-texto="Contraseña"' in html or 'menu-cuenta activo' in html


def test_sin_sesion_conserva_la_barra_superior(cliente, base):
    html = cliente.get("/no-existe").text
    assert "menu-nav" not in html


def test_pwa_service_worker_manifiesto_y_sin_conexion(cliente, base):
    sw = cliente.get("/sw.js")
    assert sw.status_code == 200 and "javascript" in sw.headers["content-type"]
    assert sw.headers["cache-control"] == "no-cache"
    assert '"/tablero"' not in sw.text  # la página con datos nunca va a la caché (su hoja de estilos sí)
    manifiesto = cliente.get("/manifest.webmanifest")
    assert manifiesto.status_code == 200 and manifiesto.json()["display"] == "standalone"
    for icono in manifiesto.json()["icons"]:
        assert cliente.get(icono["src"]).status_code == 200
    sin_red = cliente.get("/offline.html")
    assert sin_red.status_code == 200 and "Sin conexión" in sin_red.text


def test_404_propia(cliente, base):
    r = cliente.get("/no-existe-esta-ruta")
    assert r.status_code == 404
    assert "Esta afiliación no está en el reporte" in r.text and "/no-existe-esta-ruta" in r.text
