import asyncio
import json
import random
import logging
from typing import List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

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
            await emit_mock_odds()
            while True:
                # Keep connection alive, wait for client messages if needed
                data = await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket)

    @app.on_event("startup")
    async def startup_event():
        # Iniciar el emisor de cuotas en background
        asyncio.create_task(odds_generator_task())


async def emit_mock_odds():
    """Genera una actualización simulada de cuotas y la envía vía WebSocket."""
    # Simulamos fluctuación de cuotas de mercado (para ahorrar API requests)
    matches = [
        {"id": "mat_1", "home": "Real Madrid", "away": "Barcelona", "home_odd": round(random.uniform(2.10, 2.30), 2), "away_odd": round(random.uniform(2.80, 3.10), 2), "draw_odd": round(random.uniform(3.20, 3.50), 2)},
        {"id": "mat_2", "home": "Atlético Madrid", "away": "Sevilla", "home_odd": round(random.uniform(1.60, 1.80), 2), "away_odd": round(random.uniform(4.50, 5.00), 2), "draw_odd": round(random.uniform(3.40, 3.80), 2)},
        {"id": "mat_3", "home": "Real Betis", "away": "Valencia", "home_odd": round(random.uniform(2.00, 2.20), 2), "away_odd": round(random.uniform(3.20, 3.60), 2), "draw_odd": round(random.uniform(3.10, 3.30), 2)},
    ]
    
    payload = {
        "type": "odds_update",
        "matches": matches,
        "timestamp": asyncio.get_event_loop().time()
    }
    
    await manager.broadcast(payload)

async def odds_generator_task():
    """Ciclo infinito que genera actualizaciones de cuotas."""
    while True:
        await asyncio.sleep(5)  # Actualizar cada 5 segundos
        if manager.active_connections:
            await emit_mock_odds()
