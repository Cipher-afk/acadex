from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from config import settings


class WhatsAppAPIError(RuntimeError):
    """Raised when Meta rejects a WhatsApp Cloud API request."""


class WhatsAppClient:
    """Small async client for the official WhatsApp Cloud API."""

    def __init__(self) -> None:
        if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
            raise RuntimeError("WhatsApp Cloud API credentials are not configured")

        self.base_url = (
            f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/"
            f"{settings.WHATSAPP_PHONE_NUMBER_ID}"
        )
        self.headers = {
            "Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}",
        }

    async def _request(self, method: str, url: str, **kwargs: Any) -> dict:
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.request(
                method, url, headers=self.headers, **kwargs
            )
        if response.is_error:
            raise WhatsAppAPIError(
                f"WhatsApp API returned {response.status_code}: {response.text}"
            )
        return response.json()

    async def send_text(self, to: str, text: str) -> dict:
        return await self._request(
            "POST",
            f"{self.base_url}/messages",
            json={
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": to,
                "type": "text",
                "text": {"preview_url": False, "body": text[:4096]},
            },
        )

    async def _upload_media(self, path: Path, mime_type: str) -> str:
        async with httpx.AsyncClient(timeout=120) as client:
            with path.open("rb") as file_handle:
                response = await client.post(
                    f"{self.base_url}/media",
                    headers=self.headers,
                    data={"messaging_product": "whatsapp"},
                    files={"file": (path.name, file_handle, mime_type)},
                )
        if response.is_error:
            raise WhatsAppAPIError(
                f"WhatsApp media upload failed ({response.status_code}): {response.text}"
            )
        return response.json()["id"]

    @staticmethod
    def _file_path(document: Any) -> Path:
        # Aiogram FSInputFile exposes its path; ordinary paths are also accepted.
        raw_path = getattr(document, "path", document)
        path = Path(raw_path)
        if not path.is_file():
            raise FileNotFoundError(f"Media file does not exist: {path}")
        return path

    async def send_document(
        self, to: str, document: Any, caption: str | None = None
    ) -> dict:
        path = self._file_path(document)
        media_id = await self._upload_media(path, "application/pdf" if path.suffix.lower() == ".pdf" else "application/octet-stream")
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "document",
            "document": {"id": media_id, "filename": path.name},
        }
        if caption:
            payload["document"]["caption"] = str(caption)[:1024]
        return await self._request("POST", f"{self.base_url}/messages", json=payload)

    async def send_photo(self, to: str, photo: Any, caption: str | None = None) -> dict:
        path = self._file_path(photo)
        suffix = path.suffix.lower()
        mime_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(suffix, "application/octet-stream")
        media_id = await self._upload_media(path, mime_type)
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {"id": media_id},
        }
        if caption:
            payload["image"]["caption"] = str(caption)[:1024]
        return await self._request("POST", f"{self.base_url}/messages", json=payload)
