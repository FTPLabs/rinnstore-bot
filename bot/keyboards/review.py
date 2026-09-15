from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def rating_kb(review_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(*[
        InlineKeyboardButton(text=str(n), callback_data=f"review_rate_{review_id}_{n}", icon_custom_emoji_id="5893494861612455015", style="primary")
        for n in range(1, 6)
    ])
    builder.row(InlineKeyboardButton(text="🛒 Купить свой ключ", callback_data="catalog", style="primary"))
    return builder.as_markup()


def comment_kb(review_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="Пропустить комментарий", icon_custom_emoji_id="5893368370530621889", style="primary",
        callback_data=f"review_skip_{review_id}",
    ))
    builder.row(InlineKeyboardButton(text="🛒 Купить свой ключ", callback_data="catalog", style="primary"))
    return builder.as_markup()
