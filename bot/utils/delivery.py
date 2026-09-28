"""Formatting helpers for delivered digital goods."""
from __future__ import annotations

import html
from collections.abc import Iterable
from typing import Any

from .emoji import KEY


def format_delivered_items(items: Iterable[dict[str, Any]]) -> str:
    """Return Telegram-safe HTML for secret values sent to the purchaser."""
    return "\n".join(
        f"{KEY} <code>{html.escape(str(item['data']))}</code>"
        for item in items
    )
