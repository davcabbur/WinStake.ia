import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api_v1.endpoints import analysis, dashboard

app = FastAPI(
    title="WinStake.ia API",
    description="API robusta para la plataforma de staking y juegos esp. para backend web/PWA.",
    version="1.0.0",
)

# Leer orígenes permitidos desde el entorno (separados por coma)
# Por defecto permite el servidor dev de Angular
cors_origins_str = os.getenv("CORS_ORIGINS", "http://localhost:4200")
cors_origins = [origin.strip() for origin in cors_origins_str.split(",") if origin.strip()]

# Configuración CORS (Asegurar puertos de Angular/PWA permitidos)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["Dashboard"])
# TODO: Registrar auth.router cuando se implementen sus dependencias
#       (app.db.session, app.core.security, app.schemas.user, app.crud.user)


@app.get("/")
def read_root():
    return {"message": "WinStake API Running"}


@app.get("/health")
def health_check():
    return {"status": "ok", "db": "pending"}
