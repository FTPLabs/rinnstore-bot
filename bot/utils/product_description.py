"""Safe serialization of product descriptions with Telegram entities."""
from __future__ import annotations

import html

from aiogram.types import Message

_DESCRIPTION_HTML_PREFIX = "telegram-html:v1:"


def product_description_from_message(message: Message) -> str:
    """Persist an admin message as Telegram HTML, preserving custom emoji entities."""
    text = (message.text or "").strip()
    if text == "-":
        return ""
    # Aiogram converts MessageEntity(type="custom_emoji") to Telegram's
    # supported <tg-emoji emoji-id="…">…</tg-emoji> representation.
    return _DESCRIPTION_HTML_PREFIX + (message.html_text or "").strip()


def product_description_to_html(value: str | None) -> str:
    """Render a stored description without interpreting legacy plain text as HTML."""
    if not value:
        return ""
    if value.startswith(_DESCRIPTION_HTML_PREFIX):
        return value.removeprefix(_DESCRIPTION_HTML_PREFIX)
    return html.escape(value)
