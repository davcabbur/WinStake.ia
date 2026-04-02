from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import time

from src.api.routes import router as api_router
from src.api.websockets import setup_websockets
from src.cache import APICache
from src.database import Database

logger = logging.getLogger(__name__)

# Timestamp de inicio para calcular uptime
_start_time = time.time()


def create_app() -> FastAPI:
    """Crea y configura la aplicación FastAPI para el dashboard de WinStake.ia."""
    app = FastAPI(
        title="WinStake.ia Dashboard API",
        description="API para servir datos al dashboard de Angular y webSockets para live odds.",
        version="1.0.0"
    )

    # Permitir CORS para el frontend (Angular usa 4200 por defecto)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Registrar rutas REST
    app.include_router(api_router, prefix="/api")

    # Configurar WebSockets
    setup_websockets(app)

    @app.on_event("startup")
    async def startup_event():
        logger.info("🚀 WinStake.ia Dashboard API iniciada")

    @app.get("/health")
    def health_check():
        """Health check con métricas del sistema."""
        uptime_seconds = time.time() - _start_time
        uptime_hours = round(uptime_seconds / 3600, 2)

        # Cache stats
        cache = APICache()
        cache_stats = cache.get_stats()

        # DB stats
        try:
            db = Database()
            roi = db.get_roi_summary()
            pending = db.get_pending_results()
            recent = db.get_recent_analyses(limit=1)
            last_analysis = recent[0]["run_date"] if recent else None
            db_stats = {
                "total_bets": roi["total_bets"],
                "roi_percent": roi["roi_percent"],
                "pending_results": len(pending),
                "last_analysis": last_analysis,
            }
        except Exception:
            db_stats = {"error": "database unavailable"}

        return {
            "status": "ok",
            "service": "WinStake.ia API",
            "uptime_hours": uptime_hours,
            "cache": cache_stats,
            "database": db_stats,
        }

    return app

app = create_app()
