"""Receipt uploads from the Mini App.

The file is checked by its first bytes (not the browser's content type), then sent
once to the owner's own bot chat. That gives a Telegram file_id, so admins receive
the receipt exactly like one sent in the bot. Duplicate detection uses a content
hash, which catches the same file uploaded again by anyone.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile, Message

from app.services.payments import Receipt

MAX_RECEIPT_BYTES = 10 * 1024 * 1024
HASH_PREFIX = "sha256:"


class ReceiptError(Exception):
    """Upload problem shown to the owner by code."""

    def __init__(self, code: str, status: int = 400) -> None:
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class Upload:
    data: bytes
    ext: str
    kind: str  # "photo" for images, "document" for PDF

    @property
    def digest(self) -> str:
        return HASH_PREFIX + hashlib.sha256(self.data).hexdigest()


def sniff(data: bytes) -> tuple[str, str] | None:
    """(extension, kind) for JPEG, PNG, WebP or PDF; None for anything else."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg", "photo"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", "photo"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "photo"
    if data.startswith(b"%PDF-"):
        return "pdf", "document"
    return None


def check_upload(data: bytes) -> Upload:
    if not data:
        raise ReceiptError("receipt")
    if len(data) > MAX_RECEIPT_BYTES:
        raise ReceiptError("too_large", 413)
    found = sniff(data)
    if found is None:
        raise ReceiptError("bad_type", 415)
    return Upload(data, found[0], found[1])


async def read_part(part, limit: int = MAX_RECEIPT_BYTES) -> bytes:
    """Read one multipart part, stopping as soon as it passes `limit`."""
    chunks: list[bytes] = []
    size = 0
    while True:
        chunk = await part.read_chunk(256 * 1024)
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise ReceiptError("too_large", 413)
        chunks.append(chunk)
    return b"".join(chunks)


async def store_receipt(bot: Bot | None, chat_id: int, upload: Upload, caption: str) -> Receipt:
    """Send the file to the owner's bot chat and return its Telegram ids plus content hash."""
    if bot is None:
        raise ReceiptError("unavailable", 503)
    name = f"receipt.{upload.ext}"
    try:
        message = await _send(bot, chat_id, upload, name, caption)
    except TelegramForbiddenError as exc:
        raise ReceiptError("start_bot", 409) from exc
    except TelegramBadRequest as exc:
        raise ReceiptError("bad_type", 415) from exc
    file_id, kind = _file_of(message)
    if not file_id:
        raise ReceiptError("unavailable", 503)
    return Receipt(file_id=file_id, unique_id=upload.digest, kind=kind)


async def _send(bot: Bot, chat_id: int, upload: Upload, name: str, caption: str) -> Message:
    if upload.kind == "photo":
        try:
            return await bot.send_photo(
                chat_id, BufferedInputFile(upload.data, name), caption=caption
            )
        except TelegramBadRequest:
            pass  # odd dimensions or format: keep the original as a file instead
    return await bot.send_document(chat_id, BufferedInputFile(upload.data, name), caption=caption)


def _file_of(message: Message) -> tuple[str | None, str]:
    if message.photo:
        return message.photo[-1].file_id, "photo"
    if message.document is not None:
        return message.document.file_id, "document"
    return None, "photo"
