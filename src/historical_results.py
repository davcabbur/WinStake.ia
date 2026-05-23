"""
Fetch retroactivo de resultados NBA para poblar match_outcomes.

Uso:
    python -m src.historical_results --sport=nba --season=2025-26
"""

import argparse
import logging
import sqlite3
import time
from datetime import date, datetime, timedelta, timezone

logger = logging.getLogger(__name__)

DB_PATH = "data/winstake.db"

# Nombres que difieren entre nba_api y nuestra BD
_NAME_MAP = {
    "LA Clippers": "Los Angeles Clippers",
}


def fetch_nba_season_results(season: str = "2025-26") -> list[dict]:
    """
    Descarga todos los partidos NBA de la temporada desde nba_api.
    Devuelve lista de dicts: game_date, home_team, away_team, home_score,
    away_score, total_score, winner ('home'/'away').
    """
    from nba_api.stats.endpoints import leaguegamefinder

    logger.info(f"Descargando temporada NBA {season} desde nba_api...")
    finder = leaguegamefinder.LeagueGameFinder(
        season_nullable=season,
        league_id_nullable="00",
    )
    df = finder.get_data_frames()[0]
    logger.info(f"  {len(df)} filas (2 por partido) descargadas.")

    games: dict[str, dict] = {}
    for _, row in df.iterrows():
        gid = row["GAME_ID"]
        is_home = "vs." in row["MATCHUP"]
        entry = games.setdefault(gid, {"game_date": row["GAME_DATE"], "home": None, "away": None})
        side = "home" if is_home else "away"
        team_name = _NAME_MAP.get(row["TEAM_NAME"], row["TEAM_NAME"])
        entry[side] = {"team": team_name, "pts": row["PTS"]}

    results = []
    for g in games.values():
        if g["home"] is None or g["away"] is None:
            continue
        home_score = int(g["home"]["pts"]) if g["home"]["pts"] is not None else None
        away_score = int(g["away"]["pts"]) if g["away"]["pts"] is not None else None
        winner = None
        if home_score is not None and away_score is not None:
            winner = "home" if home_score > away_score else "away"
        results.append({
            "game_date":   g["game_date"],
            "home_team":   g["home"]["team"],
            "away_team":   g["away"]["team"],
            "home_score":  home_score,
            "away_score":  away_score,
            "total_score": (home_score + away_score) if (home_score and away_score) else None,
            "winner":      winner,
        })

    logger.info(f"  {len(results)} partidos unicos reconstruidos.")
    return results


def match_games(
    pending_games: list[dict],
    nba_games: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Para cada partido único pendiente busca su resultado en nba_games.
    Devuelve (matched, unmatched).

    Nota: commence_time se almacena en UTC; nba_api devuelve GAME_DATE en
    hora local US. Partidos nocturnos (>= ~20:00 ET) aparecen como el día
    siguiente en UTC → se intenta también con game_date - 1 día.
    """
    index: dict[tuple, dict] = {}
    for g in nba_games:
        key = (g["home_team"], g["away_team"], g["game_date"])
        index[key] = g

    matched: list[dict] = []
    unmatched: list[dict] = []

    for p in pending_games:
        home, away, gd = p["home_team"], p["away_team"], p["game_date"]
        game = index.get((home, away, gd))
        if game is None:
            prev = (date.fromisoformat(gd) - timedelta(days=1)).isoformat()
            game = index.get((home, away, prev))
        if game:
            matched.append(game)
        else:
            unmatched.append(p)

    return matched, unmatched


def persist_outcomes(
    games: list[dict],
    db_path: str = DB_PATH,
    source: str = "nba_api",
) -> dict:
    """
    Inserta partidos en match_outcomes.
    Idempotente: INSERT OR IGNORE por UNIQUE(home_team, away_team, game_date).
    Devuelve stats: total, inserted, skipped.
    """
    conn = sqlite3.connect(db_path)
    fetched_at = datetime.now(timezone.utc).isoformat()

    inserted = 0
    skipped = 0

    for g in games:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO match_outcomes
                (home_team, away_team, game_date, home_score, away_score,
                 total_score, winner, fetched_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                g["home_team"],
                g["away_team"],
                g["game_date"],
                g["home_score"],
                g["away_score"],
                g["total_score"],
                g["winner"],
                fetched_at,
                source,
            ),
        )
        if cur.rowcount == 1:
            inserted += 1
        else:
            skipped += 1

    conn.commit()
    conn.close()

    return {"total": len(games), "inserted": inserted, "skipped": skipped}


def _load_pending_games(db_path: str = DB_PATH, sport: str = "nba") -> list[dict]:
    """
    Devuelve partidos únicos (home_team, away_team, game_date) del deporte dado
    que aún no tienen fila en match_outcomes.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT DISTINCT a.home_team, a.away_team, DATE(a.commence_time) AS game_date
        FROM analyses a
        LEFT JOIN match_outcomes mo
               ON mo.home_team = a.home_team
              AND mo.away_team = a.away_team
              AND mo.game_date = DATE(a.commence_time)
        WHERE a.sport = ? AND mo.id IS NULL
        ORDER BY game_date, a.home_team
        """,
        (sport,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def run(sport: str = "nba", season: str = "2025-26", db_path: str = DB_PATH):
    t0 = time.time()

    pending = _load_pending_games(db_path, sport)
    logger.info(f"Partidos unicos pendientes: {len(pending)}")

    if not pending:
        logger.info("Nada que resolver.")
        return

    nba_games = fetch_nba_season_results(season)

    matched, unmatched = match_games(pending, nba_games)
    logger.info(f"Matches encontrados: {len(matched)} / {len(pending)}")
    logger.info(f"Sin match: {len(unmatched)}")

    if unmatched:
        logger.warning("Partidos sin match:")
        for p in unmatched:
            logger.warning(f"  {p['game_date']}  {p['home_team']} vs {p['away_team']}")

    stats = persist_outcomes(matched, db_path=db_path, source=source if (source := "nba_api") else "nba_api")
    elapsed = time.time() - t0

    print(f"\nRESULTADO")
    print(f"  Partidos pendientes : {len(pending)}")
    print(f"  Partidos en API     : {len(nba_games)}")
    print(f"  Matches             : {len(matched)}")
    print(f"  Sin match           : {len(unmatched)}")
    print(f"  Insertados          : {stats['inserted']}")
    print(f"  Ignorados (ya exist): {stats['skipped']}")
    print(f"  Tiempo              : {elapsed:.1f}s")

    if unmatched:
        print(f"\nPartidos sin match ({len(unmatched)}):")
        for p in unmatched:
            print(f"  {p['game_date']}  {p['home_team']} vs {p['away_team']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport",  default="nba")
    parser.add_argument("--season", default="2025-26")
    parser.add_argument("--db",     default=DB_PATH)
    args = parser.parse_args()
    run(sport=args.sport, season=args.season, db_path=args.db)
