from ..utils.custom_emoji import emoji_id
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


BUY_URL = "https://t.me/rinnnstore_bot?start=catalog"
BUY_EMOJI_ID = "5893382531037794941"


def rating_kb(review_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(*[
        InlineKeyboardButton(
            text=str(n), callback_data=f"review_rate_{review_id}_{n}",
            icon_custom_emoji_id=emoji_id("5893494861612455015"), style="primary",
        ) for n in range(1, 6)
    ])
    builder.row(InlineKeyboardButton(text="Купить свой ключ", url=BUY_URL, icon_custom_emoji_id=BUY_EMOJI_ID, style="primary"))
    return builder.as_markup()


def anonymity_kb(review_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Публично", callback_data=f"review_anonymous_{review_id}_0", style="primary"),
        InlineKeyboardButton(text="Анонимно", callback_data=f"review_anonymous_{review_id}_1", style="primary"),
    )
    return builder.as_markup()


def comment_kb(review_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="Пропустить комментарий", icon_custom_emoji_id=emoji_id("5893368370530621889"), style="primary",
        callback_data=f"review_skip_{review_id}",
    ))
    builder.row(InlineKeyboardButton(text="Купить свой ключ", url=BUY_URL, icon_custom_emoji_id=BUY_EMOJI_ID, style="primary"))
    return builder.as_markup()


def moderation_kb(review_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="✅ Одобрить и запостить в канал",
            callback_data=f"review_approve_{review_id}", style="success",
        ),
        InlineKeyboardButton(
            text="❌ Отклонить", callback_data=f"review_reject_{review_id}", style="danger",
        ),
    )
    return builder.as_markup()
