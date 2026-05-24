"""
Tests de autenticación contra src.api.app (API actual).

Reemplaza test_api_auth.py (legacy, contra app.main).

Diferencias respecto al legacy:
- Key vacía → modo dev, permite acceso (antes: 503)
- Key incorrecta → 401 (antes: 403)
- Key ausente  → 401 (igual)
"""
from unittest.mock import patch

import config
import pytest
from fastapi.testclient import TestClient

from src.api.app import app

client = TestClient(app)


def test_dev_mode_allows_access_when_no_key_configured():
    """Si DASHBOARD_API_KEY está vacía, el sistema permite acceso (modo dev)."""
    with patch.object(config, "DASHBOARD_API_KEY", ""):
        response = client.get("/api/dashboard/stats")
    assert response.status_code != 401


def test_wrong_api_key_returns_401():
    """Con key configurada, una key incorrecta devuelve 401."""
    with patch.object(config, "DASHBOARD_API_KEY", "super_secret_test_key"):
        response = client.get(
            "/api/dashboard/stats",
            headers={"X-API-Key": "wrong_key"},
        )
    assert response.status_code == 401
    assert "inválida" in response.json()["detail"] or "ausente" in response.json()["detail"]


def test_missing_api_key_header_returns_401():
    """Con key configurada, omitir el header devuelve 401."""
    with patch.object(config, "DASHBOARD_API_KEY", "super_secret_test_key"):
        response = client.get("/api/dashboard/stats")
    assert response.status_code == 401


def test_correct_api_key_passes_auth():
    """Con key configurada y correcta, auth pasa (status != 401)."""
    with patch.object(config, "DASHBOARD_API_KEY", "super_secret_test_key"):
        response = client.get(
            "/api/dashboard/stats",
            headers={"X-API-Key": "super_secret_test_key"},
        )
    assert response.status_code != 401


def test_health_endpoint_is_public():
    """/health no requiere auth."""
    response = client.get("/health")
    assert response.status_code == 200
