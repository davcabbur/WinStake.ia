import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot_daemon import start_command, ping_command, roi_command, _analizar_sport

@pytest.mark.asyncio
async def test_start_command():
    update = MagicMock()
    update.message = AsyncMock()
    context = MagicMock()
    
    await start_command(update, context)
    update.message.reply_html.assert_called_once()
    args, _ = update.message.reply_html.call_args
    assert "WinStake.ia" in args[0]
    assert "/laliga" in args[0]

@pytest.mark.asyncio
async def test_ping_command():
    update = MagicMock()
    update.message = AsyncMock()
    context = MagicMock()
    
    await ping_command(update, context)
    update.message.reply_text.assert_called_once()
    args, _ = update.message.reply_text.call_args
    assert "Motor WinStake.ia operativo" in args[0]

@pytest.mark.asyncio
@patch("src.bot_daemon.Database")
async def test_roi_command_empty(mock_db_class):
    update = MagicMock()
    update.message = AsyncMock()
    context = MagicMock()
    
    mock_db = mock_db_class.return_value
    mock_db.get_roi_summary.return_value = {"total_bets": 0, "roi_percent": 0.0}
    
    await roi_command(update, context)
    update.message.reply_text.assert_called_once()
    assert "todavía no hay apuestas" in update.message.reply_text.call_args[0][0].lower()


@pytest.mark.asyncio
@patch("src.bot_daemon.Database")
async def test_roi_command_with_data(mock_db_class):
    update = MagicMock()
    update.message = AsyncMock()
    context = MagicMock()
    
    mock_db = mock_db_class.return_value
    mock_db.get_roi_summary.return_value = {
        "total_bets": 5, "wins": 3, "losses": 2, 
        "total_profit": 5.5, "win_rate": 60, "total_staked": 10,
        "roi_percent": 55, "avg_ev": 10.5
    }
    
    await roi_command(update, context)
    update.message.reply_html.assert_called_once()
    text = update.message.reply_html.call_args[0][0]
    assert "Resumen de Rendimiento" in text
    assert "Total Apuestas:</b> 5" in text


@pytest.mark.asyncio
@patch("src.bot_daemon._run_analysis_for_jornada")
async def test_analizar_sport_no_matches(mock_run):
    # Simula que _run_analysis.. retorna un dict vacio
    mock_run.return_value = {}
    
    update = MagicMock()
    update.message = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    context = MagicMock()
    
    await _analizar_sport(update, context, "laliga")
    
    assert update.message.reply_text.call_count == 2
    assert "Analizando" in update.message.reply_text.call_args_list[0][0][0]
    assert "No se encontraron partidos" in update.message.reply_text.call_args_list[1][0][0]


@pytest.mark.asyncio
@patch("src.bot_daemon._run_analysis_for_jornada")
async def test_analizar_sport_with_matches(mock_run):
    from src.analyzer import MatchAnalysis
    
    # Crea un Mock rudimentario para MatchAnalysis
    analysis_mock = MagicMock(spec=MatchAnalysis)
    analysis_mock.best_bet = None
    analysis_mock.home_team = "Local"
    analysis_mock.away_team = "Visitante"
    analysis_mock.commence_time = "2026-04-04T18:30:00Z"
    analysis_mock.match_id = "test_match"
    
    # 1 partido en los resultados funcionales
    mock_run.return_value = {"test_match": analysis_mock}
    
    update = MagicMock()
    update.message = AsyncMock()
    update.effective_chat = MagicMock()
    update.effective_chat.id = 12345
    context = MagicMock()
    
    await _analizar_sport(update, context, "laliga")
    
    # Deberia enviar un HTML con los botones por lo que reply_html se dispara
    assert update.message.reply_html.call_count == 1
    
    args, kwargs = update.message.reply_html.call_args
    assert "Local vs Visitante" in str(kwargs.get("reply_markup"))
