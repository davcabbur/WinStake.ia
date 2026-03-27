import sys
import logging
from fastapi import APIRouter, HTTPException

# Import the existing classes from src/
from src.odds_client import OddsClient
from src.football_client import FootballClient
from src.analyzer import Analyzer

router = APIRouter()
logger = logging.getLogger("WinStakeAPI")

@router.get("/")
def get_analysis_results():
    """Execute the core analysis logic and return value bets as JSON."""
    try:
        odds_client = OddsClient()
        football_client = FootballClient()
        analyzer = Analyzer()

        matches_odds = odds_client.get_upcoming_odds()
        if not matches_odds:
            raise HTTPException(status_code=404, detail="No upcoming odds could be fetched.")

        standings = football_client.get_standings()
        analyses = []

        for match in matches_odds:
            home = match["home_team"]
            away = match["away_team"]
            odds = match["avg_odds"]

            home_stats = football_client.find_team_in_standings(home, standings)
            away_stats = football_client.find_team_in_standings(away, standings)

            analysis = analyzer.analyze_match(
                home_team=home,
                away_team=away,
                odds=odds,
                home_stats=home_stats,
                away_stats=away_stats,
                commence_time=match.get("commence_time", ""),
            )
            
            # Solo devolver las apuestas con valor para el frontend
            if analysis.best_bet and analysis.best_bet.is_value:
                analyses.append({
                    "match": f"{home} vs {away}",
                    "commence_time": match.get("commence_time", ""),
                    "selection": analysis.best_bet.selection,
                    "odds": analysis.best_bet.odds,
                    "ev_percent": analysis.best_bet.ev_percent,
                    "recommended_stake": analysis.best_bet.recommended_stake
                })

        return {"status": "success", "value_bets": analyses, "total_analyzed": len(matches_odds)}

    except Exception as e:
        logger.error(f"Error executing analysis: {e}")
        raise HTTPException(status_code=500, detail=str(e))
