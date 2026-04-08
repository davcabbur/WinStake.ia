"""
WinStake.ia — Dashboard API Endpoints
Serves stats, history, and chart data to the Angular frontend.
"""

import logging
from fastapi import APIRouter, Depends, Query

from src.database import Database
from app.core.api_key import require_api_key

router = APIRouter(dependencies=[Depends(require_api_key)])
logger = logging.getLogger("WinStakeAPI")


def _get_db() -> Database:
    return Database()


@router.get("/stats")
def get_dashboard_stats():
    """KPI stats: total bets, wins, win rate, total profit."""
    db = _get_db()
    roi = db.get_roi_summary()
    return {
        "total_bets": roi["total_bets"],
        "won_bets": roi["wins"],
        "win_rate": roi["win_rate"],
        "total_profit": roi["total_profit"],
    }


@router.get("/history")
def get_bet_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """Paginated bet history with results."""
    db = _get_db()
    with db._get_conn() as conn:
        rows = conn.execute("""
            SELECT
                a.run_date,
                a.home_team,
                a.away_team,
                a.commence_time,
                vb.selection,
                vb.odds,
                vb.ev_percent,
                vb.confidence,
                vb.stake_units,
                mr.bet_won,
                mr.profit_units
            FROM value_bets vb
            JOIN analyses a ON vb.analysis_id = a.id
            LEFT JOIN match_results mr ON mr.value_bet_id = vb.id
            ORDER BY a.run_date DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()

        data = []
        for row in rows:
            d = dict(row)
            # bet_won can be None if no result recorded yet
            if d["bet_won"] is None:
                d["profit_units"] = None
            data.append(d)

        return {"data": data, "limit": limit, "offset": offset}


@router.get("/chart-data")
def get_chart_data():
    """Cumulative profit over time for the profit chart."""
    db = _get_db()
    with db._get_conn() as conn:
        rows = conn.execute("""
            SELECT
                DATE(a.run_date) as date,
                SUM(mr.profit_units) as daily_profit
            FROM match_results mr
            JOIN value_bets vb ON mr.value_bet_id = vb.id
            JOIN analyses a ON vb.analysis_id = a.id
            GROUP BY DATE(a.run_date)
            ORDER BY date
        """).fetchall()

        dates = []
        cumulative_profit = []
        running = 0.0

        for row in rows:
            dates.append(row["date"])
            running += row["daily_profit"] or 0
            cumulative_profit.append(round(running, 2))

        return {"dates": dates, "cumulative_profit": cumulative_profit}


@router.get("/analysis-results")
def get_latest_analysis():
    """Get the most recent analysis results with value bets."""
    db = _get_db()
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


@router.get("/stats-by-selection")
def get_stats_by_selection():
    """ROI breakdown by bet type (Local, Empate, Visitante, etc.)."""
    db = _get_db()
    return {"breakdown": db.get_stats_by_selection()}
