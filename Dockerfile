FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Instalar navegadores + deps de Playwright
RUN playwright install --with-deps chromium

# Código del worker
COPY worker ./worker

# Arranque correcto
CMD ["python", "-m", "worker.worker"]
