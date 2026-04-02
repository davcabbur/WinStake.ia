"""
WinStake.ia — Autenticación del Dashboard API
Protege los endpoints con un API key configurable.
"""

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
import config

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str = Security(API_KEY_HEADER)):
    """Valida el header X-API-Key contra DASHBOARD_API_KEY del .env."""
    expected = config.DASHBOARD_API_KEY
    if not expected:
        # Si no se configuró API key, permitir acceso (modo desarrollo)
        return None
    if not api_key or api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida o ausente")
    return api_key
