"""
Tests para OddsClient._parse_odds — emisión de chosen_book_odds.

Estos tests verifican que la pasada 3 de _parse_odds elige correctamente
la cuota cruda del bookmaker (Bet365 si está, si no el primer book) sin
alterar avg_odds ni bet365_odds.
"""

import pytest

from src.odds_client import OddsClient


# ── Helpers ─────────────────────────────────────────────────────────────────

def _bm(key, *, h2h=None, totals=None, btts=None, spreads=None,
        double_chance=None, home_team="Home", away_team="Away"):
    """Construye un dict de bookmaker con los mercados indicados."""
    markets = []
    if h2h:
        outcomes = []
        if "home" in h2h:
            outcomes.append({"name": home_team, "price": h2h["home"]})
        if "draw" in h2h:
            outcomes.append({"name": "Draw", "price": h2h["draw"]})
        if "away" in h2h:
            outcomes.append({"name": away_team, "price": h2h["away"]})
        markets.append({"key": "h2h", "outcomes": outcomes})
    if totals:
        # Lista de tuplas (kind, point, price). kind ∈ {"Over","Under"}.
        markets.append({
            "key": "totals",
            "outcomes": [
                {"name": kind, "price": price, "point": point}
                for (kind, point, price) in totals
            ],
        })
    if btts:
        outcomes = []
        if "yes" in btts:
            outcomes.append({"name": "Yes", "price": btts["yes"]})
        if "no" in btts:
            outcomes.append({"name": "No", "price": btts["no"]})
        markets.append({"key": "btts", "outcomes": outcomes})
    if spreads:
        # Lista de tuplas (side, point, price). side ∈ {"home","away"}.
        outcomes = []
        for side, point, price in spreads:
            name = home_team if side == "home" else away_team
            outcomes.append({"name": name, "price": price, "point": point})
        markets.append({"key": "spreads", "outcomes": outcomes})
    if double_chance:
        outcomes = []
        if "1x" in double_chance:
            outcomes.append({"name": f"{home_team} or Draw", "price": double_chance["1x"]})
        if "x2" in double_chance:
            outcomes.append({"name": f"{away_team} or Draw", "price": double_chance["x2"]})
        if "12" in double_chance:
            outcomes.append({"name": f"{home_team} or {away_team}", "price": double_chance["12"]})
        markets.append({"key": "double_chance", "outcomes": outcomes})
    return {"key": key, "markets": markets}


def _event(bookmakers, home_team="Home", away_team="Away"):
    return {
        "id": "test_event_1",
        "home_team": home_team,
        "away_team": away_team,
        "commence_time": "2026-12-31T20:00:00Z",
        "bookmakers": bookmakers,
    }


@pytest.fixture
def client():
    """OddsClient sin llamadas HTTP — _parse_odds no las requiere."""
    return OddsClient(api_key="dummy_for_test")


# ── Tests ───────────────────────────────────────────────────────────────────

def test_parse_odds_emits_chosen_book(client):
    """Con 4 books incluyendo Bet365, chosen_book_odds usa cuotas crudas de Bet365."""
    bookmakers = [
        _bm("pinnacle",     h2h={"home": 1.80, "draw": 3.50, "away": 4.20}),
        _bm("william_hill", h2h={"home": 1.82, "draw": 3.40, "away": 4.10}),
        _bm("bet365",       h2h={"home": 1.85, "draw": 3.60, "away": 4.50}),
        _bm("unibet",       h2h={"home": 1.81, "draw": 3.55, "away": 4.30}),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    assert len(parsed) == 1
    m = parsed[0]

    assert m["chosen_book_odds"]["home"] == 1.85
    assert m["chosen_book_odds"]["draw"] == 3.60
    assert m["chosen_book_odds"]["away"] == 4.50
    assert m["chosen_book_meta"]["home"] == "bet365"
    assert m["chosen_book_meta"]["draw"] == "bet365"
    assert m["chosen_book_meta"]["away"] == "bet365"


def test_parse_odds_chosen_book_fallback(client):
    """Sin Bet365, chosen_book_odds cae al primer book con datos para ese mercado."""
    bookmakers = [
        _bm("pinnacle",     h2h={"home": 1.80, "draw": 3.50, "away": 4.20}),  # primero
        _bm("william_hill", h2h={"home": 1.82, "draw": 3.40, "away": 4.10}),
        _bm("unibet",       h2h={"home": 1.81, "draw": 3.55, "away": 4.30}),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    m = parsed[0]

    assert m["chosen_book_odds"]["home"] == 1.80
    assert m["chosen_book_odds"]["draw"] == 3.50
    assert m["chosen_book_odds"]["away"] == 4.20
    assert m["chosen_book_meta"]["home"] == "pinnacle"
    assert m["chosen_book_meta"]["draw"] == "pinnacle"
    assert m["chosen_book_meta"]["away"] == "pinnacle"


def test_parse_odds_market_missing(client):
    """Un solo book sin BTTS → chosen_book_odds[btts_*] = None y meta = None."""
    bookmakers = [
        _bm("pinnacle", h2h={"home": 1.80, "draw": 3.50, "away": 4.20}),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    m = parsed[0]

    assert m["chosen_book_odds"]["home"] == 1.80
    assert m["chosen_book_odds"]["btts_yes"] is None
    assert m["chosen_book_odds"]["btts_no"] is None
    assert m["chosen_book_meta"]["btts_yes"] is None
    assert m["chosen_book_meta"]["btts_no"] is None


def test_parse_odds_chosen_book_preserves_raw_line_spread(client):
    """Para spreads, chosen_book_odds lleva la línea CRUDA del libro elegido, no la media."""
    bookmakers = [
        _bm("pinnacle", spreads=[("home", -3.0, 1.91), ("away",  3.0, 1.91)]),
        _bm("bet365",   spreads=[("home", -2.5, 1.95), ("away",  2.5, 1.87)]),  # preferido
        _bm("unibet",   spreads=[("home", -3.5, 1.88), ("away",  3.5, 1.94)]),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    m = parsed[0]

    assert m["chosen_book_odds"]["spread_home"] == 1.95
    assert m["chosen_book_odds"]["spread_away"] == 1.87
    assert m["chosen_book_odds"]["spread_line"] == -2.5  # línea cruda de Bet365, no media
    assert m["chosen_book_meta"]["spread_home"] == "bet365"
    assert m["chosen_book_meta"]["spread_line"] == "bet365"


def test_parse_odds_chosen_book_preserves_raw_line_total_nba(client):
    """Para totals NBA (point>50), chosen_book_odds lleva la línea cruda y el over/under del mismo book."""
    bookmakers = [
        _bm("pinnacle", totals=[("Over", 224.5, 1.91), ("Under", 224.5, 1.91)]),
        _bm("bet365",   totals=[("Over", 222.5, 1.95), ("Under", 222.5, 1.88)]),  # preferido
        _bm("unibet",   totals=[("Over", 226.0, 1.88), ("Under", 226.0, 1.94)]),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    m = parsed[0]

    assert m["chosen_book_odds"]["over"]       == 1.95
    assert m["chosen_book_odds"]["under"]      == 1.88
    assert m["chosen_book_odds"]["total_line"] == 222.5
    assert m["chosen_book_meta"]["over"]       == "bet365"
    assert m["chosen_book_meta"]["total_line"] == "bet365"


def test_parse_odds_avg_and_bet365_unchanged(client):
    """Pasada 3 NO altera avg_odds ni bet365_odds — siguen comportándose como antes."""
    bookmakers = [
        _bm("pinnacle", h2h={"home": 1.80, "draw": 3.50, "away": 4.20}),
        _bm("bet365",   h2h={"home": 1.85, "draw": 3.60, "away": 4.50}),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    m = parsed[0]

    # avg_odds: con <4 valores, _trimmed_mean es media simple. Pero cuando
    # Bet365 está disponible para moneyline, avg_odds.home prefiere Bet365.
    assert m["avg_odds"]["home"] == 1.85

    # bet365_odds dedicado sigue presente con el flag de disponibilidad.
    assert m["bet365_odds"]["available"] is True
    assert m["bet365_odds"]["h2h_home"] == 1.85
    assert m["bet365_odds"]["h2h_away"] == 4.50


def test_parse_odds_chosen_book_per_market_independence(client):
    """Cada mercado elige su propio book — un book puede ganar h2h y otro spreads."""
    bookmakers = [
        # Bet365 solo cubre h2h (no spreads ni btts)
        _bm("bet365",   h2h={"home": 1.85, "draw": 3.60, "away": 4.50}),
        # Pinnacle cubre spreads y btts (no h2h)
        _bm("pinnacle", spreads=[("home", -3.0, 1.92), ("away", 3.0, 1.90)],
                        btts={"yes": 1.78, "no": 2.05}),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    m = parsed[0]

    # h2h → Bet365
    assert m["chosen_book_meta"]["home"] == "bet365"
    assert m["chosen_book_odds"]["home"] == 1.85
    # spreads → no hay Bet365 → primer book con datos = pinnacle
    assert m["chosen_book_meta"]["spread_home"] == "pinnacle"
    assert m["chosen_book_odds"]["spread_home"] == 1.92
    assert m["chosen_book_odds"]["spread_line"] == -3.0
    # btts → no hay Bet365 → pinnacle
    assert m["chosen_book_meta"]["btts_yes"] == "pinnacle"
    assert m["chosen_book_odds"]["btts_yes"] == 1.78


# ── ISSUE 1/2/3 fixes ─────────────────────────────────────────────────────

def test_spread_chosen_book_must_cover_both_sides(client):
    """
    Bet365 solo cubre spread_home; Pinnacle cubre ambos lados.
    chosen_book debe ser Pinnacle (NO Bet365), porque Bet365 sin
    spread_away daría una combinación inapostable.
    """
    bookmakers = [
        # Bet365 con SOLO spread_home (sin spread_away)
        _bm("bet365",   spreads=[("home", -2.5, 1.95)]),
        # Pinnacle cubre ambos lados
        _bm("pinnacle", spreads=[("home", -3.0, 1.91), ("away", 3.0, 1.91)]),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    m = parsed[0]

    assert m["chosen_book_meta"]["spread_home"] == "pinnacle"
    assert m["chosen_book_meta"]["spread_away"] == "pinnacle"
    assert m["chosen_book_meta"]["spread_line"] == "pinnacle"
    assert m["chosen_book_odds"]["spread_home"] == 1.91
    assert m["chosen_book_odds"]["spread_away"] == 1.91
    assert m["chosen_book_odds"]["spread_line"] == -3.0


def test_nba_totals_chosen_book_consistent(client):
    """
    Bet365 cubre solo over_main; Pinnacle cubre ambos.
    over + under + total_line vienen los 3 de Pinnacle (no se mezclan libros).
    """
    bookmakers = [
        # Bet365 con SOLO Over (sin Under)
        _bm("bet365",   totals=[("Over", 222.5, 1.95)]),
        # Pinnacle cubre ambos lados
        _bm("pinnacle", totals=[("Over", 224.5, 1.91), ("Under", 224.5, 1.91)]),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    m = parsed[0]

    assert m["chosen_book_meta"]["over"]       == "pinnacle"
    assert m["chosen_book_meta"]["under"]      == "pinnacle"
    assert m["chosen_book_meta"]["total_line"] == "pinnacle"
    assert m["chosen_book_odds"]["over"]       == 1.91
    assert m["chosen_book_odds"]["under"]      == 1.91
    assert m["chosen_book_odds"]["total_line"] == 224.5


def test_bet365_odds_includes_draw(client):
    """
    bet365_odds debe exportar h2h_draw (no solo home/away). Sin esto,
    _resolve_legacy_bookmaker marcaría 'trimmed_avg' para empates aunque
    Bet365 los cubriera, contaminando la columna `bookmaker` de value_bets.
    """
    bookmakers = [
        _bm("bet365",   h2h={"home": 1.85, "draw": 3.40, "away": 4.20}),
        _bm("pinnacle", h2h={"home": 1.83, "draw": 3.45, "away": 4.10}),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    m = parsed[0]

    assert m["bet365_odds"]["h2h_home"] == 1.85
    assert m["bet365_odds"]["h2h_draw"] == 3.40
    assert m["bet365_odds"]["h2h_away"] == 4.20
    assert m["bet365_odds"]["available"] is True


def test_nba_multiple_lines_picks_market_main(client):
    """
    Un solo book con 3 líneas alternativas (220.5, 222.5, 225.5).
    Mediana = 222.5 → dedup elige esa línea (la del medio).
    """
    bookmakers = [
        _bm("pinnacle", totals=[
            ("Over",  220.5, 2.10), ("Under", 220.5, 1.78),
            ("Over",  222.5, 1.95), ("Under", 222.5, 1.88),  # mediana
            ("Over",  225.5, 1.78), ("Under", 225.5, 2.10),
        ]),
    ]
    parsed = client._parse_odds([_event(bookmakers)])
    m = parsed[0]

    assert m["chosen_book_odds"]["total_line"] == 222.5
    assert m["chosen_book_odds"]["over"]       == 1.95
    assert m["chosen_book_odds"]["under"]      == 1.88
    assert m["chosen_book_meta"]["over"]       == "pinnacle"
    assert m["chosen_book_meta"]["under"]      == "pinnacle"
    assert m["chosen_book_meta"]["total_line"] == "pinnacle"
