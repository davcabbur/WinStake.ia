import asyncio
import json
import logging
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src.odds_client import OddsClient

logger = logging.getLogger(__name__)

_odds_client = OddsClient()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected to Live Odds. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
            
        json_msg = json.dumps(message)
        failed_connections = []
        
        for connection in self.active_connections:
            try:
                await connection.send_text(json_msg)
            except Exception as e:
                logger.error(f"Error sending message to client: {e}")
                failed_connections.append(connection)
                
        # Cleanup failed connections
        for conn in failed_connections:
            self.disconnect(conn)

manager = ConnectionManager()

def setup_websockets(app: FastAPI):
    """Configura el endpoint de WebSockets en FastAPI e inicia el background task."""
    
    @app.websocket("/api/ws/odds")
    async def websocket_endpoint(websocket: WebSocket):
        await manager.connect(websocket)
        try:
            # Enviar initial payload
            await emit_real_odds()
            while True:
                # Keep connection alive, wait for client messages if needed
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    @app.on_event("startup")
    async def startup_event():
        # Iniciar el emisor de cuotas en background
        asyncio.create_task(odds_generator_task())


async def emit_real_odds():
    """Obtiene cuotas reales desde OddsClient (caché en disco) y las emite vía WebSocket."""
    try:
        loop = asyncio.get_event_loop()
        matches_raw = await loop.run_in_executor(None, _odds_client.get_upcoming_odds)

        matches = []
        for m in matches_raw:
            avg_odds = m.get("avg_odds") or {}
            home_odd = avg_odds.get("home")
            away_odd = avg_odds.get("away")
            # Skip matches without the minimum usable odds
            if home_odd is None or away_odd is None:
                continue
            matches.append({
                "id": m.get("id"),
                "home": m.get("home_team"),
                "away": m.get("away_team"),
                "home_odd": home_odd,
                "away_odd": away_odd,
                "draw_odd": avg_odds.get("draw"),  # May be None; frontend handles null
            })

        payload = {
            "type": "odds_update",
            "matches": matches,
            "timestamp": asyncio.get_event_loop().time(),
        }
    except Exception as e:
        logger.error(f"Error fetching real odds for WebSocket broadcast: {e}")
        payload = {
            "type": "odds_update",
            "matches": [],
            "timestamp": asyncio.get_event_loop().time(),
        }

    await manager.broadcast(payload)

async def odds_generator_task():
    """Ciclo infinito que emite actualizaciones de cuotas reales."""
    while True:
        await asyncio.sleep(60)  # Cuotas en caché ~30min; 60s es suficiente
        if manager.active_connections:
            await emit_real_odds()
