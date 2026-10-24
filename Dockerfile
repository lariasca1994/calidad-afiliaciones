FROM python:3.12.15-slim
# Almacén de certificados del sistema sin las raíces que firmaron los intermedios
# comprometidos de eMudhra (octubre 2026): emSign y Comodo "AAA Certificate Services".
RUN if command -v update-ca-certificates > /dev/null; then \
        rm -f /usr/share/ca-certificates/mozilla/emSign_* /usr/share/ca-certificates/mozilla/Comodo_AAA_Services_root.crt \
        && update-ca-certificates --fresh > /dev/null 2>&1; \
    fi

WORKDIR /app

# ca-certificates: pymysql necesita poder validar la cadena de certificados
# de Aiven cuando DB_SSL_CA apunta a uno; la imagen slim no lo trae.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Deja /app en el sys.path explícitamente: "from proceso import ..." en
# web/main.py depende de que la raíz del proyecto sea importable, y no
# todos los invocadores de uvicorn la agregan por su cuenta.
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "web.main:app", "--host", "0.0.0.0", "--port", "8000"]
