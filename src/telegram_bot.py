"""
WinStake.ia — Bot de Telegram
Envía análisis formateados a un chat de Telegram.
"""

import asyncio
import logging

from telegram import Bot
from telegram.constants import ParseMode

import config

logger = logging.getLogger(__name__)


class TelegramSender:
    """Envía mensajes al bot de Telegram."""

    def __init__(self, token: str = None, chat_id: str = None):
        self.token = token or config.TELEGRAM_BOT_TOKEN
        self.chat_id = chat_id or config.TELEGRAM_CHAT_ID

        if not self.token or self.token == "tu_token_aqui":
            logger.warning("⚠️  TELEGRAM_BOT_TOKEN no configurado.")
            self._mock_mode = True
        elif not self.chat_id or self.chat_id == "tu_chat_id_aqui":
            logger.warning("⚠️  TELEGRAM_CHAT_ID no configurado.")
            self._mock_mode = True
        else:
            self._mock_mode = False
            self.bot = Bot(token=self.token)

    def send_messages(self, messages: list[str]) -> bool:
        """
        Envía una lista de mensajes a Telegram (sync wrapper).
        Divide mensajes que excedan 4096 chars.
        """
        if self._mock_mode:
            return self._mock_send(messages)

        try:
            asyncio.run(self._send_async(messages))
            return True
        except Exception as e:
            logger.error(f"❌ Error enviando a Telegram: {e}")
            return False

    async def _send_async(self, messages: list[str]):
        """Envía mensajes de forma asíncrona."""
        for i, msg in enumerate(messages):
            chunks = self._split_message(msg)
            for chunk in chunks:
                try:
                    await self.bot.send_message(
                        chat_id=self.chat_id,
                        text=chunk,
                        parse_mode=ParseMode.HTML,
                        disable_web_page_preview=True,
                    )
                    logger.info(f"✅ Mensaje {i+1}/{len(messages)} enviado ({len(chunk)} chars)")
                except Exception as e:
                    logger.error(f"❌ Error en mensaje {i+1}: {e}")
                    # Reintentar sin formato
                    try:
                        await self.bot.send_message(
                            chat_id=self.chat_id,
                            text=self._strip_html(chunk),
                            disable_web_page_preview=True,
                        )
                        logger.info(f"✅ Mensaje {i+1} reenviado sin formato")
                    except Exception as e2:
                        logger.error(f"❌ Fallo definitivo en mensaje {i+1}: {e2}")

            # Pausa entre mensajes para evitar rate limit
            if i < len(messages) - 1:
                await asyncio.sleep(1)

    @staticmethod
    def _split_message(text: str, max_length: int = 4096) -> list[str]:
        """Divide un mensaje largo en chunks de max_length."""
        if len(text) <= max_length:
            return [text]

        chunks = []
        while text:
            if len(text) <= max_length:
                chunks.append(text)
                break

            # Buscar último salto de línea antes del límite
            split_pos = text.rfind("\n", 0, max_length)
            if split_pos == -1:
                split_pos = max_length

            chunks.append(text[:split_pos])
            text = text[split_pos:].lstrip("\n")

        return chunks

    @staticmethod
    def _strip_html(text: str) -> str:
        """Elimina tags HTML para envío fallback."""
        import re
        return re.sub(r"<[^>]+>", "", text)

    def _mock_send(self, messages: list[str]) -> bool:
        """Modo sin Telegram: imprime en consola."""
        logger.info("🔧 Modo desarrollo: mensajes impresos en consola\n")
        print("\n" + "=" * 60)
        print("  TELEGRAM OUTPUT (modo desarrollo)")
        print("=" * 60)

        for i, msg in enumerate(messages):
            clean_msg = self._strip_html(msg)
            print(f"\n--- Mensaje {i+1}/{len(messages)} ---")
            print(clean_msg)

        print("\n" + "=" * 60)
        return True
