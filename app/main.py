from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api_v1.endpoints import analysis

app = FastAPI(
    title="WinStake.ia API",
    description="API robusta para la plataforma de staking y juegos esp. para backend web/PWA.",
    version="1.0.0",
)

# Configuración CORS (Asegurar puertos de Angular/PWA permitidos)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],  # Angular dev server por defecto
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["Analysis"])
# TODO: Registrar auth.router cuando se implementen sus dependencias
#       (app.db.session, app.core.security, app.schemas.user, app.crud.user)


@app.get("/")
def read_root():
    return {"message": "WinStake API Running"}


@app.get("/health")
def health_check():
    return {"status": "ok", "db": "pending"}
