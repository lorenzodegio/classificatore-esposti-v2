# Immagine della v2: solo ciò che serve. Si costruisce con internet,
# senza documenti montati; poi gira solo sulla rete interna.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HOME=/tmp

# LibreOffice senza interfaccia per convertire Word/RTF in PDF, con font
# compatibili Office.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        libreoffice-writer-nogui fonts-dejavu fonts-liberation \
        fonts-crosextra-carlito fonts-crosextra-caladea \
 && rm -rf /var/lib/apt/lists/*

# Servizio HTTP (servizio/, contratto 1.1): FastAPI + uvicorn + python-multipart;
# httpx (TestClient) e jsonschema per i test di contratto.
RUN pip install \
        pypdfium2==4.30.0 \
        Pillow==10.4.0 \
        reportlab==4.2.5 \
        pytest==8.3.3 \
        fastapi==0.115.6 \
        uvicorn==0.32.1 \
        python-multipart==0.0.20 \
        httpx==0.27.2 \
        jsonschema==4.23.0

WORKDIR /app
USER 1000:1000
