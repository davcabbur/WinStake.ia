"""
WinStake.ia — API Key Authentication
Dependency de FastAPI para proteger endpoints con X-API-Key header.
"""

import os
import logging

from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

logger = logging.getLogger("WinStakeAPI")

# Header esperado: X-API-Key: <clave>
_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Cargar la clave desde la variable de entorno (ya definida en config.py raíz)
_DASHBOARD_API_KEY = os.getenv("DASHBOARD_API_KEY", "")


async def require_api_key(
    api_key: str = Security(_api_key_header),
) -> str:
    """
    Dependency de FastAPI que valida el header X-API-Key.

    Uso:
        @router.get("/stats", dependencies=[Depends(require_api_key)])
        def get_stats(): ...

    O a nivel de router:
        router = APIRouter(dependencies=[Depends(require_api_key)])
    """
    if not _DASHBOARD_API_KEY:
        # Si no hay API key configurada, bloquear todo en producción
        logger.warning(
            "⚠️ DASHBOARD_API_KEY no configurada en .env — "
            "los endpoints protegidos están BLOQUEADOS."
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key not configured on server. Set DASHBOARD_API_KEY in .env",
        )

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Include header: X-API-Key: <your-key>",
        )

    if api_key != _DASHBOARD_API_KEY:
        logger.warning(f"🔒 API key inválida recibida (primeros 8 chars: {api_key[:8]}...)")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key",
        )

    return api_key
