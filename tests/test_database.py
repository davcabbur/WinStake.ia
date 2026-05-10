import os
import pytest
import tempfile

from src.database import Database
from src.analyzer import MatchAnalysis, MatchProbabilities, EVResult, KellyResult


@pytest.fixture
def mock_db():
    fd, path = tempfile.mkstemp(suffix=".sqlite")
    os.close(fd)
    db = Database(db_path=path)
    yield db
    try:
        if os.path.exists(path):
            os.remove(path)
    except PermissionError:
        pass


def _make_analysis(home="Team A", away="Team B", has_value=True) -> MatchAnalysis:
    """Helper para crear un MatchAnalysis con datos mínimos."""
    analysis = MatchAnalysis(
        home_team=home,
        away_team=away,
        commence_time="2026-04-04T18:30:00Z",
        probabilities=MatchProbabilities(
            home_win=0.55, draw=0.25, away_win=0.20,
            over_25=0.60, under_25=0.40,
            lambda_home=1.5, lambda_away=1.1,
        ),
        market_odds={"home": 1.85, "draw": 3.40, "away": 4.20, "over_25": 2.10, "under_25": 1.75},
        recommendation="Local @ 1.85",
        confidence="Media",
    )
    if has_value:
        value_bet = EVResult(
            selection="Local", probability=0.55, odds=1.85,
            ev=0.0175, ev_percent=1.75, is_value=True,
        )
        analysis.best_bet = value_bet
        analysis.ev_results = [
            value_bet,
            EVResult(selection="Empate", probability=0.25, odds=3.40,
                     ev=-0.15, ev_percent=-15.0, is_value=False),
        ]
        analysis.kelly = KellyResult(
            kelly_full=5.0, kelly_half=2.5, stake_units=2.5, risk_level="Bajo",
        )
    return analysis


# ── Inicialización ────────────────────────────────────────

def test_database_initialization(mock_db):
    """Las tablas se crean correctamente."""
    with mock_db._get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]

    assert "analyses" in tables
    assert "value_bets" in tables
    assert "match_results" in tables


def test_migrations_idempotent(tmp_path):
    """Re-instanciar Database sobre la misma BD no duplica columnas ni falla."""
    import sqlite3

    path = str(tmp_path / "winstake_migrations.sqlite")
    Database(db_path=path)
    Database(db_path=path)
    Database(db_path=path)

    conn = sqlite3.connect(path)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(value_bets)").fetchall()]
    conn.close()

    expected = (
        "sport", "line",
        "bookmaker", "odds_at_pick", "closing_odds", "is_paper",
        "created_at", "settled_at", "result", "pnl_units",
    )
    for col in expected:
        assert cols.count(col) == 1, f"Columna {col} duplicada o ausente: {cols}"


def test_foreign_keys_enabled(mock_db):
    """PRAGMA foreign_keys debe estar ON."""
    with mock_db._get_conn() as conn:
        result = conn.execute("PRAGMA foreign_keys").fetchone()
    assert result[0] == 1


# ── Save & Retrieve ───────────────────────────────────────

def test_save_analysis_with_value_bet(mock_db):
    """Guardar análisis con value bet crea registros en ambas tablas."""
    analysis = _make_analysis(has_value=True)
    analysis_id = mock_db.save_analysis(analysis)

    assert analysis_id > 0

    with mock_db._get_conn() as conn:
        row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        assert row["home_team"] == "Team A"
        assert row["away_team"] == "Team B"

        vb = conn.execute("SELECT * FROM value_bets WHERE analysis_id = ?", (analysis_id,)).fetchone()
        assert vb["selection"] == "Local"
        assert vb["odds"] == 1.85


def test_save_analysis_without_value_bet(mock_db):
    """Guardar análisis sin value bet solo crea registro en analyses."""
    analysis = _make_analysis(has_value=False)
    analysis_id = mock_db.save_analysis(analysis)

    with mock_db._get_conn() as conn:
        vb = conn.execute("SELECT * FROM value_bets WHERE analysis_id = ?", (analysis_id,)).fetchone()
    assert vb is None


# ── ROI Summary ───────────────────────────────────────────

def test_roi_summary_empty(mock_db):
    """ROI vacío con 0 resultados."""
    roi = mock_db.get_roi_summary()
    assert roi["total_bets"] == 0
    assert roi["roi_percent"] == 0.0


def test_roi_summary_with_results(mock_db):
    """ROI calculado correctamente con resultados reales."""
    analysis = _make_analysis()
    mock_db.save_analysis(analysis)

    # Registrar resultado: apuesta ganada
    with mock_db._get_conn() as conn:
        vb_id = conn.execute("SELECT id FROM value_bets").fetchone()[0]

    profit = mock_db.record_result(vb_id, home_goals=2, away_goals=1)
    assert profit > 0  # Local ganó

    roi = mock_db.get_roi_summary()
    assert roi["total_bets"] == 1
    assert roi["wins"] == 1
    assert roi["total_profit"] > 0


# ── Record Result ─────────────────────────────────────────

def test_record_result_win(mock_db):
    """Resultado correcto genera profit positivo."""
    analysis = _make_analysis()
    mock_db.save_analysis(analysis)

    with mock_db._get_conn() as conn:
        vb = conn.execute("SELECT id, odds, stake_units FROM value_bets").fetchone()

    profit = mock_db.record_result(vb["id"], home_goals=3, away_goals=1)
    expected = vb["stake_units"] * (vb["odds"] - 1)
    assert abs(profit - expected) < 0.1


def test_record_result_loss(mock_db):
    """Resultado incorrecto genera pérdida."""
    analysis = _make_analysis()
    mock_db.save_analysis(analysis)

    with mock_db._get_conn() as conn:
        vb_id = conn.execute("SELECT id FROM value_bets").fetchone()[0]

    profit = mock_db.record_result(vb_id, home_goals=0, away_goals=2)
    assert profit < 0


def test_record_result_invalid_bet_id(mock_db):
    """ID inexistente retorna 0."""
    profit = mock_db.record_result(9999, home_goals=1, away_goals=0)
    assert profit == 0.0


# ── Check Bet Won ─────────────────────────────────────────

def test_check_bet_local_win():
    assert Database._check_bet_won("Local", 2, 1) is True
    assert Database._check_bet_won("Local", 1, 2) is False
    assert Database._check_bet_won("Local", 1, 1) is False


def test_check_bet_empate():
    assert Database._check_bet_won("Empate", 1, 1) is True
    assert Database._check_bet_won("Empate", 2, 1) is False


def test_check_bet_visitante():
    assert Database._check_bet_won("Visitante", 0, 1) is True
    assert Database._check_bet_won("Visitante", 1, 0) is False


def test_check_bet_over_25():
    assert Database._check_bet_won("Over 2.5", 2, 1) is True   # 3 goles
    assert Database._check_bet_won("Over 2.5", 1, 1) is False  # 2 goles
    assert Database._check_bet_won("Over 2.5", 0, 0) is False  # 0 goles


def test_check_bet_under_25():
    assert Database._check_bet_won("Under 2.5", 1, 1) is True  # 2 goles
    assert Database._check_bet_won("Under 2.5", 2, 1) is False # 3 goles


# ── Pending Results ───────────────────────────────────────

def test_pending_results(mock_db):
    """Value bets sin resultado aparecen como pendientes."""
    analysis = _make_analysis()
    mock_db.save_analysis(analysis)

    pending = mock_db.get_pending_results()
    assert len(pending) == 1
    assert pending[0]["selection"] == "Local"


def test_pending_results_cleared_after_recording(mock_db):
    """Tras registrar resultado, la bet ya no aparece como pendiente."""
    analysis = _make_analysis()
    mock_db.save_analysis(analysis)

    with mock_db._get_conn() as conn:
        vb_id = conn.execute("SELECT id FROM value_bets").fetchone()[0]

    mock_db.record_result(vb_id, home_goals=1, away_goals=0)

    pending = mock_db.get_pending_results()
    assert len(pending) == 0


# ── Recent Analyses ───────────────────────────────────────

def test_recent_analyses(mock_db):
    """Recuperar análisis recientes."""
    for i in range(5):
        mock_db.save_analysis(_make_analysis(home=f"Team {i}"))

    recent = mock_db.get_recent_analyses(limit=3)
    assert len(recent) == 3


# ── Paper trading: bookmaker + odds_at_pick + is_paper + created_at ───────

def test_save_analysis_persists_bookmaker_and_odds_at_pick(mock_db):
    """
    Con bookmaker_meta poblado (modo USE_RAW_ODDS=1), value_bets persiste
    bookmaker per-mercado, odds_at_pick = ev.odds, is_paper=1, created_at
    no nulo.
    """
    analysis = _make_analysis(has_value=True)
    # EVResult del fixture tiene selection="Local"; le añadimos market_key
    # y poblamos bookmaker_meta paralelo.
    analysis.ev_results[0].market_key = "home"
    analysis.bookmaker_meta = {"home": "pinnacle", "draw": "bet365", "away": "unibet"}

    mock_db.save_analysis(analysis)

    with mock_db._get_conn() as conn:
        row = conn.execute(
            "SELECT bookmaker, odds_at_pick, is_paper, created_at, odds "
            "FROM value_bets WHERE selection = 'Local'"
        ).fetchone()

    assert row["bookmaker"] == "pinnacle"
    assert row["odds_at_pick"] == row["odds"]   # ev.odds tal cual
    assert row["is_paper"] == 1
    assert row["created_at"] is not None
    assert "T" in row["created_at"]              # ISO 8601


def test_save_analysis_legacy_bookmaker(mock_db):
    """
    Sin bookmaker_meta, _resolve_legacy_bookmaker decide:
      - h2h home/draw/away → 'bet365' si bet365_odds lo cubre
      - spreads            → 'bet365' si bet365_odds lo cubre
      - over_25, btts_yes  → 'trimmed_avg'
    """
    analysis = _make_analysis(has_value=True)
    analysis.bookmaker_meta = None
    analysis.bet365_odds = {
        "h2h_home":     1.85,
        "h2h_draw":     3.40,
        "h2h_away":     4.20,
        "spread_home":  1.91,
        "spread_away":  None,
        "spread_line":  -2.5,
    }

    # Picks de los 6 mercados a verificar
    analysis.ev_results = [
        EVResult(selection="Local",     market_key="home",         probability=0.55, odds=1.85, ev=0.02, ev_percent=2.0,  is_value=True),
        EVResult(selection="Empate",    market_key="draw",         probability=0.30, odds=3.40, ev=0.02, ev_percent=2.0,  is_value=True),
        EVResult(selection="Visitante", market_key="away",         probability=0.24, odds=4.20, ev=0.01, ev_percent=1.0,  is_value=True),
        EVResult(selection="Spread Home", market_key="spread_home", probability=0.55, odds=1.91, ev=0.05, ev_percent=5.0, is_value=True, line=-2.5),
        EVResult(selection="Over 2.5",  market_key="over_25",      probability=0.55, odds=2.10, ev=0.155, ev_percent=15.5, is_value=True),
        EVResult(selection="BTTS Sí",   market_key="btts_yes",     probability=0.55, odds=1.85, ev=0.02, ev_percent=2.0,  is_value=True),
    ]

    mock_db.save_analysis(analysis)

    with mock_db._get_conn() as conn:
        rows = {
            r["selection"]: r["bookmaker"]
            for r in conn.execute(
                "SELECT selection, bookmaker FROM value_bets"
            ).fetchall()
        }

    assert rows["Local"]       == "bet365"
    assert rows["Empate"]      == "bet365"   # post-arreglo 1
    assert rows["Visitante"]   == "bet365"
    assert rows["Spread Home"] == "bet365"
    assert rows["Over 2.5"]    == "trimmed_avg"
    assert rows["BTTS Sí"]     == "trimmed_avg"


def test_save_analysis_legacy_bookmaker_no_bet365_data(mock_db):
    """
    bookmaker_meta=None y bet365_odds=None → todos los picks marcados
    'trimmed_avg' (no podemos afirmar Bet365 sin evidencia).
    """
    analysis = _make_analysis(has_value=True)
    analysis.bookmaker_meta = None
    analysis.bet365_odds = None
    analysis.ev_results[0].market_key = "home"

    mock_db.save_analysis(analysis)

    with mock_db._get_conn() as conn:
        row = conn.execute(
            "SELECT bookmaker FROM value_bets WHERE selection = 'Local'"
        ).fetchone()

    assert row["bookmaker"] == "trimmed_avg"
