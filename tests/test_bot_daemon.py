import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.bot_daemon import (
    start_command, ping_command, roi_command, _analizar_sport,
    laliga_command, analizar_command, _LALIGA_DISABLED_MSG,
    _format_scheduled_picks_message, _execute_nba_analysis,
    _daily_nba_analysis_task,
)

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
    # Simula que _run_analysis.. retorna (analyses, lineup_updates) vacíos
    mock_run.return_value = ({}, {})
    
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
    mock_run.return_value = ({"test_match": analysis_mock}, {})
    
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


@pytest.mark.asyncio
@patch("src.bot_daemon._analizar_sport")
async def test_laliga_command_disabled(mock_analizar):
    update = MagicMock()
    update.message = AsyncMock()
    context = MagicMock()

    await laliga_command(update, context)

    mock_analizar.assert_not_called()
    update.message.reply_text.assert_called_once_with(_LALIGA_DISABLED_MSG)
    assert "desactivada temporalmente" in _LALIGA_DISABLED_MSG


@pytest.mark.asyncio
@patch("src.bot_daemon._analizar_sport")
async def test_analizar_command_disabled(mock_analizar):
    update = MagicMock()
    update.message = AsyncMock()
    context = MagicMock()

    await analizar_command(update, context)

    mock_analizar.assert_not_called()
    update.message.reply_text.assert_called_once_with(_LALIGA_DISABLED_MSG)


def _make_analysis_mock(home="Lakers", away="Celtics", is_value=True, ev=5.0, odds=1.95, sel="home"):
    from src.analyzer import MatchAnalysis
    analysis = MagicMock(spec=MatchAnalysis)
    analysis.home_team = home
    analysis.away_team = away
    analysis.commence_time = "2026-05-25T23:00:00Z"
    analysis.match_id = f"{home}_{away}"
    if is_value:
        bb = MagicMock()
        bb.is_value = True
        bb.selection = sel
        bb.odds = odds
        bb.ev_percent = ev
        bb.confidence = "HIGH"
        analysis.best_bet = bb
    else:
        analysis.best_bet = None
    return analysis


def test_format_scheduled_with_picks():
    analysis = _make_analysis_mock(ev=7.5)
    analyses = {analysis.match_id: analysis}
    msg = _format_scheduled_picks_message(analyses, total_matches=3, value_picks_count=1)

    assert "Análisis NBA automático" in msg
    assert "3 partidos" in msg
    assert "1 value picks" in msg
    assert "Lakers vs Celtics" in msg
    assert "EV +7.5%" in msg
    assert "Picks persistidos" in msg


def test_format_scheduled_zero_value():
    analysis = _make_analysis_mock(is_value=False)
    analyses = {analysis.match_id: analysis}
    msg = _format_scheduled_picks_message(analyses, total_matches=2, value_picks_count=0)

    assert "0 picks con value" in msg
    assert "2 partidos analizados" in msg
    assert "/nba" in msg
    assert "Lakers vs Celtics" not in msg


@pytest.mark.asyncio
@patch("src.bot_daemon._execute_nba_analysis", new_callable=AsyncMock)
@patch("src.bot_daemon.asyncio.sleep", new_callable=AsyncMock)
async def test_daily_task_silent_when_zero_matches(mock_sleep, mock_execute):
    mock_execute.return_value = {
        "analyses": {}, "lineup_updates": {}, "sorted_matches": [],
        "keyboard": [], "total_matches": 0, "value_picks_count": 0,
        "injury_report": None,
    }
    # After first sleep+execute, raise CancelledError to exit the loop
    mock_sleep.side_effect = [None, asyncio.CancelledError()]

    app = MagicMock()
    app.bot.send_message = AsyncMock()

    await _daily_nba_analysis_task(app)

    app.bot.send_message.assert_not_called()


@pytest.mark.asyncio
@patch("src.bot_daemon._execute_nba_analysis", new_callable=AsyncMock)
@patch("src.bot_daemon.asyncio.sleep", new_callable=AsyncMock)
async def test_daily_task_sends_message_with_matches(mock_sleep, mock_execute):
    analysis = _make_analysis_mock(ev=6.0)
    mock_execute.return_value = {
        "analyses": {analysis.match_id: analysis},
        "lineup_updates": {},
        "sorted_matches": [analysis],
        "keyboard": [],
        "total_matches": 1,
        "value_picks_count": 1,
        "injury_report": None,
    }
    mock_sleep.side_effect = [None, asyncio.CancelledError()]

    app = MagicMock()
    app.bot.send_message = AsyncMock()

    await _daily_nba_analysis_task(app)

    app.bot.send_message.assert_called_once()
    sent_text = app.bot.send_message.call_args.kwargs.get("text", "")
    assert "Lakers vs Celtics" in sent_text


@pytest.mark.asyncio
@patch("src.bot_daemon._execute_nba_analysis", new_callable=AsyncMock)
@patch("src.bot_daemon.asyncio.sleep", new_callable=AsyncMock)
async def test_daily_task_sends_injury_report_when_present(mock_sleep, mock_execute):
    analysis = _make_analysis_mock(ev=4.5)
    mock_execute.return_value = {
        "analyses": {analysis.match_id: analysis},
        "lineup_updates": {},
        "sorted_matches": [analysis],
        "keyboard": [],
        "total_matches": 1,
        "value_picks_count": 1,
        "injury_report": "Injury: Player X out",
    }
    mock_sleep.side_effect = [None, asyncio.CancelledError()]

    app = MagicMock()
    app.bot.send_message = AsyncMock()

    await _daily_nba_analysis_task(app)

    assert app.bot.send_message.call_count == 2
    injury_text = app.bot.send_message.call_args_list[1].kwargs.get("text", "")
    assert "Injury" in injury_text


@pytest.mark.asyncio
@patch("src.bot_daemon._execute_nba_analysis", new_callable=AsyncMock)
@patch("src.bot_daemon.asyncio.sleep", new_callable=AsyncMock)
async def test_daily_task_recovers_from_error(mock_sleep, mock_execute):
    mock_execute.side_effect = [RuntimeError("API down"), asyncio.CancelledError()]
    mock_sleep.side_effect = [None, None, asyncio.CancelledError()]

    app = MagicMock()
    app.bot.send_message = AsyncMock()

    await _daily_nba_analysis_task(app)

    app.bot.send_message.assert_not_called()
    # sleep called: initial wait + error recovery wait
    assert mock_sleep.call_count >= 2

