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
    assert "match_outcomes" in tables


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


# ── UPSERT dedup NBA ──────────────────────────────────────

def _make_nba_analysis(home="Lakers", away="Celtics", selection="Over", odds=1.91, line=215.5) -> MatchAnalysis:
    """NBA-style analysis for UPSERT tests."""
    from src.ev_calculator import EVResult
    analysis = MatchAnalysis(
        home_team=home,
        away_team=away,
        commence_time="2026-05-01T00:00:00Z",
        probabilities=MatchProbabilities(
            home_win=0.55, draw=0.0, away_win=0.45,
            over_25=0.60, under_25=0.40,
            lambda_home=1.5, lambda_away=1.1,
        ),
        market_odds={"home": 1.91, "away": 1.91, "over": odds, "under": 1.91},
        recommendation=f"{selection} @ {odds}",
        confidence="Media",
    )
    ev_result = EVResult(
        selection=selection, probability=0.58, odds=odds,
        ev=0.1, ev_percent=10.0, is_value=True, line=line,
    )
    analysis.best_bet = ev_result
    analysis.ev_results = [ev_result]
    from src.ev_calculator import KellyResult
    analysis.kelly = KellyResult(kelly_full=5.0, kelly_half=2.5, stake_units=2.5, risk_level="Bajo")
    return analysis


def test_save_analysis_nba_sets_match_key(mock_db):
    """Nuevo pick NBA queda con match_key poblado."""
    analysis = _make_nba_analysis()
    mock_db.save_analysis(analysis, sport="nba")

    with mock_db._get_conn() as conn:
        row = conn.execute("SELECT match_key FROM value_bets WHERE sport = 'nba'").fetchone()
    assert row is not None
    assert row["match_key"] == "Lakers|Celtics|2026-05-01T00:00:00Z|Over"


def test_save_analysis_nba_upserts_duplicate(mock_db):
    """Segunda llamada con el mismo partido no crea pick duplicado — actualiza el existente."""
    analysis = _make_nba_analysis(odds=1.91)
    mock_db.save_analysis(analysis, sport="nba")

    analysis2 = _make_nba_analysis(odds=1.95)  # cuota distinta, mismo partido/selección
    mock_db.save_analysis(analysis2, sport="nba")

    with mock_db._get_conn() as conn:
        rows = conn.execute("SELECT odds FROM value_bets WHERE sport = 'nba'").fetchall()
    assert len(rows) == 1, f"Esperaba 1 pick, hay {len(rows)}"
    assert rows[0]["odds"] == pytest.approx(1.95)  # actualizado con la segunda cuota


def test_save_analysis_nba_does_not_overwrite_settled(mock_db):
    """Si el pick ya tiene result != NULL, el UPSERT no lo sobreescribe."""
    analysis = _make_nba_analysis(odds=1.91)
    mock_db.save_analysis(analysis, sport="nba")

    with mock_db._get_conn() as conn:
        vb_id = conn.execute("SELECT id FROM value_bets WHERE sport = 'nba'").fetchone()[0]
        conn.execute(
            "UPDATE value_bets SET result = 'WIN', pnl_units = 4.55, settled_at = '2026-05-02T12:00:00' WHERE id = ?",
            (vb_id,),
        )
        conn.commit()

    analysis2 = _make_nba_analysis(odds=2.10)  # nueva cuota
    mock_db.save_analysis(analysis2, sport="nba")

    with mock_db._get_conn() as conn:
        rows = conn.execute("SELECT odds, result FROM value_bets WHERE sport = 'nba'").fetchall()
    assert len(rows) == 1
    assert rows[0]["odds"] == pytest.approx(1.91)  # cuota original — no fue pisada
    assert rows[0]["result"] == "WIN"


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


# ── match_outcomes (game-centric schema) ──────────────────

def test_match_outcomes_schema(mock_db):
    """match_outcomes tiene el schema game-centric correcto."""
    with mock_db._get_conn() as conn:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(match_outcomes)").fetchall()]
    assert "home_team" in cols
    assert "away_team" in cols
    assert "game_date" in cols
    assert "home_score" in cols
    assert "away_score" in cols
    assert "winner" in cols
    assert "analysis_id" not in cols


def test_match_outcomes_insert_and_dedup(mock_db):
    """INSERT OR IGNORE respeta UNIQUE(home_team, away_team, game_date)."""
    with mock_db._get_conn() as conn:
        conn.execute("""
            INSERT INTO match_outcomes
                (home_team, away_team, game_date, home_score, away_score,
                 total_score, winner, fetched_at, source)
            VALUES ('Lakers', 'Celtics', '2026-04-07', 110, 105, 215,
                    'home', '2026-05-24T00:00:00Z', 'test')
        """)
        conn.commit()
        # Segunda inserción con mismo partido → debe ser ignorada
        conn.execute("""
            INSERT OR IGNORE INTO match_outcomes
                (home_team, away_team, game_date, home_score, away_score,
                 total_score, winner, fetched_at, source)
            VALUES ('Lakers', 'Celtics', '2026-04-07', 999, 999, 1998,
                    'away', '2026-05-24T00:00:00Z', 'test')
        """)
        conn.commit()
        rows = conn.execute(
            "SELECT * FROM match_outcomes WHERE home_team='Lakers'"
        ).fetchall()

    assert len(rows) == 1
    assert rows[0]["home_score"] == 110


def test_match_outcomes_join_with_analyses(mock_db):
    """match_outcomes se puede enlazar con analyses por (home_team, away_team, DATE(commence_time))."""
    analysis = _make_analysis(home="Golden State Warriors", away="Phoenix Suns", has_value=False)
    analysis.commence_time = "2026-04-10T00:00:00Z"
    mock_db.save_analysis(analysis, sport="nba")

    with mock_db._get_conn() as conn:
        conn.execute("""
            INSERT INTO match_outcomes
                (home_team, away_team, game_date, home_score, away_score,
                 total_score, winner, fetched_at, source)
            VALUES ('Golden State Warriors', 'Phoenix Suns', '2026-04-10',
                    120, 115, 235, 'home', '2026-05-24T00:00:00Z', 'test')
        """)
        conn.commit()
        row = conn.execute("""
            SELECT a.home_team, mo.home_score, mo.winner
            FROM analyses a
            JOIN match_outcomes mo
               ON mo.home_team = a.home_team
              AND mo.away_team = a.away_team
              AND mo.game_date = DATE(a.commence_time)
            WHERE a.home_team = 'Golden State Warriors'
        """).fetchone()

    assert row is not None
    assert row["home_score"] == 120
    assert row["winner"] == "home"
