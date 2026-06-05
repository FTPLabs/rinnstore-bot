from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛍 Каталог", callback_data="catalog"))
    builder.row(
        InlineKeyboardButton(text="🛒 Корзина", callback_data="cart"),
        InlineKeyboardButton(text="📦 Заказы", callback_data="my_orders"),
    )
    builder.row(
        InlineKeyboardButton(text="🔖 Промокод", callback_data="promo"),
        InlineKeyboardButton(text="💬 Поддержка", callback_data="support"),
    )
    builder.row(InlineKeyboardButton(text="👤 Профиль", callback_data="profile"))
    return builder.as_markup()


def catalog_kb(categories: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(InlineKeyboardButton(text=cat.name, callback_data=f"cat_{cat.id}"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))
    return builder.as_markup()


def product_kb(product_id: int, stock: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if stock > 0:
        builder.row(InlineKeyboardButton(text="🛒 В корзину", callback_data=f"add_cart_{product_id}"))
    else:
        builder.row(InlineKeyboardButton(text="Нет в наличии", callback_data="no_stock"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"cat_back_{product_id}"))
    return builder.as_markup()


def cart_kb(has_items: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_items:
        builder.row(InlineKeyboardButton(text="✅ Оформить", callback_data="checkout"))
        builder.row(InlineKeyboardButton(text="✕ Очистить", callback_data="clear_cart"))
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="main_menu"))
    return builder.as_markup()


def payment_method_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="₿ CryptoBot", callback_data=f"pay_crypto_{order_id}"))
    builder.row(InlineKeyboardButton(text="💳 RollyPay (скоро)", callback_data="pay_rollypay_soon"))
    builder.row(InlineKeyboardButton(text="✕ Отменить заказ", callback_data=f"cancel_order_{order_id}"))
    return builder.as_markup()


def payment_link_kb(pay_url: str, order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оплатить", url=pay_url))
    builder.row(InlineKeyboardButton(text="🔄 Проверить", callback_data=f"check_payment_{order_id}"))
    builder.row(InlineKeyboardButton(text="✕ Отменить", callback_data=f"cancel_order_{order_id}"))
    return builder.as_markup()


def orders_kb(orders: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    status_icon = {
        "pending": "⏳", "paid": "✅", "cancelled": "✕", "delivered": "🔑", "partial": "⚠️"
    }
    for order in orders:
        icon = status_icon.get(order.status, "❓")
        builder.row(InlineKeyboardButton(
            text=f"{icon} #{order.id} — {order.total_amount} ₽",
            callback_data=f"order_{order.id}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="main_menu"))
    return builder.as_markup()


def order_detail_kb(order_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status in ("paid", "delivered"):
        builder.row(InlineKeyboardButton(text="🔑 Получить товар", callback_data=f"get_items_{order_id}"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="my_orders"))
    return builder.as_markup()


def back_to_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Меню", callback_data="main_menu"))
    return builder.as_markup()
