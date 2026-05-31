"""Tests para WorldCupClient — sin pegar a la API real (no gastar requests)."""

from unittest.mock import MagicMock

import requests

from src.cache import APICache
from src.worldcup_client import WorldCupClient


def _fake_response(json_data, status_ok=True):
    """Construye un fake requests.Response."""
    resp = MagicMock()
    resp.json.return_value = json_data
    resp.headers = {"x-requests-remaining": "1499"}
    if status_ok:
        resp.raise_for_status.return_value = None
    else:
        resp.raise_for_status.side_effect = requests.exceptions.HTTPError("boom")
    return resp


def _client(tmp_path, api_key="testkey", lang=None):
    """Cliente con caché aislada en tmp_path."""
    c = WorldCupClient(api_key=api_key, lang=lang)
    c.cache = APICache(cache_dir=str(tmp_path))
    return c


def test_empty_key_no_http(tmp_path):
    c = _client(tmp_path, api_key="")
    c.session.get = MagicMock()
    assert c.get_livescores() is None
    c.session.get.assert_not_called()


def test_request_injects_key_and_lang(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({"ok": 1}))
    c.get_livescores()
    _, kwargs = c.session.get.call_args
    assert kwargs["params"]["key"] == "testkey"
    assert kwargs["params"]["lang"] == c.lang


def test_livescores_url_and_return(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({"v": 1}))
    result = c.get_livescores()
    assert result == {"v": 1}
    args, _ = c.session.get.call_args
    assert args[0].endswith("/livescores")


def test_second_call_uses_cache(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({"v": 1}))
    first = c.get_livescores()
    second = c.get_livescores()
    assert first == second == {"v": 1}
    assert c.session.get.call_count == 1  # la 2ª se sirve de caché


def test_cache_key_varies_with_lang(tmp_path):
    c_es = _client(tmp_path, lang="es")
    c_es.session.get = MagicMock(return_value=_fake_response({"l": "es"}))
    c_es.get_livescores()
    c_en = _client(tmp_path, lang="en")
    c_en.session.get = MagicMock(return_value=_fake_response({"l": "en"}))
    c_en.get_livescores()
    # Idioma distinto → cache key distinta → sí hace HTTP
    assert c_en.session.get.call_count == 1


def test_http_error_returns_none(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response(None, status_ok=False))
    assert c.get_livescores() is None


def test_connection_error_returns_none(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(side_effect=requests.exceptions.ConnectionError("timeout"))
    assert c.get_livescores() is None


def test_fixtures_optional_params_omitted(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({"r": []}))
    c.get_fixtures(group="A")
    _, kwargs = c.session.get.call_args
    p = kwargs["params"]
    assert p["group"] == "A"
    assert "team_id" not in p and "date" not in p


def test_fixtures_team_and_date(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_fixtures(team_id=1443, date="2026-06-11")
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/fixtures")
    assert kwargs["params"]["team_id"] == 1443
    assert kwargs["params"]["date"] == "2026-06-11"
    assert "group" not in kwargs["params"]


def test_standings_form_flag(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_standings(group="B", form=True)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/standings")
    assert kwargs["params"]["group"] == "B"
    assert kwargs["params"]["form"] == 1


def test_standings_no_form_by_default(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_standings(group="C")
    _, kwargs = c.session.get.call_args
    assert "form" not in kwargs["params"]


def test_live_standings_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_live_standings("A")
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/livestandings")
    assert kwargs["params"]["group"] == "A"
