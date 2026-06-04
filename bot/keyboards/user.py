from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from ..utils.emoji import (
    CATALOG, CART, BAG, SUPPORT, PROFILE, PROMO,
    BACK, OK, FAIL, STAR, KEY, GIFT, LOCK, SHIELD,
    CLOCK, REFRESH, ORDERS
)


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"{CATALOG} Каталог товаров",
        callback_data="catalog"
    ))
    builder.row(
        InlineKeyboardButton(text=f"{CART} Корзина", callback_data="cart"),
        InlineKeyboardButton(text=f"{BAG} Мои заказы", callback_data="my_orders"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{PROMO} Промокод", callback_data="promo"),
        InlineKeyboardButton(text=f"{SUPPORT} Поддержка", callback_data="support"),
    )
    builder.row(InlineKeyboardButton(text=f"{PROFILE} Профиль", callback_data="profile"))
    return builder.as_markup()


def catalog_kb(categories: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(InlineKeyboardButton(
            text=f"{STAR} {cat.name}",
            callback_data=f"cat_{cat.id}"
        ))
    builder.row(InlineKeyboardButton(text=f"{BACK} Назад", callback_data="main_menu"))
    return builder.as_markup()


def products_kb(products: list, category_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products:
        builder.row(InlineKeyboardButton(
            text=f"{p.name} — {p.price} руб.",
            callback_data=f"product_{p.id}"
        ))
    builder.row(InlineKeyboardButton(text=f"{BACK} Назад", callback_data="catalog"))
    return builder.as_markup()


def product_kb(product_id: int, stock: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if stock > 0:
        builder.row(InlineKeyboardButton(
            text=f"{CART} Добавить в корзину",
            callback_data=f"add_cart_{product_id}"
        ))
    else:
        builder.row(InlineKeyboardButton(
            text=f"{FAIL} Нет в наличии",
            callback_data="no_stock"
        ))
    builder.row(InlineKeyboardButton(
        text=f"{BACK} Назад",
        callback_data=f"cat_back_{product_id}"
    ))
    return builder.as_markup()


def cart_kb(has_items: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_items:
        builder.row(InlineKeyboardButton(
            text=f"{OK} Оформить заказ",
            callback_data="checkout"
        ))
        builder.row(InlineKeyboardButton(
            text=f"{FAIL} Очистить корзину",
            callback_data="clear_cart"
        ))
    builder.row(InlineKeyboardButton(text=f"{BACK} В меню", callback_data="main_menu"))
    return builder.as_markup()


def payment_method_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"{SHIELD} Оплата криптовалютой (CryptoBot)",
        callback_data=f"pay_crypto_{order_id}"
    ))
    builder.row(InlineKeyboardButton(
        text=f"{LOCK} RollyPay (скоро)",
        callback_data="pay_rollypay_soon"
    ))
    builder.row(InlineKeyboardButton(
        text=f"{FAIL} Отменить заказ",
        callback_data=f"cancel_order_{order_id}"
    ))
    return builder.as_markup()


def payment_link_kb(pay_url: str, order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"{SHIELD} Оплатить сейчас", url=pay_url))
    builder.row(InlineKeyboardButton(
        text=f"{REFRESH} Проверить оплату",
        callback_data=f"check_payment_{order_id}"
    ))
    builder.row(InlineKeyboardButton(
        text=f"{FAIL} Отменить",
        callback_data=f"cancel_order_{order_id}"
    ))
    return builder.as_markup()


def orders_kb(orders: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        status_emoji = {
            "pending": f"{CLOCK}",
            "paid": f"{OK}",
            "cancelled": f"{FAIL}",
            "delivered": f"{KEY}",
        }.get(order.status, "❓")
        builder.row(InlineKeyboardButton(
            text=f"{status_emoji} Заказ #{order.id} — {order.total_amount} руб.",
            callback_data=f"order_{order.id}"
        ))
    builder.row(InlineKeyboardButton(text=f"{BACK} Назад", callback_data="main_menu"))
    return builder.as_markup()


def order_detail_kb(order_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status in ("paid", "delivered"):
        builder.row(InlineKeyboardButton(
            text=f"{KEY} Получить товар",
            callback_data=f"get_items_{order_id}"
        ))
    builder.row(InlineKeyboardButton(text=f"{BACK} Назад", callback_data="my_orders"))
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"{BACK} В главное меню", callback_data="main_menu"))
    return builder.as_markup()
