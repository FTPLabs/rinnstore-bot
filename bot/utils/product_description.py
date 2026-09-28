"""Safe serialization of product descriptions with Telegram entities."""
from __future__ import annotations

import html
import re

from aiogram.types import Message

from ..services.custom_emoji_service import PROTECTSTATUS_EMOJIS, emoji_html

_DESCRIPTION_HTML_PREFIX = "telegram-html:v1:"
_CUSTOM_EMOJI_TAG_RE = re.compile(r"(<tg-emoji\b[^>]*>.*?</tg-emoji>)", re.DOTALL)
_PREMIUM_BY_UNICODE: dict[str, str] = {}
for _custom_id, _fallback in PROTECTSTATUS_EMOJIS:
    _PREMIUM_BY_UNICODE.setdefault(_fallback, _custom_id)
_PREMIUM_EMOJI_RE = re.compile(
    "|".join(re.escape(value) for value in sorted(_PREMIUM_BY_UNICODE, key=len, reverse=True))
)


def _upgrade_plain_emoji_html(value: str) -> str:
    """Replace known Unicode emoji outside existing Telegram emoji tags."""
    if not value or not _PREMIUM_BY_UNICODE:
        return value

    def replace_plain(part: str) -> str:
        return _PREMIUM_EMOJI_RE.sub(
            lambda match: emoji_html(_PREMIUM_BY_UNICODE[match.group(0)], match.group(0)),
            part,
        )

    pieces = _CUSTOM_EMOJI_TAG_RE.split(value)
    return "".join(piece if index % 2 else replace_plain(piece) for index, piece in enumerate(pieces))


def product_description_from_message(message: Message) -> str:
    """Persist admin text with Telegram custom emoji entities and auto-premium emoji."""
    text = (message.text or "").strip()
    if text == "-":
        return ""
    # Aiogram converts native Telegram custom emoji entities to supported HTML.
    html_text = (message.html_text or "").strip()
    return _DESCRIPTION_HTML_PREFIX + _upgrade_plain_emoji_html(html_text)


def product_description_to_html(value: str | None) -> str:
    """Render stored descriptions, upgrading legacy Unicode emoji to premium emoji."""
    if not value:
        return ""
    if value.startswith(_DESCRIPTION_HTML_PREFIX):
        return _upgrade_plain_emoji_html(value.removeprefix(_DESCRIPTION_HTML_PREFIX))
    return _upgrade_plain_emoji_html(html.escape(value))
