from fastapi import APIRouter, Depends, HTTPException
import sqlite3
from pydantic import BaseModel
from src.database import DB_PATH, Database
from src.api.auth import require_api_key


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
def get_dashboard_stats():
    """Devuelve estadísticas agregadas de ROI, winrate y profit."""
    conn = get_db_connection()
    try:
        # Calcular ROI real desde match_results y value_bets
        cursor = conn.execute("""
            SELECT 
                COUNT(*) as total_bets,
                SUM(CASE WHEN bet_won = 1 THEN 1 ELSE 0 END) as won_bets,
                SUM(profit_units) as total_profit
            FROM match_results
        """)
        row = cursor.fetchone()
        
        total_bets = row["total_bets"] or 0
        won_bets = row["won_bets"] or 0
        total_profit = row["total_profit"] or 0.0
        win_rate = (won_bets / total_bets * 100) if total_bets > 0 else 0.0

        return {
            "total_bets": total_bets,
            "won_bets": won_bets,
            "win_rate": round(win_rate, 2),
            "total_profit": round(total_profit, 2)
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
