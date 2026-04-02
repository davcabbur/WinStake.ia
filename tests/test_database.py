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
        analysis.best_bet = EVResult(
            selection="Local", probability=0.55, odds=1.85,
            ev=0.0175, ev_percent=1.75, is_value=True,
        )
        analysis.kelly = KellyResult(
            kelly_full=5.0, kelly_half=2.5, stake_units=2.5, risk_level="Bajo",
        )
    return analysis


# ── Inicialización ────────────────────────────────────────

def test_database_initialization(mock_db):
    """Las tablas se crean correctamente."""
    conn = mock_db._get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    conn.close()

    assert "analyses" in tables
    assert "value_bets" in tables
    assert "match_results" in tables


def test_foreign_keys_enabled(mock_db):
    """PRAGMA foreign_keys debe estar ON."""
    conn = mock_db._get_conn()
    result = conn.execute("PRAGMA foreign_keys").fetchone()
    conn.close()
    assert result[0] == 1


# ── Save & Retrieve ───────────────────────────────────────

def test_save_analysis_with_value_bet(mock_db):
    """Guardar análisis con value bet crea registros en ambas tablas."""
    analysis = _make_analysis(has_value=True)
    analysis_id = mock_db.save_analysis(analysis)

    assert analysis_id > 0

    conn = mock_db._get_conn()
    row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
    assert row["home_team"] == "Team A"
    assert row["away_team"] == "Team B"

    vb = conn.execute("SELECT * FROM value_bets WHERE analysis_id = ?", (analysis_id,)).fetchone()
    assert vb["selection"] == "Local"
    assert vb["odds"] == 1.85
    conn.close()


def test_save_analysis_without_value_bet(mock_db):
    """Guardar análisis sin value bet solo crea registro en analyses."""
    analysis = _make_analysis(has_value=False)
    analysis_id = mock_db.save_analysis(analysis)

    conn = mock_db._get_conn()
    vb = conn.execute("SELECT * FROM value_bets WHERE analysis_id = ?", (analysis_id,)).fetchone()
    assert vb is None
    conn.close()


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
    conn = mock_db._get_conn()
    vb_id = conn.execute("SELECT id FROM value_bets").fetchone()[0]
    conn.close()

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

    conn = mock_db._get_conn()
    vb = conn.execute("SELECT id, odds, stake_units FROM value_bets").fetchone()
    conn.close()

    profit = mock_db.record_result(vb["id"], home_goals=3, away_goals=1)
    expected = vb["stake_units"] * (vb["odds"] - 1)
    assert abs(profit - expected) < 0.1


def test_record_result_loss(mock_db):
    """Resultado incorrecto genera pérdida."""
    analysis = _make_analysis()
    mock_db.save_analysis(analysis)

    conn = mock_db._get_conn()
    vb_id = conn.execute("SELECT id FROM value_bets").fetchone()[0]
    conn.close()

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

    conn = mock_db._get_conn()
    vb_id = conn.execute("SELECT id FROM value_bets").fetchone()[0]
    conn.close()

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
