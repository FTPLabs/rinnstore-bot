from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from decimal import Decimal
from ..utils.emoji import (
    BAG, ORDERS, PROMO, PROFILE, SUPPORT, SETTINGS,
    BACK, BROADCAST, LOCK, OK, REFRESH,
    OPEN_FOLDER, CATEGORY, KEY, COINS, CLOCK, WARN,
    CARD, LINK, plain,
)


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{plain(BAG)} Каталог", callback_data="catalog"),
        InlineKeyboardButton(text=f"{plain(ORDERS)} Мои заказы", callback_data="my_orders"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(PROMO)} Промокод", callback_data="promo"),
        InlineKeyboardButton(text=f"{plain(PROFILE)} Профиль", callback_data="profile"),
    )
    builder.row(InlineKeyboardButton(text=f"{plain(SUPPORT)} Поддержка", callback_data="support"))
    if is_admin:
        builder.row(InlineKeyboardButton(text=f"{plain(SETTINGS)} Админ-панель", callback_data="admin_main"))
    return builder.as_markup()


def profile_kb(ref_code: str, bot_username: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    ref_link = f"https://t.me/{bot_username}?start={ref_code}"
    builder.row(InlineKeyboardButton(text=f"{plain(LINK)} Моя реф. ссылка", url=ref_link))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Меню", callback_data="main_menu"))
    return builder.as_markup()


def welcome_kb(channel_invite: str, tos_url: str, pp_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"{plain(BROADCAST)} Подписаться на канал", url=channel_invite))
    builder.row(
        InlineKeyboardButton(text=f"{plain(ORDERS)} Соглашение", url=tos_url),
        InlineKeyboardButton(text=f"{plain(LOCK)} Конфиденц.", url=pp_url),
    )
    builder.row(InlineKeyboardButton(text=f"{plain(OK)} Принимаю условия", callback_data="accept_terms"))
    return builder.as_markup()


def channel_only_kb(channel_invite: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"{plain(BROADCAST)} Вступить в канал", url=channel_invite))
    builder.row(InlineKeyboardButton(text=f"{plain(OK)} Я подписан", callback_data="check_channel"))
    return builder.as_markup()


def captcha_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"{plain(REFRESH)} Новая картинка", callback_data="refresh_captcha"))
    return builder.as_markup()


def terms_kb(pp_url: str, tos_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{plain(ORDERS)} Соглашение", url=tos_url),
        InlineKeyboardButton(text=f"{plain(LOCK)} Конфиденц.", url=pp_url),
    )
    builder.row(InlineKeyboardButton(text=f"{plain(OK)} Принимаю и продолжаю", callback_data="accept_terms"))
    return builder.as_markup()


def channel_kb(channel: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    channel_url = channel if channel.startswith("http") else f"https://t.me/{channel.lstrip('@')}"
    builder.row(InlineKeyboardButton(text=f"{plain(BROADCAST)} Вступить в канал", url=channel_url))
    builder.row(InlineKeyboardButton(text=f"{plain(OK)} Проверить подписку", callback_data="check_channel"))
    return builder.as_markup()


def catalog_kb(categories: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(InlineKeyboardButton(
            text=f"{plain(OPEN_FOLDER)} {cat.name}",
            callback_data=f"cat_{cat.id}"
        ))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="main_menu"))
    return builder.as_markup()


def subcatalog_kb(subcategories: list, back_cb: str = "catalog") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in subcategories:
        builder.row(InlineKeyboardButton(
            text=f"{plain(CATEGORY)} {cat.name}",
            callback_data=f"subcat_{cat.id}"
        ))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data=back_cb))
    return builder.as_markup()


def products_kb(products: list, cat_id: int, parent_cat_id: int | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        builder.row(InlineKeyboardButton(
            text=f"{plain(KEY)} {product.name} — {product.price} ₽",
            callback_data=f"prod_{product.id}"
        ))
    back_cb = f"subcat_{parent_cat_id}" if parent_cat_id else "catalog"
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data=back_cb))
    return builder.as_markup()


def payment_method_kb(
    order_id: int,
    user_balance: "Decimal | None" = None,
    rollypay_enabled: bool = True,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="₿ CryptoBot (USDT)",
        callback_data=f"pay_crypto_{order_id}",
    ))
    if rollypay_enabled:
        builder.row(InlineKeyboardButton(
            text=f"{plain(CARD)} СБП / RollyPay (RUB)",
            callback_data=f"pay_rollypay_{order_id}",
        ))
    if user_balance is not None and user_balance > Decimal("0"):
        builder.row(InlineKeyboardButton(
            text=f"{plain(COINS)} Баланс ({user_balance:.2f} ₽)",
            callback_data=f"pay_balance_{order_id}",
        ))
    builder.row(InlineKeyboardButton(
        text="✕ Отмена",
        callback_data=f"cancel_order_{order_id}",
    ))
    return builder.as_markup()


def payment_link_kb(pay_url: str, order_id: int, provider: str = "crypto") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    btn_text = f"{plain(CARD)} Перейти к оплате (СБП)" if provider == "rollypay" else "₿ Оплатить"
    builder.row(InlineKeyboardButton(text=btn_text, url=pay_url))
    builder.row(
        InlineKeyboardButton(
            text=f"{plain(OK)} Проверить оплату",
            callback_data=f"check_payment_{order_id}_{provider}",
        ),
        InlineKeyboardButton(
            text="✕ Отмена",
            callback_data=f"cancel_order_{order_id}",
        ),
    )
    return builder.as_markup()


def orders_kb(orders: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    status_icon = {
        "pending": plain(CLOCK),
        "paid": plain(OK),
        "cancelled": "✕",
        "delivered": plain(KEY),
        "partial": plain(WARN),
    }
    for order in orders:
        icon = status_icon.get(order.status, plain(WARN))
        builder.row(InlineKeyboardButton(
            text=f"{icon} #{order.id} — {order.total_amount} ₽",
            callback_data=f"order_{order.id}",
        ))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="main_menu"))
    return builder.as_markup()


def order_detail_kb(order_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status in ("paid", "delivered", "partial"):
        builder.row(InlineKeyboardButton(
            text=f"{plain(KEY)} Получить товар",
            callback_data=f"get_items_{order_id}",
        ))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="my_orders"))
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Меню", callback_data="main_menu"))
    return builder.as_markup()
