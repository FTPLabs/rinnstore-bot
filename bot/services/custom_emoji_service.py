"""ProtectStatus custom emoji catalog with DB-backed loading and safe fallbacks."""
from __future__ import annotations

from html import escape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import CustomEmoji

# Immutable fallback catalog: preserves current behavior if the DB is unavailable.
PROTECTSTATUS_EMOJIS: tuple[tuple[str, str], ...] = (
    ("5902016123972358349", "🛡"), ("5893365724830765382", "🛡"),
    ("5895652322469482989", "📱"), ("5893034681636491040", "📱"),
    ("5893442248263078309", "📱"), ("5895266423952904371", "📱"),
    ("5895514131896733546", "✅"), ("5893163582194978381", "❌"),
    ("5893081007153746175", "❌"), ("5895713431264170680", "✅"),
    ("5893197207493939355", "❌"), ("5893102202817352158", "🕞"),
    ("5902050947567194830", "⏰"), ("5893333516871012690", "✈️"),
    ("5893297890117292323", "📞"), ("5893255507380014983", "💼"),
    ("5893281616486209299", "💤"), ("5774138454896022007", "💤"),
    ("5893473283696759404", "💰"), ("5893382531037794941", "🔎"),
    ("5895440460322706085", "📌"), ("5893290369629556374", "💡"),
    ("5893100690988863311", "📱"), ("5892966078123872045", "🎶"),
    ("5895444149699612825", "📊"), ("5893072412924187198", "❗️"),
    ("5895338626648117927", "✌️"), ("5893376775781617954", "🏆"),
    ("5895770017458294953", "💫"), ("5893494861612455015", "⭐️"),
    ("5893450623449305489", "⚡️"), ("5893203503915996356", "⚡️"),
    ("5893048571560726748", "⚡️"), ("5893321843149902412", "✨"),
    ("5893185207355315979", "🔥"), ("5893080732275840699", "☀️"),
    ("5893402730268987918", "🍀"), ("5893162100431261050", "❄️"),
    ("5893293174243201165", "🕷"), ("5893311672667345793", "🦎"),
    ("5893464393114456544", "🐾"), ("5895213106228891182", "♥️"),
    ("5893401729541608160", "♥️"), ("5893406892092297627", "♥️"),
    ("5893365462837760511", "💱"), ("5902002809573740949", "✅"),
    ("5893224751119208859", "✅"), ("5895734085761896734", "©️"),
    ("5895401947350962540", "®️"), ("5893149782465057649", "🕞"),
    ("5893193062850499428", "📱"), ("5893370539489104568", "📱"),
    ("6039450035152753195", "🌐"), ("6039802097916974085", "🪙"),
    ("6039709013090768335", "🌐"), ("5902242339899838759", "🌐"),
    ("5904692292324692386", "⚠️"), ("5902056028513505203", "💳"),
    ("5902453596456227896", "➕"), ("5904238507555033712", "⛔️"),
    ("5904542823167824187", "🗑"), ("6041705726206808304", "🚀"),
    ("6039641775377748623", "👛"), ("5893161718179173515", "⚙️"),
    ("5902432207519093015", "⚙️"), ("5893431652578758294", "✅"),
    ("5893168654551355607", "✅"), ("5902335789798265487", "👤"),
    ("5902449142575141204", "🔗"), ("5893368370530621889", "🔜"),
)

_EMOJI_CACHE: dict[str, str] = dict(PROTECTSTATUS_EMOJIS)


async def seed_custom_emojis(session: AsyncSession) -> int:
    """Insert missing ProtectStatus records; never overwrite existing IDs."""
    result = await session.execute(select(CustomEmoji.custom_emoji_id))
    existing = set(result.scalars().all())
    added = 0
    for custom_emoji_id, emoji in PROTECTSTATUS_EMOJIS:
        if custom_emoji_id not in existing:
            session.add(CustomEmoji(
                custom_emoji_id=custom_emoji_id,
                pack_name="ProtectStatus",
                emoji=emoji,
            ))
            added += 1
    if added:
        await session.commit()
    return added


async def load_custom_emojis(session: AsyncSession) -> None:
    result = await session.execute(select(CustomEmoji))
    rows = result.scalars().all()
    _EMOJI_CACHE.clear()
    _EMOJI_CACHE.update(dict(PROTECTSTATUS_EMOJIS))
    for row in rows:
        _EMOJI_CACHE[row.custom_emoji_id] = row.emoji


def emoji_id(custom_emoji_id: str) -> str:
    """Return the DB-known ID, preserving the supplied ID as a fallback."""
    return custom_emoji_id if custom_emoji_id in _EMOJI_CACHE else custom_emoji_id


def emoji_html(custom_emoji_id: str, fallback: str | None = None) -> str:
    """Build Telegram HTML using the DB-backed emoji alternative."""
    alt = fallback or _EMOJI_CACHE.get(custom_emoji_id, "🙂")
    return f'<tg-emoji emoji-id="{escape(custom_emoji_id)}">{alt}</tg-emoji>'
