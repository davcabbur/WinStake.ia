import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from app.main import app

client = TestClient(app)

@patch("app.core.api_key._DASHBOARD_API_KEY", "")
def test_dashboard_access_unavailable_when_no_key_configured():
    """Prueba de Fail-Closed: Si el server arranca sin API Key instalada, deniega por defecto."""
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


@patch("app.core.api_key._DASHBOARD_API_KEY", "super_secret_test_key")
def test_dashboard_access_with_invalid_key():
    """Prueba que un header malicioso o erroneo recibe un 403 Forbidden."""
    response = client.get(
        "/api/dashboard/stats",
        headers={"X-API-Key": "wrong_key"}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API key"


@patch("app.core.api_key._DASHBOARD_API_KEY", "super_secret_test_key")
def test_dashboard_access_with_missing_key():
    """Prueba que sin proveer el header se recibe 401."""
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 401
    assert "Missing API key" in response.json()["detail"]


@patch("app.core.api_key._DASHBOARD_API_KEY", "super_secret_test_key")
@patch("app.api_v1.endpoints.dashboard._get_db")
def test_dashboard_access_with_valid_key(mock_get_db):
    """Prueba el acceso exitoso enviando el header correcto."""
    mock_db = mock_get_db.return_value
    mock_db.get_roi_summary.return_value = {
        "total_bets": 0, "wins": 0, "losses": 0, 
        "total_profit": 0, "win_rate": 0, "total_staked": 0,
        "roi_percent": 0.0, "avg_ev": 0.0
    }

    response = client.get(
        "/api/dashboard/stats",
        headers={"X-API-Key": "super_secret_test_key"}
    )
    
    assert response.status_code == 200
    assert "total_bets" in response.json()
