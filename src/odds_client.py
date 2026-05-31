"""
WinStake.ia — Cliente de The Odds API
Obtiene cuotas de mercado para La Liga desde The Odds API v4.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

import config
from src.cache import APICache

logger = logging.getLogger(__name__)


def _create_session(retries: int = 3, backoff_factor: float = 0.5) -> requests.Session:
    """Crea una sesión HTTP con retry y backoff exponencial."""
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,  # 0.5s, 1s, 2s
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def resolve_odds_source(match: dict) -> tuple[dict, Optional[dict]]:
    """
    Devuelve (odds, bookmaker_meta) según el feature flag USE_RAW_ODDS.

    USE_RAW_ODDS=1 → chosen_book_odds (cuota cruda del libro elegido) y
                     chosen_book_meta (mapa market_key → bookmaker).
    USE_RAW_ODDS=0 → avg_odds (trimmed mean — comportamiento histórico) y
                     bookmaker_meta=None (la convención legacy se resuelve
                     en Database._resolve_legacy_bookmaker).

    Extraído para testabilidad: el switch se testea contra esta función sin
    mockear todo el pipeline de main.py / bot_daemon.py.
    """
    if config.USE_RAW_ODDS:
        return match["chosen_book_odds"], match["chosen_book_meta"]
    return match["avg_odds"], None


class OddsClient:
    """Cliente para The Odds API v4. Soporta múltiples deportes."""

    def __init__(self, api_key: str = None, sport_config=None):
        self.api_key = api_key or config.ODDS_API_KEY
        self.base_url = config.ODDS_API_BASE
        self.cache = APICache()
        self.session = _create_session()

        # Sport config (default: La Liga para compatibilidad)
        self.sport_config = sport_config
        self.sport_key = sport_config.odds_sport_key if sport_config else config.SPORT_KEY
        self.odds_markets = sport_config.odds_markets if sport_config else config.ODDS_MARKETS
        self.odds_regions = sport_config.odds_regions if sport_config else config.ODDS_REGIONS
        self.matchday_window = sport_config.matchday_window_days if sport_config else 7
        self.matchday_span = sport_config.matchday_span_days if sport_config else 4

        if not self.api_key or self.api_key == "tu_clave_aqui":
            logger.warning("⚠️  ODDS_API_KEY no configurada. No se obtendrán cuotas reales.")

    def get_upcoming_odds(self) -> list[dict]:
        """
        Obtiene cuotas para los próximos partidos del deporte configurado.
        Retorna lista de partidos con cuotas promedio por resultado.
        """
        if not self.api_key or self.api_key == "tu_clave_aqui":
            logger.error("❌ ODDS_API_KEY no configurada — no se obtienen cuotas reales")
            return []

        # Intentar caché primero
        cache_key = f"odds_{self.sport_key}"
        cached = self.cache.get(cache_key, config.CACHE_TTL_ODDS)
        if cached is not None:
            logger.info(f"✅ Cuotas desde caché ({len(cached)} partidos) — 0 requests usadas")
            return cached

        try:
            url = f"{self.base_url}/sports/{self.sport_key}/odds"
            params = {
                "apiKey": self.api_key,
                "regions": self.odds_regions,
                "markets": self.odds_markets,
                "oddsFormat": config.ODDS_FORMAT,
            }
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()

            raw_data = response.json()
            remaining = response.headers.get("x-requests-remaining", "?")
            logger.info(f"✅ Odds API: {len(raw_data)} partidos. Requests restantes: {remaining}")

            parsed = self._parse_odds(raw_data)

            # Filtrar solo partidos de la próxima jornada
            parsed = self._filter_next_matchday(
                parsed,
                window_days=self.matchday_window,
                span_days=self.matchday_span,
            )
            logger.info(f"📅 Tras filtro de jornada: {len(parsed)} partidos")

            # Guardar en caché
            self.cache.set(cache_key, parsed)
            logger.info(f"💾 Cuotas guardadas en caché (TTL: {config.CACHE_TTL_ODDS // 60}min)")

            return parsed

        except requests.exceptions.HTTPError as e:
            logger.error(f"❌ Odds API HTTP error: {e}")
            if e.response.status_code == 401:
                logger.error("   → API key inválida. Verifica ODDS_API_KEY en .env")
            elif e.response.status_code == 429:
                logger.error("   → Límite de requests alcanzado (500/mes en plan gratuito)")
            return []
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Odds API connection error: {e}")
            return []

    @staticmethod
    def _filter_next_matchday(
        matches: list[dict],
        window_days: int = 7,
        span_days: int = 4,
    ) -> list[dict]:
        """
        Filtra partidos para mostrar solo la próxima jornada/día.

        Args:
            window_days: Ventana máxima para buscar partidos futuros.
            span_days: Duración de una jornada (4 para fútbol Vie-Lun, 1 para NBA).
        """
        if not matches:
            return matches

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=window_days)

        # 1. Filtrar partidos futuros dentro de la ventana
        future = []
        for m in matches:
            ct = m.get("commence_time", "")
            if not ct:
                continue
            try:
                dt = datetime.fromisoformat(ct.replace("Z", "+00:00"))
                if now - timedelta(hours=2) <= dt <= cutoff:
                    m["_dt"] = dt
                    future.append(m)
            except (ValueError, TypeError):
                continue

        if not future:
            return matches  # Fallback: devolver todo

        # 2. Ordenar por fecha
        future.sort(key=lambda m: m["_dt"])

        # 3. Agrupar: desde el primer partido, tomar todos dentro de span_days
        first_dt = future[0]["_dt"]
        matchday_end = first_dt + timedelta(days=span_days)

        result = []
        for m in future:
            if m["_dt"] <= matchday_end:
                m.pop("_dt", None)
                result.append(m)

        return result

    def _parse_odds(self, raw_data: list[dict]) -> list[dict]:
        """Parsea respuesta de la API y calcula cuotas promedio por resultado."""
        matches = []

        for event in raw_data:
            match = {
                "id": event.get("id"),
                "home_team": event.get("home_team"),
                "away_team": event.get("away_team"),
                "commence_time": event.get("commence_time"),
                "odds_h2h": {"home": [], "draw": [], "away": []},
                "odds_totals": {"over_15": [], "under_15": [], "over_25": [], "under_25": [], "over_35": [], "under_35": [], "over_main": [], "under_main": [], "main_line": []},
                "odds_btts": {"yes": [], "no": []},
                "odds_double_chance": {"1x": [], "x2": [], "12": []},
                "odds_spreads": {"home": [], "away": [], "home_points": [], "away_points": []},
                "bookmakers_count": 0,
            }

            bookmakers = event.get("bookmakers", [])
            match["bookmakers_count"] = len(bookmakers)

            # Tracking de cuota cruda por mercado: (bm_key, price, line|None).
            # Preserva el orden de aparición de los bookmakers en la respuesta.
            # Se usa en la pasada 3 para construir chosen_book_odds (cuota
            # cruda del libro elegido, sin promediar).
            raw_books_by_market: dict[str, list[tuple[str, float, Optional[float]]]] = {
                k: [] for k in (
                    "home", "draw", "away",
                    "double_chance_1x", "double_chance_x2", "double_chance_12",
                    "over_15", "under_15",
                    "over_25", "under_25",
                    "over_35", "under_35",
                    "over_main", "under_main",
                    "btts_yes", "btts_no",
                    "spread_home", "spread_away",
                )
            }

            for bm in bookmakers:
                bm_key = bm.get("key", "unknown")
                for market in bm.get("markets", []):
                    if market["key"] == "h2h":
                        for o in market.get("outcomes", []):
                            if o["name"] == event["home_team"]:
                                match["odds_h2h"]["home"].append(o["price"])
                                raw_books_by_market["home"].append((bm_key, o["price"], None))
                            elif o["name"] == event["away_team"]:
                                match["odds_h2h"]["away"].append(o["price"])
                                raw_books_by_market["away"].append((bm_key, o["price"], None))
                            elif o["name"] == "Draw":
                                match["odds_h2h"]["draw"].append(o["price"])
                                raw_books_by_market["draw"].append((bm_key, o["price"], None))

                    elif market["key"] == "totals":
                        for o in market.get("outcomes", []):
                            point = o.get("point", 2.5)
                            if o["name"] == "Over":
                                if point == 1.5:
                                    match["odds_totals"]["over_15"].append(o["price"])
                                    raw_books_by_market["over_15"].append((bm_key, o["price"], 1.5))
                                elif point == 2.5:
                                    match["odds_totals"]["over_25"].append(o["price"])
                                    raw_books_by_market["over_25"].append((bm_key, o["price"], 2.5))
                                elif point == 3.5:
                                    match["odds_totals"]["over_35"].append(o["price"])
                                    raw_books_by_market["over_35"].append((bm_key, o["price"], 3.5))
                                # Linea principal generica (NBA: ~224.5, etc.)
                                if point > 50:
                                    match["odds_totals"]["over_main"].append(o["price"])
                                    match["odds_totals"]["main_line"].append(point)
                                    raw_books_by_market["over_main"].append((bm_key, o["price"], point))
                            elif o["name"] == "Under":
                                if point == 1.5:
                                    match["odds_totals"]["under_15"].append(o["price"])
                                    raw_books_by_market["under_15"].append((bm_key, o["price"], 1.5))
                                elif point == 2.5:
                                    match["odds_totals"]["under_25"].append(o["price"])
                                    raw_books_by_market["under_25"].append((bm_key, o["price"], 2.5))
                                elif point == 3.5:
                                    match["odds_totals"]["under_35"].append(o["price"])
                                    raw_books_by_market["under_35"].append((bm_key, o["price"], 3.5))
                                if point > 50:
                                    match["odds_totals"]["under_main"].append(o["price"])
                                    raw_books_by_market["under_main"].append((bm_key, o["price"], point))

                    elif market["key"] == "spreads":
                        for o in market.get("outcomes", []):
                            point = o.get("point", 0)
                            if o["name"] == event["home_team"]:
                                match["odds_spreads"]["home"].append(o["price"])
                                match["odds_spreads"]["home_points"].append(point)
                                raw_books_by_market["spread_home"].append((bm_key, o["price"], point))
                            elif o["name"] == event["away_team"]:
                                match["odds_spreads"]["away"].append(o["price"])
                                match["odds_spreads"]["away_points"].append(point)
                                raw_books_by_market["spread_away"].append((bm_key, o["price"], point))

                    elif market["key"] == "btts":
                        for o in market.get("outcomes", []):
                            if o["name"] == "Yes":
                                match["odds_btts"]["yes"].append(o["price"])
                                raw_books_by_market["btts_yes"].append((bm_key, o["price"], None))
                            elif o["name"] == "No":
                                match["odds_btts"]["no"].append(o["price"])
                                raw_books_by_market["btts_no"].append((bm_key, o["price"], None))

                    elif market["key"] == "double_chance":
                        for o in market.get("outcomes", []):
                            name = o["name"]
                            if name == f"{event['home_team']} or Draw":
                                match["odds_double_chance"]["1x"].append(o["price"])
                                raw_books_by_market["double_chance_1x"].append((bm_key, o["price"], None))
                            elif name == f"{event['away_team']} or Draw":
                                match["odds_double_chance"]["x2"].append(o["price"])
                                raw_books_by_market["double_chance_x2"].append((bm_key, o["price"], None))
                            elif "Draw" not in name:
                                match["odds_double_chance"]["12"].append(o["price"])
                                raw_books_by_market["double_chance_12"].append((bm_key, o["price"], None))

            # ── Extraer cuotas específicas de Bet365 ──────────────
            bet365_h2h = {"home": None, "away": None, "draw": None}
            bet365_spread = {"home": None, "away": None, "line": None}
            for bm in bookmakers:
                if bm.get("key") == "bet365":
                    for market in bm.get("markets", []):
                        if market["key"] == "h2h":
                            for o in market.get("outcomes", []):
                                if o["name"] == event["home_team"]:
                                    bet365_h2h["home"] = o["price"]
                                elif o["name"] == event["away_team"]:
                                    bet365_h2h["away"] = o["price"]
                                elif o["name"] == "Draw":
                                    bet365_h2h["draw"] = o["price"]
                        elif market["key"] == "spreads":
                            for o in market.get("outcomes", []):
                                if o["name"] == event["home_team"]:
                                    bet365_spread["home"] = o["price"]
                                    bet365_spread["line"] = o.get("point", 0)
                                elif o["name"] == event["away_team"]:
                                    bet365_spread["away"] = o["price"]
                    break  # Solo un bet365

            match["bet365_odds"] = {
                "h2h_home": bet365_h2h["home"],
                "h2h_draw": bet365_h2h["draw"],
                "h2h_away": bet365_h2h["away"],
                "spread_home": bet365_spread["home"],
                "spread_away": bet365_spread["away"],
                "spread_line": bet365_spread["line"],
                "available": bet365_h2h["home"] is not None or bet365_spread["home"] is not None,
            }

            # Calcular cuotas promedio (filtrando outliers)
            match["avg_odds"] = {
                # Moneyline: Bet365 si disponible, si no media recortada
                "home": bet365_h2h["home"] if bet365_h2h["home"] is not None else self._trimmed_mean(match["odds_h2h"]["home"]),
                "draw": bet365_h2h["draw"] if bet365_h2h["draw"] is not None else self._trimmed_mean(match["odds_h2h"]["draw"]),
                "away": bet365_h2h["away"] if bet365_h2h["away"] is not None else self._trimmed_mean(match["odds_h2h"]["away"]),
                "double_chance_1x": self._trimmed_mean(match["odds_double_chance"]["1x"]),
                "double_chance_x2": self._trimmed_mean(match["odds_double_chance"]["x2"]),
                "double_chance_12": self._trimmed_mean(match["odds_double_chance"]["12"]),
                "over_15": self._trimmed_mean(match["odds_totals"]["over_15"]),
                "under_15": self._trimmed_mean(match["odds_totals"]["under_15"]),
                "over_25": self._trimmed_mean(match["odds_totals"]["over_25"]),
                "under_25": self._trimmed_mean(match["odds_totals"]["under_25"]),
                "over_35": self._trimmed_mean(match["odds_totals"]["over_35"]),
                "under_35": self._trimmed_mean(match["odds_totals"]["under_35"]),
                "btts_yes": self._trimmed_mean(match["odds_btts"]["yes"]),
                "btts_no": self._trimmed_mean(match["odds_btts"]["no"]),
                # Spreads: Bet365 si disponible, si no media recortada
                "spread_home": bet365_spread["home"] if bet365_spread["home"] is not None else self._trimmed_mean(match["odds_spreads"]["home"]),
                "spread_away": bet365_spread["away"] if bet365_spread["away"] is not None else self._trimmed_mean(match["odds_spreads"]["away"]),
            }

            # Calcular spread_line: Bet365 preferido, si no media del mercado
            if bet365_spread["line"] is not None:
                match["avg_odds"]["spread_line"] = float(bet365_spread["line"])
            elif match["odds_spreads"]["home_points"]:
                match["avg_odds"]["spread_line"] = round(
                    sum(match["odds_spreads"]["home_points"])
                    / len(match["odds_spreads"]["home_points"]), 1
                )
            else:
                match["avg_odds"]["spread_line"] = 0.0

            # Totals principal: para NBA usa linea alta (>50), para futbol usa 2.5
            if match["odds_totals"]["over_main"]:
                match["avg_odds"]["over"] = self._trimmed_mean(match["odds_totals"]["over_main"])
                match["avg_odds"]["under"] = self._trimmed_mean(match["odds_totals"]["under_main"])
                match["avg_odds"]["total_line"] = round(
                    sum(match["odds_totals"]["main_line"])
                    / len(match["odds_totals"]["main_line"]), 1
                )
            else:
                match["avg_odds"]["over"] = match["avg_odds"].get("over_25")
                match["avg_odds"]["under"] = match["avg_odds"].get("under_25")
                match["avg_odds"]["total_line"] = 2.5

            # ── Pasada 3: chosen_book_odds + chosen_book_meta ────
            # Para cada mercado, elegimos la cuota cruda del libro:
            #   1) Bet365 si aparece para ese mercado
            #   2) Si no, el primer book con datos (orden de aparición)
            # NO se promedia: se devuelve la cuota tal cual la cotizaba el libro,
            # incluyendo la línea (spread/total) cuando aplique.
            #
            # Mercados pareados (spread_home/away+line, over/under+total_line):
            # SIEMPRE del MISMO bookmaker. Una combinación de cuotas de libros
            # distintos NO es apostable. Si no hay un único libro que cubra
            # ambos lados, las 3 keys (cuotas + línea) quedan a None.
            def _pick_chosen(entries):
                if not entries:
                    return None, None, None
                for bm_key_, price, line in entries:
                    if bm_key_ == "bet365":
                        return bm_key_, price, line
                return entries[0]

            def _pick_chosen_pair(home_entries, away_entries):
                """
                Para mercados de dos lados, elige UN único bookmaker que cubra
                ambos. Prioriza Bet365; si no, el primer book (en orden de
                aparición en home_entries) que también esté en away_entries.
                Devuelve (bm_key, home_entry, away_entry) o (None,None,None).
                """
                home_books = {bm for bm, _, _ in home_entries}
                away_books = {bm for bm, _, _ in away_entries}
                common = home_books & away_books
                if not common:
                    return None, None, None
                if "bet365" in common:
                    chosen = "bet365"
                else:
                    chosen = next((bm for bm, _, _ in home_entries if bm in common), None)
                if chosen is None:
                    return None, None, None
                home_entry = next(e for e in home_entries if e[0] == chosen)
                away_entry = next(e for e in away_entries if e[0] == chosen)
                return chosen, home_entry, away_entry

            def _dedupe_to_market_main(entries):
                """
                Si un mismo book publica varias líneas alternativas (típico en
                NBA), quedarse con la entrada cuya línea esté más cerca de la
                mediana global de líneas vistas en el mercado.

                Justificación del criterio (mediana vs precio cercano a 1.91):
                la mediana captura el consenso de mercado entre todos los
                libros y es robusta a outliers (un libro con línea anómala
                no la mueve). Un criterio basado en "precio más balanceado"
                depende del vig específico de cada libro y daría resultados
                sesgados cuando los libros aplican márgenes asimétricos.
                """
                if not entries:
                    return entries
                lines = [line for _, _, line in entries if line is not None]
                if not lines:
                    return entries
                sorted_lines = sorted(lines)
                n = len(sorted_lines)
                if n % 2 == 1:
                    median_line = sorted_lines[n // 2]
                else:
                    median_line = (sorted_lines[n // 2 - 1] + sorted_lines[n // 2]) / 2
                # Por book: la entrada con línea más cercana a la mediana
                by_book: dict = {}
                for e in entries:
                    bm, _, line = e
                    best = by_book.get(bm)
                    if best is None or abs(line - median_line) < abs(best[2] - median_line):
                        by_book[bm] = e
                # Preservar orden de primera aparición de cada book
                seen, out = set(), []
                for e in entries:
                    bm = e[0]
                    if bm not in seen:
                        out.append(by_book[bm])
                        seen.add(bm)
                return out

            chosen_book_odds: dict = {}
            chosen_book_meta: dict = {}

            # Mercados sin acoplamiento entre lados o líneas
            for mk in (
                "home", "draw", "away",
                "double_chance_1x", "double_chance_x2", "double_chance_12",
                "over_15", "under_15", "over_25", "under_25", "over_35", "under_35",
                "btts_yes", "btts_no",
            ):
                bm_, price_, _line_ = _pick_chosen(raw_books_by_market[mk])
                chosen_book_odds[mk] = price_
                chosen_book_meta[mk] = bm_

            # ── Spreads acoplados: spread_home + spread_away + spread_line ──
            sp_bm, sp_h, sp_a = _pick_chosen_pair(
                raw_books_by_market["spread_home"],
                raw_books_by_market["spread_away"],
            )
            if sp_bm is not None:
                chosen_book_odds["spread_home"] = sp_h[1]
                chosen_book_odds["spread_away"] = sp_a[1]
                chosen_book_odds["spread_line"] = sp_h[2]
                chosen_book_meta["spread_home"] = sp_bm
                chosen_book_meta["spread_away"] = sp_bm
                chosen_book_meta["spread_line"] = sp_bm
            else:
                for k in ("spread_home", "spread_away", "spread_line"):
                    chosen_book_odds[k] = None
                    chosen_book_meta[k] = None

            # ── Totals acoplados: over + under + total_line ──
            # NBA prioriza over_main/under_main (línea variable, dedup por mediana).
            # Fútbol cae a over_25/under_25 con línea fija 2.5 (también pareado).
            over_main_d  = _dedupe_to_market_main(raw_books_by_market["over_main"])
            under_main_d = _dedupe_to_market_main(raw_books_by_market["under_main"])

            tot_bm, tot_o, tot_u = _pick_chosen_pair(over_main_d, under_main_d)
            if tot_bm is not None:
                chosen_book_odds["over"]       = tot_o[1]
                chosen_book_odds["under"]      = tot_u[1]
                chosen_book_odds["total_line"] = tot_o[2]
                chosen_book_meta["over"]       = tot_bm
                chosen_book_meta["under"]      = tot_bm
                chosen_book_meta["total_line"] = tot_bm
            else:
                # Fallback fútbol: over_25 + under_25 del mismo libro, línea fija 2.5
                fb_bm, fb_o, fb_u = _pick_chosen_pair(
                    raw_books_by_market["over_25"],
                    raw_books_by_market["under_25"],
                )
                if fb_bm is not None:
                    chosen_book_odds["over"]       = fb_o[1]
                    chosen_book_odds["under"]      = fb_u[1]
                    chosen_book_odds["total_line"] = 2.5
                    chosen_book_meta["over"]       = fb_bm
                    chosen_book_meta["under"]      = fb_bm
                    chosen_book_meta["total_line"] = fb_bm
                else:
                    for k in ("over", "under", "total_line"):
                        chosen_book_odds[k] = None
                        chosen_book_meta[k] = None

            match["chosen_book_odds"] = chosen_book_odds
            match["chosen_book_meta"] = chosen_book_meta

            matches.append(match)

        return matches

    @staticmethod
    def _trimmed_mean(values: list[float]) -> Optional[float]:
        """Media recortada: elimina el valor más alto y más bajo si hay 4+ datos."""
        if not values:
            return None
        if len(values) < 4:
            return round(sum(values) / len(values), 2)

        sorted_vals = sorted(values)
        trimmed = sorted_vals[1:-1]  # Quita extremos
        return round(sum(trimmed) / len(trimmed), 2)

