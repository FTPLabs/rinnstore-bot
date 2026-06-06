from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from ..utils.emoji import (
    BAG, CATEGORY, ORDERS, USERS, STATS, PROMO,
    BROADCAST, SETTINGS, ADD, EDIT, DELETE, OK, FAIL,
    BACK, REFRESH, FIRE, KEY, LOG, BANNED, SHIELD, CATALOG, plain
)


def admin_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{plain(BAG)} Товары", callback_data="admin_products"),
        InlineKeyboardButton(text=f"{plain(CATALOG)} Категории", callback_data="admin_categories"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(ORDERS)} Заказы", callback_data="admin_orders"),
        InlineKeyboardButton(text=f"{plain(USERS)} Пользователи", callback_data="admin_users"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(STATS)} Статистика", callback_data="admin_stats"),
        InlineKeyboardButton(text=f"{plain(PROMO)} Промокоды", callback_data="admin_promos"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(BROADCAST)} Рассылка", callback_data="admin_broadcast"),
        InlineKeyboardButton(text=f"{plain(SETTINGS)} Настройки", callback_data="admin_settings"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    return builder.as_markup()


def admin_products_kb(products: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in products:
        status = plain(OK) if p.is_active else plain(FAIL)
        builder.row(InlineKeyboardButton(
            text=f"{status} {p.name} — {p.price} руб.",
            callback_data=f"admin_product_{p.id}"
        ))
    builder.row(InlineKeyboardButton(
        text=f"{plain(ADD)} Добавить товар",
        callback_data="admin_add_product"
    ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_main"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_product_detail_kb(product_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = f"{plain(FAIL)} Отключить" if is_active else f"{plain(OK)} Включить"
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data=f"admin_toggle_product_{product_id}"),
        InlineKeyboardButton(text="💰 Цена", callback_data=f"admin_change_price_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(KEY)} Добавить ключи", callback_data=f"admin_add_keys_{product_id}"),
        InlineKeyboardButton(text=f"{plain(STATS)} Остатки", callback_data=f"admin_stock_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="🏷 Скидка", callback_data=f"admin_set_discount_{product_id}"),
        InlineKeyboardButton(text=f"{plain(DELETE)} Удалить", callback_data=f"admin_delete_product_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_products"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_orders_kb(orders: list, page: int = 0) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for order in orders:
        status_emoji = {
            "pending": "⏳", "paid": plain(OK), "cancelled": plain(FAIL), "delivered": plain(KEY)
        }.get(order.status, "❓")
        builder.row(InlineKeyboardButton(
            text=f"{status_emoji} #{order.id} — {order.total_amount}₽ · user{order.user_id}",
            callback_data=f"admin_order_{order.id}"
        ))
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton(text="◀️", callback_data=f"admin_orders_page_{page-1}"))
    nav_row.append(InlineKeyboardButton(text=f"стр. {page+1}", callback_data="noop"))
    nav_row.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_orders_page_{page+1}"))
    builder.row(*nav_row)
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_main"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_order_detail_kb(order_id: int, status: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if status == "paid":
        builder.row(InlineKeyboardButton(
            text=f"{plain(KEY)} Выдать товар вручную",
            callback_data=f"admin_deliver_{order_id}"
        ))
    if status in ("pending", "paid"):
        builder.row(InlineKeyboardButton(
            text=f"{plain(FAIL)} Отменить заказ",
            callback_data=f"admin_cancel_order_{order_id}"
        ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_orders"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_categories_kb(categories: list) -> InlineKeyboardMarkup:
    """Список корневых категорий."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        status = plain(OK) if cat.is_active else plain(FAIL)
        builder.row(InlineKeyboardButton(
            text=f"{status} 📂 {cat.name}",
            callback_data=f"admin_cat_{cat.id}"
        ))
    builder.row(InlineKeyboardButton(
        text=f"{plain(ADD)} Добавить главную категорию",
        callback_data="admin_add_category"
    ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_main"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_category_detail_kb(cat_id: int, is_active: bool, has_subcats: bool = False) -> InlineKeyboardMarkup:
    """Детали категории с кнопкой добавления подкатегории."""
    builder = InlineKeyboardBuilder()
    toggle_text = f"{plain(FAIL)} Скрыть" if is_active else f"{plain(OK)} Показать"
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data=f"admin_toggle_cat_{cat_id}"),
        InlineKeyboardButton(text=f"{plain(DELETE)} Удалить", callback_data=f"admin_delete_cat_{cat_id}"),
    )
    builder.row(InlineKeyboardButton(
        text=f"{plain(ADD)} Добавить подкатегорию",
        callback_data=f"admin_add_subcat_{cat_id}"
    ))
    if has_subcats:
        builder.row(InlineKeyboardButton(
            text="📁 Подкатегории",
            callback_data=f"admin_subcats_{cat_id}"
        ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_categories"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_subcategories_kb(subcats: list, parent_cat_id: int) -> InlineKeyboardMarkup:
    """Список подкатегорий с управлением."""
    builder = InlineKeyboardBuilder()
    for cat in subcats:
        status = plain(OK) if cat.is_active else plain(FAIL)
        builder.row(InlineKeyboardButton(
            text=f"{status} 📁 {cat.name}",
            callback_data=f"admin_subcat_detail_{cat.id}"
        ))
    builder.row(InlineKeyboardButton(
        text=f"{plain(ADD)} Добавить подкатегорию",
        callback_data=f"admin_add_subcat_{parent_cat_id}"
    ))
    builder.row(InlineKeyboardButton(
        text=f"{plain(BACK)} Назад",
        callback_data=f"admin_cat_{parent_cat_id}"
    ))
    return builder.as_markup()


def admin_subcategory_detail_kb(subcat_id: int, is_active: bool, parent_cat_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = f"{plain(FAIL)} Скрыть" if is_active else f"{plain(OK)} Показать"
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data=f"admin_toggle_cat_{subcat_id}"),
        InlineKeyboardButton(text=f"{plain(DELETE)} Удалить", callback_data=f"admin_delete_cat_{subcat_id}"),
    )
    builder.row(InlineKeyboardButton(
        text=f"{plain(BACK)} Назад",
        callback_data=f"admin_subcats_{parent_cat_id}"
    ))
    return builder.as_markup()


def admin_users_kb(users: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for u in users:
        ban_icon = plain(BANNED) if u.is_banned else plain(SHIELD)
        name = u.first_name or f"id{u.id}"
        builder.row(InlineKeyboardButton(
            text=f"{ban_icon} {name} · {u.id}",
            callback_data=f"admin_user_{u.id}"
        ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_main"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_user_detail_kb(user_id: int, is_banned: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    ban_text = f"{plain(OK)} Разбанить" if is_banned else f"{plain(BANNED)} Забанить"
    builder.row(InlineKeyboardButton(text=ban_text, callback_data=f"admin_ban_{user_id}"))
    builder.row(InlineKeyboardButton(
        text=f"{plain(ORDERS)} Заказы пользователя",
        callback_data=f"admin_user_orders_{user_id}"
    ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_users"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_promos_kb(promos: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for p in promos:
        status = plain(OK) if p.is_active else plain(FAIL)
        val = f"{p.discount_value}%" if p.discount_type == "percent" else f"{p.discount_value}₽"
        builder.row(InlineKeyboardButton(
            text=f"{status} {p.code} — {val}",
            callback_data=f"admin_promo_{p.id}"
        ))
    builder.row(InlineKeyboardButton(
        text=f"{plain(ADD)} Создать промокод",
        callback_data="admin_add_promo"
    ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_main"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_promo_detail_kb(promo_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle = f"{plain(FAIL)} Деактивировать" if is_active else f"{plain(OK)} Активировать"
    builder.row(InlineKeyboardButton(text=toggle, callback_data=f"admin_toggle_promo_{promo_id}"))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_promos"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_main"))
    return builder.as_markup()


def admin_confirm_kb(action: str, entity_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"confirm_{action}_{entity_id}"),
        InlineKeyboardButton(text="✕ Отмена", callback_data="admin_main"),
    )
    return builder.as_markup()


def admin_select_category_kb(categories: list, action_prefix: str) -> InlineKeyboardMarkup:
    """Выбор категории (для создания товара)."""
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(InlineKeyboardButton(
            text=f"{'📁' if cat.parent_id else '📂'} {cat.name}",
            callback_data=f"{action_prefix}{cat.id}"
        ))
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_products"))
    return builder.as_markup()
