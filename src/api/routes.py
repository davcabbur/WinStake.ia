from fastapi import APIRouter, Depends, HTTPException, Query
import sqlite3
import logging
from pydantic import BaseModel
from src.database import DB_PATH, Database
from src.api.auth import require_api_key
from src.odds_client import OddsClient
from src.football_client import FootballClient
from src.nba_client import NBAClient
from src.analyzer import Analyzer
from src.sports.config import get_sport, SPORTS

logger = logging.getLogger(__name__)


class EngineConfigIn(BaseModel):
    ev_min: float
    kelly_fraction: float
    kelly_cap: float
    home_advantage: float
    xg_weight: float
    bankroll_base: float

router = APIRouter(dependencies=[Depends(require_api_key)])

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@router.get("/dashboard/stats")
def get_dashboard_stats(sport: str = Query(default="nba")) -> dict:
    """Devuelve stats de picks paper cerrados (WIN/LOSS) filtradas por sport."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT
                COUNT(*) AS total_bets,
                SUM(CASE WHEN result = 'WIN' THEN 1 ELSE 0 END) AS won_bets,
                SUM(stake_units) AS total_staked,
                SUM(pnl_units) AS total_profit
            FROM value_bets
            WHERE sport = ?
              AND is_paper = 1
              AND result IN ('WIN', 'LOSS')
        """, (sport,))
        row = cursor.fetchone()

        total_bets = row["total_bets"] or 0
        won_bets = row["won_bets"] or 0
        total_staked = row["total_staked"] or 0.0
        total_profit = row["total_profit"] or 0.0
        win_rate = (won_bets / total_bets * 100) if total_bets > 0 else 0.0
        roi_pct = (total_profit / total_staked * 100) if total_staked > 0 else 0.0

        return {
            "sport": sport,
            "total_bets": total_bets,
            "won_bets": won_bets,
            "win_rate": round(win_rate, 2),
            "total_staked": round(total_staked, 2),
            "total_profit": round(total_profit, 2),
            "roi_pct": round(roi_pct, 2),
        }
    finally:
        conn.close()

@router.get("/dashboard/history")
def get_bet_history(limit: int = 50, offset: int = 0):
    """Devuelve el historial de apuestas y análisis."""
    conn = get_db_connection()
    try:
        # Hacemos JOIN de analyses y value_bets
        cursor = conn.execute("""
            SELECT 
                a.run_date, a.home_team, a.away_team, a.commence_time,
                vb.selection, vb.odds, vb.ev_percent, vb.confidence, vb.stake_units,
                mr.bet_won, mr.profit_units
            FROM value_bets vb
            JOIN analyses a ON vb.analysis_id = a.id
            LEFT JOIN match_results mr ON vb.id = mr.value_bet_id
            ORDER BY a.run_date DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        
        rows = cursor.fetchall()
        history = [dict(row) for row in rows]
        
        return {"data": history, "limit": limit, "offset": offset}
    finally:
        conn.close()

@router.get("/dashboard/chart-data")
def get_chart_data():
    """Devuelve datos de evolución del Bankroll/Profit por fecha."""
    conn = get_db_connection()
    try:
        cursor = conn.execute("""
            SELECT 
                substr(recorded_at, 1, 10) as date,
                SUM(profit_units) as daily_profit
            FROM match_results
            GROUP BY substr(recorded_at, 1, 10)
            ORDER BY date ASC
        """)
        
        rows = cursor.fetchall()
        dates = []
        profits = []
        cumulative = 0.0
        
        for row in rows:
            dates.append(row["date"])
            cumulative += row["daily_profit"]
            profits.append(round(cumulative, 2))
            
        return {"dates": dates, "cumulative_profit": profits}
    finally:
        conn.close()


@router.get("/dashboard/engine-config")
def get_engine_config():
    """Devuelve la configuración actual del motor."""
    db = Database()
    return db.get_settings()


@router.put("/dashboard/engine-config")
def update_engine_config(config: EngineConfigIn):
    """Actualiza la configuración del motor."""
    db = Database()
    updated = db.update_settings(config.model_dump())
    return updated


@router.get("/dashboard/analysis-results")
def get_latest_analysis() -> dict:
    """Últimos 30 análisis con sus value bets asociadas."""
    db = Database()
    analyses = db.get_recent_analyses(limit=30)
    results = []
    for a in analyses:
        results.append({
            "home_team": a["home_team"],
            "away_team": a["away_team"],
            "commence_time": a["commence_time"],
            "prob_home": a["prob_home"],
            "prob_draw": a["prob_draw"],
            "prob_away": a["prob_away"],
            "prob_over25": a["prob_over25"],
            "prob_under25": a["prob_under25"],
            "odds_home": a["odds_home"],
            "odds_draw": a["odds_draw"],
            "odds_away": a["odds_away"],
            "recommendation": a["recommendation"],
            "confidence": a["confidence"],
            "selection": a.get("bet_selection"),
            "ev_percent": a.get("bet_ev"),
            "stake_units": a.get("bet_stake"),
            "run_date": a["run_date"],
        })
    return {"results": results, "total": len(results)}


@router.get("/dashboard/stats-by-selection")
def get_stats_by_selection() -> dict:
    """ROI desglosado por tipo de selección (Local, Empate, Visitante, etc.)."""
    db = Database()
    return {"breakdown": db.get_stats_by_selection()}


@router.get("/v1/analysis/")
def run_analysis(
    sport: str = Query("laliga", description="Deporte a analizar", enum=list(SPORTS.keys())),
) -> dict:
    """Ejecuta el análisis en vivo y devuelve las value bets encontradas."""
    try:
        sport_config = get_sport(sport)
        is_nba = sport_config.sport_type == "basketball"

        odds_client = OddsClient(sport_config=sport_config)
        stats_client = NBAClient() if is_nba else FootballClient()
        analyzer = Analyzer(sport_config=sport_config)

        matches_odds = odds_client.get_upcoming_odds()
        if not matches_odds:
            raise HTTPException(status_code=404, detail="No upcoming odds could be fetched.")

        standings = stats_client.get_standings()
        analyzer.calibrate_from_standings(standings)

        analyses = []
        for match in matches_odds:
            home = match["home_team"]
            away = match["away_team"]
            odds = match["avg_odds"]

            home_stats = stats_client.find_team_in_standings(home, standings)
            away_stats = stats_client.find_team_in_standings(away, standings)

            h2h_data = []
            if home_stats and away_stats:
                home_id = home_stats.get("team_id")
                away_id = away_stats.get("team_id")
                if home_id and away_id:
                    h2h_data = stats_client.get_h2h(home_id, away_id)

            analysis = analyzer.analyze_match(
                home_team=home,
                away_team=away,
                odds=odds,
                home_stats=home_stats,
                away_stats=away_stats,
                commence_time=match.get("commence_time", ""),
                h2h_data=h2h_data,
            )

            for ev in analysis.ev_results:
                if ev.is_value:
                    kelly = analyzer._kelly_criterion(ev.probability, ev.odds)
                    confidence = analyzer._classify_confidence(ev.ev_percent)
                    analyses.append({
                        "match": f"{home} vs {away}",
                        "commence_time": match.get("commence_time", ""),
                        "selection": ev.selection,
                        "odds": ev.odds,
                        "ev_percent": ev.ev_percent,
                        "probability": ev.probability,
                        "kelly_half": kelly.kelly_half,
                        "stake_units": kelly.stake_units,
                        "confidence": confidence,
                        "sport": sport,
                    })

        return {
            "status": "success",
            "sport": sport,
            "value_bets": analyses,
            "total_analyzed": len(matches_odds),
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error ejecutando análisis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
