FROM python:3.12-slim AS base

WORKDIR /app

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Crear directorio de datos
RUN mkdir -p /app/data/cache

# ── Bot (análisis + Telegram) ────────────────────────────
FROM base AS bot
CMD ["python", "main.py"]

# ── Scheduler (ejecución programada) ─────────────────────
FROM base AS scheduler
CMD ["python", "scheduler.py"]

# ── Dashboard API (FastAPI) ──────────────────────────────
FROM base AS dashboard
EXPOSE 8000
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
