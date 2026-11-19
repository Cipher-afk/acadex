from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from whatsapp.client import WhatsAppClient


@dataclass
class WhatsAppChat:
    id: str


class WhatsAppMessage:
    """Compatibility surface for the Message methods used by scraper_file.py."""

    def __init__(self, phone_number: str, client: WhatsAppClient):
        self.chat = WhatsAppChat(id=phone_number)
        self.from_user = type("WhatsAppUser", (), {"id": phone_number})()
        self._client = client

    async def answer(self, text: str, **_: Any) -> dict:
        # reply_markup/parse_mode are Telegram-specific and intentionally ignored.
        return await self._client.send_text(self.chat.id, str(text))


class WhatsAppBot:
    """Compatibility surface for the Bot methods used by scraper_file.py."""

    def __init__(self, client: WhatsAppClient):
        self._client = client

    async def send_message(self, chat_id: str, text: str, **_: Any) -> dict:
        return await self._client.send_text(str(chat_id), str(text))

    async def send_document(
        self, chat_id: str, document: Any, caption: str | None = None, **_: Any
    ) -> dict:
        return await self._client.send_document(str(chat_id), document, caption)

    async def send_photo(
        self, chat_id: str, photo: Any, caption: str | None = None, **_: Any
    ) -> dict:
        return await self._client.send_photo(str(chat_id), photo, caption)
