"""
WinStake.ia — Backtester Data Loader
Descarga y parsea datasets de temporadas pasadas desde football-data.co.uk
"""

import os
import requests
import logging
import csv
from datetime import datetime

logger = logging.getLogger(__name__)

# Mapeo de ligas a códigos de football-data.co.uk
# SP1 = La Liga, E0 = Premier League, I1 = Serie A, D1 = Bundesliga
LEAGUE_CODES = {
    "soccer_spain_la_liga": "SP1",
    "soccer_epl": "E0", 
    "soccer_italy_serie_a": "I1",
    "soccer_germany_bundesliga": "D1",
}

class DataLoader:
    def __init__(self, data_dir: str = "data/historical"):
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)

    def fetch_season_data(self, league_key: str, season_start_year: int) -> str:
        """
        Descarga el CSV de una temporada si no existe localmente.
        Ej: season_start_year=22 -> Temporada 2022-2023 (URL usa '2223')
        """
        code = LEAGUE_CODES.get(league_key)
        if not code:
            raise ValueError(f"Liga no soportada para backtesting libre: {league_key}")

        season_str = f"{season_start_year:02d}{season_start_year+1:02d}"
        filename = f"{code}_{season_str}.csv"
        filepath = os.path.join(self.data_dir, filename)

        if os.path.exists(filepath):
            logger.info(f"📁 Usando dataset local: {filename}")
            return filepath

        url = f"https://www.football-data.co.uk/mmz4281/{season_str}/{code}.csv"
        logger.info(f"🌐 Descargando histórico: {url}")
        
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            with open(filepath, 'wb') as f:
                f.write(response.content)
            logger.info(f"✅ Guardado en {filepath}")
            return filepath
        else:
            raise Exception(f"Error descargando CSV: Status {response.status_code}")

    def load_matches(self, filepath: str) -> list[dict]:
        """
        Lee el CSV y retorna una lista de diccionarios con los campos relevantes.
        """
        matches = []
        with open(filepath, 'r', encoding='latin1') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # football-data a veces tiene filas vacías al final
                if not row.get('Date') or not row.get('HomeTeam'):
                    continue
                    
                try:
                    # Cuotas: Pinnacle (PSH, PSD, PSA) o Bet365 (B365H, B365D, B365A) si Pinnacle no está
                    odd_h = float(row.get('PSH') or row.get('B365H') or 0)
                    odd_d = float(row.get('PSD') or row.get('B365D') or 0)
                    odd_a = float(row.get('PSA') or row.get('B365A') or 0)
                    
                    if odd_h == 0 or odd_d == 0 or odd_a == 0:
                        continue # Sin cuotas, saltar partido
                        
                    match = {
                        "date": row["Date"],
                        "home_team": row["HomeTeam"],
                        "away_team": row["AwayTeam"],
                        "home_goals": int(row["FTHG"]),
                        "away_goals": int(row["FTAG"]),
                        "result": row["FTR"], # H=Home, D=Draw, A=Away
                        "odds": {
                            "home": odd_h,
                            "draw": odd_d,
                            "away": odd_a
                        }
                    }
                    matches.append(match)
                except ValueError as e:
                    # Fila corrupta o incompleta
                    continue
                    
        return matches
