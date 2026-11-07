"""Envío de correos con la API de Brevo (solo texto + HTML, sin adjuntos).

Sin BREVO_API_KEY (desarrollo) no envía nada: escribe el mensaje en el log.
"""

import html
import json
import logging
import urllib.request

import os

BREVO_API_KEY = os.getenv("BREVO_API_KEY", "").strip()
BREVO_REMITENTE = os.getenv("BREVO_REMITENTE", "").strip()
# URL pública para armar enlaces; en producción llega desde GitHub (workflow).
URL_PUBLICA = os.getenv("URL_PUBLICA", "http://127.0.0.1:8000").rstrip("/")

logger = logging.getLogger("calidad.correo")


# Paleta del sitio (static/css/acceso.css): el correo se ve como la aplicación.
_C = {
    "fondo": "#FAF8F5", "superficie": "#FFFFFF", "borde": "#E7E1D8", "texto": "#1C1917",
    "suave": "#6B635A", "acento": "#F29111", "cabecera": "#FFF3E2", "cabecera_texto": "#1C1917",
}
_FUENTE = "Inter,system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif"


def documento(asunto: str, contenido: str) -> str:
    """Envuelve el contenido del correo con la cabecera, el logo y los colores del sitio."""
    c = _C
    return (
        '<!doctype html><html lang="es"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(asunto)}</title></head>"
        f'<body style="margin:0;padding:0;background:{c["fondo"]};">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{c["fondo"]};padding:24px 12px;"><tr><td align="center">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:{c["superficie"]};'
        f'border:1px solid {c["borde"]};border-radius:12px;overflow:hidden;font-family:{_FUENTE};color:{c["texto"]};">'
        f'<tr><td style="background:{c["cabecera"]};border-top:4px solid {c["acento"]};padding:16px 28px;">'
        f'<img src="{URL_PUBLICA}/static/iconos/apple-touch-icon.png" width="28" height="28" alt="" '
        'style="vertical-align:middle;border:0;border-radius:6px;margin-right:10px;">'
        f'<span style="vertical-align:middle;font-size:17px;font-weight:700;color:{c["cabecera_texto"]};">Calidad de afiliaciones</span></td></tr>'
        f'<tr><td style="padding:24px 28px 12px;font-size:15px;line-height:1.6;color:{c["texto"]};">{contenido}</td></tr>'
        f'<tr><td style="padding:16px 28px 22px;border-top:1px solid {c["borde"]};font-size:12px;line-height:1.5;color:{c["suave"]};">'
        "Correo automático de Calidad de afiliaciones. Si no esperabas este mensaje, puedes ignorarlo.</td></tr>"
        "</table></td></tr></table></body></html>"
    )


def enviar(destino: str, nombre: str, asunto: str, texto: str, html: str) -> bool:
    if not BREVO_API_KEY or not BREVO_REMITENTE:
        logger.info("[correo local] Para %s | %s\n%s", destino, asunto, texto)
        return False
    cuerpo = json.dumps({
        "sender": {"email": BREVO_REMITENTE, "name": "Calidad de afiliaciones"},
        "to": [{"email": destino, "name": nombre}],
        "subject": asunto,
        "textContent": texto,
        "htmlContent": documento(asunto, html),
    }).encode("utf-8")
    pedido = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=cuerpo,
        headers={"api-key": BREVO_API_KEY, "content-type": "application/json", "accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(pedido, timeout=20) as respuesta:
            return 200 <= respuesta.status < 300
    except Exception:  # el usuario recibe la misma respuesta genérica igual
        logger.exception("Brevo no aceptó el correo")
        return False
