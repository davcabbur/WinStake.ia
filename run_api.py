"""
WinStake.ia — Dashboard Launcher
"""
import uvicorn
import logging

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("🚀 Iniciando WinStake.ia Dashboard API...")
    uvicorn.run("src.api.app:app", host="0.0.0.0", port=8000, reload=True)
