from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from decimal import Decimal
from ..utils.emoji import (
    BAG, ORDERS, PROMO, PROFILE, SUPPORT, SETTINGS,
    BACK, BROADCAST, LOCK, OK, REFRESH,
    OPEN_FOLDER, CATEGORY, KEY, COINS, CLOCK, WARN,
    CARD, LINK, plain,
)
from ..utils.i18n import t


def main_menu_kb(is_admin: bool = False, language: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=t(language, "catalog"), callback_data="catalog", icon_custom_emoji_id="5895440460322706085", style="primary"),
        InlineKeyboardButton(text=t(language, "orders"), callback_data="my_orders", icon_custom_emoji_id="5893255507380014983", style="primary"),
    )
    builder.row(
        InlineKeyboardButton(text=t(language, "promo"), callback_data="promo", icon_custom_emoji_id="5893365462837760511", style="primary"),
        InlineKeyboardButton(text=t(language, "profile"), callback_data="profile", icon_custom_emoji_id="5902335789798265487", style="primary"),
    )
    builder.row(InlineKeyboardButton(text=t(language, "support"), callback_data="support", icon_custom_emoji_id="5893297890117292323", style="danger"))
    builder.row(InlineKeyboardButton(text=f"🌐 {t(language, 'language')}", callback_data="language", style="primary"))
    if is_admin:
        builder.row(InlineKeyboardButton(text=f"{plain(SETTINGS)} {t(language, 'admin')}", callback_data="admin_main"))
    return builder.as_markup()


def profile_kb(ref_code: str, bot_username: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    ref_link = f"https://t.me/{bot_username}?start={ref_code}"
    builder.row(InlineKeyboardButton(text="Моя реф. ссылка", url=ref_link, icon_custom_emoji_id="5902449142575141204", style="primary"))
    builder.row(InlineKeyboardButton(text="Меню", callback_data="main_menu", icon_custom_emoji_id="5893311672667345793", style="primary"))
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
        builder.row(InlineKeyboardButton(text=cat.name, callback_data=f"cat_{cat.id}", icon_custom_emoji_id="5893382531037794941", style="primary"))
    builder.row(InlineKeyboardButton(text="В наличии", callback_data="in_stock", icon_custom_emoji_id="5893321843149902412", style="primary"))
    builder.row(InlineKeyboardButton(text="Назад", callback_data="main_menu", icon_custom_emoji_id="5893311672667345793", style="primary"))
    return builder.as_markup()


def subcatalog_kb(subcategories: list, back_cb: str = "catalog") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in subcategories:
        builder.row(InlineKeyboardButton(text=cat.name, callback_data=f"subcat_{cat.id}", icon_custom_emoji_id="5893382531037794941", style="primary"))
    builder.row(InlineKeyboardButton(text="Назад", callback_data=back_cb, icon_custom_emoji_id="5893311672667345793", style="primary"))
    return builder.as_markup()


def in_stock_categories_kb(categories: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.row(InlineKeyboardButton(text=category.name, callback_data=f"stock_cat_{category.id}", icon_custom_emoji_id="5893382531037794941", style="primary"))
    builder.row(InlineKeyboardButton(text="Назад", callback_data="catalog", icon_custom_emoji_id="5893311672667345793", style="primary"))
    return builder.as_markup()


def in_stock_subcategories_kb(categories: list, back_cb: str = "in_stock") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for category in categories:
        builder.row(InlineKeyboardButton(text=category.name, callback_data=f"stock_subcat_{category.id}", icon_custom_emoji_id="5893382531037794941", style="primary"))
    builder.row(InlineKeyboardButton(text="Назад", callback_data=back_cb, icon_custom_emoji_id="5893311672667345793", style="primary"))
    return builder.as_markup()


def products_kb(products: list, cat_id: int, parent_cat_id: int | None = None, stock_map: dict | None = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for product in products:
        stock = (stock_map or {}).get(product.id)
        stock_text = "∞" if stock is not None and stock >= 9999 else (str(stock) if stock is not None else "—")
        builder.row(InlineKeyboardButton(text=f"{product.name} — {product.price} ₽ · {stock_text}", callback_data=f"prod_{product.id}", icon_custom_emoji_id="5893321843149902412", style="primary"))
    back_cb = f"subcat_{parent_cat_id}" if parent_cat_id else "catalog"
    builder.row(InlineKeyboardButton(text="Назад", callback_data=back_cb, icon_custom_emoji_id="5893311672667345793", style="primary"))
    return builder.as_markup()


def payment_method_kb(
    order_id: int,
    user_balance: "Decimal | None" = None,
    rollypay_enabled: bool = True,
    freekassa_enabled: bool = False,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text="Оплатить Stars", icon_custom_emoji_id="5893494861612455015", style="primary",
        callback_data=f"pay_stars_{order_id}",
    ))
    builder.row(InlineKeyboardButton(
        text="CryptoBot (USDT)", icon_custom_emoji_id="6039802097916974085", style="primary",
        callback_data=f"pay_crypto_{order_id}",
    ))
    if rollypay_enabled:
        builder.row(InlineKeyboardButton(
            text="СБП / RollyPay (RUB)", icon_custom_emoji_id="5902056028513505203", style="primary",
            callback_data=f"pay_rollypay_{order_id}",
        ))
    if freekassa_enabled:
        builder.row(InlineKeyboardButton(
            text="FreeKAS (карта / СБП)", style="primary",
            callback_data=f"pay_freekassa_{order_id}",
        ))
    if user_balance is not None and user_balance > Decimal("0"):
        builder.row(InlineKeyboardButton(
            text=f"Баланс ({user_balance:.2f} ₽)", icon_custom_emoji_id="6039641775377748623", style="primary",
            callback_data=f"pay_balance_{order_id}",
        ))
    builder.row(InlineKeyboardButton(
        text="Отмена", icon_custom_emoji_id="5893163582194978381", style="danger",
        callback_data=f"cancel_order_{order_id}",
    ))
    return builder.as_markup()


def payment_link_kb(pay_url: str, order_id: int, provider: str = "crypto") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    btn_text = "Перейти к оплате (СБП)" if provider == "rollypay" else "Оплатить"
    builder.row(InlineKeyboardButton(text=btn_text, url=pay_url))
    builder.row(
        InlineKeyboardButton(
            text=f"{plain(OK)} Проверить оплату",
            callback_data=f"check_payment_{order_id}_{provider}",
        ),
        InlineKeyboardButton(
            text="Отмена",
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


def order_detail_kb(order_id: int, status: str, language: str = "ru") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status in ("paid", "delivered", "partial"):
        builder.row(InlineKeyboardButton(
            text=f"{plain(KEY)} Получить товар",
            callback_data=f"get_items_{order_id}",
        ))
        builder.row(InlineKeyboardButton(
            text="⭐ Review" if language == "en" else "⭐ Отзыв",
            callback_data=f"review_order_{order_id}", style="primary",
        ))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="my_orders"))
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Меню", callback_data="main_menu"))
    return builder.as_markup()
