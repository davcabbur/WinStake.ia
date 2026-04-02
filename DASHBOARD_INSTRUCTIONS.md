# 🚀 Cómo Iniciar WinStake.ia — Guía Completa

WinStake.ia tiene **4 componentes** que puedes iniciar según lo que necesites.
Cada uno se ejecuta en una **terminal separada**.

> ⚠️ **Requisitos previos:** Activar el entorno virtual de Python antes de cualquier comando:
> ```powershell
> cd C:\Users\davec\OneDrive\Documentos\WinStake.ia
> venv\Scripts\activate
> ```

---

## 📋 Resumen Rápido

| # | Componente | Comando | Puerto | ¿Obligatorio? |
|---|-----------|---------|--------|----------------|
| 1 | **Backend API** | `python run_api.py` | `localhost:8000` | ✅ Sí |
| 2 | **Frontend Angular** | `cd frontend && npm start` | `localhost:4200` | ✅ Sí (para ver el dashboard) |
| 3 | **Bot Telegram** | `python src\bot_daemon.py` | — | 🟡 Opcional (para /analizar, /roi) |
| 4 | **Scheduler** | `python scheduler.py` | — | 🟡 Opcional (análisis automáticos) |

---

## Terminal 1 — Backend API (FastAPI)

Sirve los datos de análisis y conecta con la base de datos SQLite.

```powershell
cd C:\Users\davec\OneDrive\Documentos\WinStake.ia
venv\Scripts\activate
python run_api.py
```

✅ Verás: `Uvicorn running on http://0.0.0.0:8000`

**Endpoints disponibles:**
- `http://localhost:8000` — Health check
- `http://localhost:8000/docs` — Swagger UI (documentación interactiva de la API)
- `http://localhost:8000/api/v1/analysis` — Ejecutar análisis y obtener value bets (JSON)

---

## Terminal 2 — Frontend Angular

Interfaz visual del dashboard. Se conecta al backend en `localhost:8000`.

```powershell
cd C:\Users\davec\OneDrive\Documentos\WinStake.ia\frontend
npm start
```

> Si es la primera vez o has cambiado dependencias, ejecuta `npm install` antes.

✅ Verás: `Application bundle generation complete`

👉 Abre tu navegador en: **http://localhost:4200**

---

## Terminal 3 — Bot Telegram (Opcional)

Bot interactivo que responde a comandos desde Telegram.
**Necesita `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` configurados en `.env`.**

```powershell
cd C:\Users\davec\OneDrive\Documentos\WinStake.ia
venv\Scripts\activate
python src\bot_daemon.py
```

✅ Verás: `WinStake.ia Bot Daemon iniciado. Escuchando comandos de Telegram...`

**Comandos disponibles en Telegram:**
- `/analizar` — Ejecuta el análisis de la jornada y envía resultados
- `/roi` — Consulta tu bankroll y ROI histórico
- `/ping` — Verifica que el bot está operativo
- `/help` — Lista de comandos

---

## Terminal 4 — Scheduler (Opcional)

Ejecuta el análisis automáticamente en los horarios de La Liga.
Útil si quieres dejarlo corriendo en segundo plano sin tener que hacer `/analizar` manualmente.

```powershell
cd C:\Users\davec\OneDrive\Documentos\WinStake.ia
venv\Scripts\activate
python scheduler.py
```

**Horarios programados:**
| Día | Hora | Motivo |
|-----|------|--------|
| Viernes | 10:00 | Antes del partido nocturno |
| Sábado | 09:00 | Antes de los partidos del día |
| Domingo | 09:00 | Antes de los partidos del día |
| Martes | 10:00 | Jornadas entre semana |
| Miércoles | 10:00 | Jornadas entre semana |

**Opciones adicionales:**
```powershell
python scheduler.py --once    # Ejecutar una sola vez y salir
python scheduler.py --test    # Ejecutar ahora + continuar con scheduler
```

---

## 🛑 Detener cualquier componente

Ve a la terminal del componente y pulsa `Ctrl + C`.

---

## 🐳 Alternativa: Docker (Todo a la vez)

Si prefieres no abrir 4 terminales, puedes usar Docker Compose:

```powershell
docker compose up -d          # Inicia scheduler + dashboard
docker compose --profile manual run bot   # Ejecutar análisis puntual
```

---

## 🔧 Análisis manual sin bot ni scheduler

Si solo quieres ejecutar un análisis puntual desde la terminal:

```powershell
venv\Scripts\activate
python main.py                    # Análisis completo (usa APIs reales)
python main.py --mock-mode        # Con datos simulados (no gasta requests)
python main.py --dry-run           # Sin enviar a Telegram ni guardar en BD
python main.py --output-csv resultados.csv   # Exportar a CSV
python main.py --backtest 24       # Backtest temporada 2024/25
python main.py --verify            # Verificar resultados pendientes
python main.py -v                  # Modo verbose (DEBUG)
```
