import logging
from fastapi import APIRouter, HTTPException, Query

from src.odds_client import OddsClient
from src.football_client import FootballClient
from src.nba_client import NBAClient
from src.analyzer import Analyzer
from src.sports.config import get_sport, SPORTS

router = APIRouter()
logger = logging.getLogger("WinStakeAPI")


@router.get("/")
def get_analysis_results(
    sport: str = Query("laliga", description="Deporte a analizar", enum=list(SPORTS.keys())),
):
    """Execute the core analysis logic and return ALL value bets as JSON."""
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
        logger.error(f"Error executing analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")
