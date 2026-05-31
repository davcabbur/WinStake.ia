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
    # lang explícito y distinto del default para verificar que se inyecta de verdad
    # (no tautológico) y de forma independiente de WINSTAKE_WC_LANG en el entorno.
    c = _client(tmp_path, lang="fr")
    c.session.get = MagicMock(return_value=_fake_response({"ok": 1}))
    c.get_livescores()
    _, kwargs = c.session.get.call_args
    assert kwargs["params"]["key"] == "testkey"
    assert kwargs["params"]["lang"] == "fr"


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


def test_commentary_with_from_to(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_commentary(335680, from_=1000, to=2000)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/commentary")
    p = kwargs["params"]
    assert p["match_id"] == 335680
    assert p["from"] == 1000
    assert p["to"] == 2000


def test_commentary_omits_optional(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_commentary(335680)
    _, kwargs = c.session.get.call_args
    assert "from" not in kwargs["params"] and "to" not in kwargs["params"]


def test_events_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_events(335680)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/events")
    assert kwargs["params"]["match_id"] == 335680


def test_statistics_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_statistics(335680)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/statistics")
    assert kwargs["params"]["match_id"] == 335680


def test_lineups_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_lineups(335680)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/lineups")
    assert kwargs["params"]["match_id"] == 335680


def test_squad_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_squad(1443)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/squads")
    assert kwargs["params"]["team_id"] == 1443


def test_history_optional_params(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_history(date_from="2022-11-01", date_to="2022-12-31")
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/history")
    p = kwargs["params"]
    assert p["date_from"] == "2022-11-01"
    assert p["date_to"] == "2022-12-31"
    assert "team_id" not in p


def test_history_by_team(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_history(team_id=1443)
    _, kwargs = c.session.get.call_args
    assert kwargs["params"]["team_id"] == 1443
    assert "date_from" not in kwargs["params"]


def test_head2head_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_head2head(208, 211)
    args, kwargs = c.session.get.call_args
    assert args[0].endswith("/head2head")
    assert kwargs["params"]["team1_id"] == 208
    assert kwargs["params"]["team2_id"] == 211


def test_top_scorers_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_top_scorers()
    args, _ = c.session.get.call_args
    assert args[0].endswith("/goalscorers")


def test_cards_url(tmp_path):
    c = _client(tmp_path)
    c.session.get = MagicMock(return_value=_fake_response({}))
    c.get_cards()
    args, _ = c.session.get.call_args
    assert args[0].endswith("/cards")


# ── Parsers de normalización (shapes reales de worldcupapi.com, 2026-05-31) ──

_REAL_FIXTURE = {
    "round": "1", "date": "2026-06-11", "time": "19:00:00",
    "home": {"name": "Mexico", "logo": "https://cdn.worldcupapi.com/teams/1450.png", "id": 1450},
    "group_id": 4286,
    "away": {"name": "South Africa", "logo": "https://cdn.worldcupapi.com/teams/2767.png", "id": 2767},
    "odds": {"pre": {"1": 1.54, "2": 7, "X": 4.3}},
    "location": "Estadio Azteca, Mexico City",
    "id": 1825339,
}

_REAL_STANDING = {
    "rank": 1, "points": 0, "matches": 0, "goal_diff": 0,
    "goals_scored": 0, "goals_conceded": 0, "lost": 0, "drawn": 0, "won": 0,
    "team": {"id": 1722, "name": "Czech Republic", "logo": "https://cdn.worldcupapi.com/teams/1722.png"},
}


def test_parse_fixture():
    from src.worldcup_client import parse_fixture
    f = parse_fixture(_REAL_FIXTURE)
    assert f["id"] == 1825339
    assert f["round"] == "1"
    assert f["date"] == "2026-06-11" and f["time"] == "19:00:00"
    assert f["home_team"] == "Mexico" and f["home_id"] == 1450
    assert f["away_team"] == "South Africa" and f["away_id"] == 2767
    assert f["group_id"] == 4286
    assert f["location"] == "Estadio Azteca, Mexico City"
    assert f["odds_1x2"] == {"home": 1.54, "draw": 4.3, "away": 7}


def test_parse_fixture_missing_odds_is_defensive():
    from src.worldcup_client import parse_fixture
    raw = {k: v for k, v in _REAL_FIXTURE.items() if k != "odds"}
    f = parse_fixture(raw)
    assert f["odds_1x2"] == {"home": None, "draw": None, "away": None}
    # campos núcleo siguen presentes
    assert f["home_team"] == "Mexico" and f["id"] == 1825339


def test_parse_fixtures_list_and_empty():
    from src.worldcup_client import parse_fixtures
    parsed = parse_fixtures([_REAL_FIXTURE])
    assert len(parsed) == 1 and parsed[0]["home_team"] == "Mexico"
    assert parse_fixtures(None) == []
    assert parse_fixtures([]) == []


def test_parse_standing():
    from src.worldcup_client import parse_standing
    s = parse_standing(_REAL_STANDING)
    assert s["rank"] == 1
    assert s["team_id"] == 1722 and s["team_name"] == "Czech Republic"
    assert s["points"] == 0 and s["played"] == 0
    assert s["won"] == 0 and s["drawn"] == 0 and s["lost"] == 0
    assert s["goals_for"] == 0 and s["goals_against"] == 0 and s["goal_diff"] == 0


def test_parse_standings_list_and_empty():
    from src.worldcup_client import parse_standings
    parsed = parse_standings([_REAL_STANDING])
    assert len(parsed) == 1 and parsed[0]["team_name"] == "Czech Republic"
    assert parse_standings(None) == []
