"""
WinStake.ia — Verificación Automática de Resultados
Consulta resultados reales de API-Football y cierra value bets pendientes.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from src.football_client import FootballClient
from src.database import Database

logger = logging.getLogger(__name__)


class ResultVerifier:
    """Verifica automáticamente resultados de partidos y calcula profit/loss."""

    def __init__(self):
        self.football_client = FootballClient()
        self.db = Database()

    def verify_pending(self) -> dict:
        """
        Verifica todas las value bets pendientes contra resultados reales.

        Returns:
            Dict con resumen: bets verificadas, profit total, errores
        """
        pending = self.db.get_pending_results()

        if not pending:
            logger.info("No hay value bets pendientes de verificación.")
            return {"verified": 0, "profit": 0.0, "errors": 0, "still_pending": 0}

        logger.info(f"Verificando {len(pending)} value bets pendientes...")

        # Obtener fixtures recientes (últimos 7 días)
        recent_results = self._fetch_recent_results()

        if not recent_results:
            logger.warning("No se pudieron obtener resultados recientes.")
            return {"verified": 0, "profit": 0.0, "errors": 0, "still_pending": len(pending)}

        verified = 0
        total_profit = 0.0
        errors = 0
        still_pending = 0

        for bet in pending:
            home = bet["home_team"]
            away = bet["away_team"]

            result = self._find_result(home, away, recent_results)

            if result is None:
                still_pending += 1
                logger.debug(f"   Pendiente: {home} vs {away} — sin resultado aún")
                continue

            try:
                hg = result["home_goals"]
                ag = result["away_goals"]
                profit = self.db.record_result(bet["bet_id"], hg, ag)
                total_profit += profit
                verified += 1

                icon = "✅" if profit > 0 else "❌"
                logger.info(
                    f"   {icon} {home} vs {away} ({hg}-{ag}) → "
                    f"{bet['selection']} @ {bet['odds']:.2f} → {profit:+.1f}u"
                )
            except Exception as e:
                errors += 1
                logger.error(f"   Error verificando {home} vs {away}: {e}")

        summary = {
            "verified": verified,
            "profit": round(total_profit, 2),
            "errors": errors,
            "still_pending": still_pending,
        }

        logger.info(
            f"\nVerificación completada: {verified} verificadas, "
            f"{total_profit:+.1f}u profit, {still_pending} pendientes"
        )

        return summary

    def _fetch_recent_results(self, days: int = 7) -> list[dict]:
        """Obtiene resultados de partidos recientes desde API-Football."""
        import config
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        to_date = datetime.now().strftime("%Y-%m-%d")

        data = self.football_client._request("fixtures", {
            "league": config.LA_LIGA_ID,
            "season": config.CURRENT_SEASON,
            "from": from_date,
            "to": to_date,
            "status": "FT",  # Solo partidos terminados
        })

        if not data:
            return []

        results = []
        try:
            for fix in data.get("response", []):
                results.append({
                    "home_team": fix["teams"]["home"]["name"],
                    "away_team": fix["teams"]["away"]["name"],
                    "home_goals": fix["goals"]["home"],
                    "away_goals": fix["goals"]["away"],
                    "date": fix["fixture"]["date"],
                })
        except (KeyError, TypeError) as e:
            logger.error(f"Error parseando resultados: {e}")

        logger.info(f"Obtenidos {len(results)} resultados de los últimos {days} días")
        return results

    def _find_result(
        self, home_team: str, away_team: str, results: list[dict]
    ) -> Optional[dict]:
        """Busca el resultado de un partido por nombres de equipo (fuzzy)."""
        home_lower = home_team.lower()
        away_lower = away_team.lower()

        for result in results:
            r_home = result["home_team"].lower()
            r_away = result["away_team"].lower()

            # Match directo o parcial
            home_match = home_lower in r_home or r_home in home_lower
            away_match = away_lower in r_away or r_away in away_lower

            if home_match and away_match:
                return result

        return None

def verify_results():
    """Entry point para verificación desde CLI o scheduler."""
    verifier = ResultVerifier()
    return verifier.verify_pending()
