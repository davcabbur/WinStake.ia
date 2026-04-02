"""
WinStake.ia — Telegram Bot Daemon
Ejecuta el bot en modo "long-polling" para recibir comandos interactivos.
"""

import logging
import asyncio
from datetime import datetime

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from src.database import Database
from main import main as run_analysis
from src.logger_config import setup_logging

logger = setup_logging("WinStakeBot")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador para /start o /help."""
    msg = (
        "🤖 <b>WinStake.ia Interactive Bot</b>\n\n"
        "Comandos disponibles:\n"
        "🔹 /analizar - Ejecutar un análisis de la jornada ahora\n"
        "🔹 /roi - Consultar tu Bankroll y ROI histórico\n"
        "🔹 /ping - Verificar estado del motor\n"
    )
    await update.message.reply_html(msg)

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manejador para /ping."""
    await update.message.reply_text("✅ Motor WinStake.ia operativo y esperando ordenes.")

async def roi_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Consulta en SQLite el ROI actual y lo devuelve."""
    db = Database()
    roi = db.get_roi_summary()
    
    if roi["total_bets"] == 0:
        await update.message.reply_text("📉 Todavía no hay apuestas registradas en la base de datos.")
        return

    msg = (
        f"📊 <b>Resumen de Rendimiento</b>\n\n"
        f"💰 <b>Total Apuestas:</b> {roi['total_bets']}\n"
        f"✅ <b>Ganadas:</b> {roi['wins']}\n"
        f"❌ <b>Perdidas:</b> {roi['losses']}\n"
        f"💵 <b>Profit Neto:</b> {roi['total_profit']:+.2f} unidades\n"
        f"📈 <b>ROI:</b> {roi['roi_percent']:+.2f}%\n"
    )
    await update.message.reply_html(msg)

async def analizar_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lanza el análisis del modelo de predicción (bloqueante manejado en thread para no colgar asyncio)."""
    await update.message.reply_text("⏳ Iniciando análisis cuantitativo de las ligas configuradas. Esto puede tardar unos segundos...")

    try:
        # Ejecutamos 'run_analysis' en un hilo separado para no bloquear el loop del bot
        # Pasamos [] como args para evitar que argparse lea sys.argv del daemon
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: run_analysis([]))
        # Nota: main() ya se encarga de formatear y enviar los resultados de vuelta a Telegram si hay value.
        await update.message.reply_text("✅ Análisis completado. (Si no recibes pronósticos, es que no hay value bets reales)")
    except (SystemExit, RuntimeError) as e:
        logger.error(f"Error en análisis: {e}")
        await update.message.reply_text(f"⚠️ Análisis finalizado con error: {e}")
    except Exception as e:
        logger.error(f"Error forzando análisis: {e}", exc_info=True)
        await update.message.reply_text("❌ Hubo un error ejecutando el modelo matemático. Revisa los logs.")


def main():
    """Inicia el demonio del bot."""
    token = config.TELEGRAM_BOT_TOKEN
    
    if not token or token == "tu_token_aqui":
        logger.error("🛑 TELEGRAM_BOT_TOKEN no configurado en '.env'. Abortando demonio del bot.")
        return

    application = Application.builder().token(token).build()

    # Comandos
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", start_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("roi", roi_command))
    application.add_handler(CommandHandler("analizar", analizar_command))

    logger.info("🚀 WinStake.ia Bot Daemon iniciado. Escuchando comandos de Telegram...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
