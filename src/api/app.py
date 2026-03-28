from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from src.api.routes import router as api_router
from src.api.websockets import setup_websockets

logger = logging.getLogger(__name__)

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
        return {"status": "ok", "service": "WinStake.ia API"}

    return app

app = create_app()
