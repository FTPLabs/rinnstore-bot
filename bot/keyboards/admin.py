from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from ..utils.emoji import (
    BAG, CATEGORY, ORDERS, USERS, STATS, PROMO,
    BROADCAST, SETTINGS, ADD, EDIT, DELETE, OK, FAIL,
    BACK, REFRESH, FIRE, KEY, LOG, BANNED, SHIELD, CATALOG, plain
)

KEYS_PAGE_SIZE = 10


def admin_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📚 Каталог", callback_data="admin_catalog"),
        InlineKeyboardButton(text=f"{plain(ORDERS)} Заказы", callback_data="admin_orders"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(USERS)} Пользователи", callback_data="admin_users"),
        InlineKeyboardButton(text=f"{plain(STATS)} Статистика", callback_data="admin_stats"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(PROMO)} Промокоды", callback_data="admin_promos"),
        InlineKeyboardButton(text=f"{plain(BROADCAST)} Рассылка", callback_data="admin_broadcast"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(SETTINGS)} Настройки", callback_data="admin_settings"),
    )
    builder.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu"))
    return builder.as_markup()


# ─── CATALOG (unified) ───────────────────────────────────────────────

def admin_catalog_root_kb(root_cats: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in root_cats:
        status = plain(OK) if cat.is_active else plain(FAIL)
        builder.row(InlineKeyboardButton(
            text=f"{status} 📂 {cat.name}",
            callback_data=f"cat_view_{cat.id}"
        ))
    builder.row(InlineKeyboardButton(
        text=f"{plain(ADD)} Добавить категорию",
        callback_data="cat_add_root"
    ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_main"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_catalog_cat_kb(
    cat_id: int,
    is_active: bool,
    subcats: list,
    products: list,
    parent_id: int | None = None,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for sc in subcats:
        status = plain(OK) if sc.is_active else plain(FAIL)
        builder.row(InlineKeyboardButton(
            text=f"{status} 📁 {sc.name}",
            callback_data=f"cat_view_{sc.id}"
        ))
    for p in products:
        status = plain(OK) if p.is_active else plain(FAIL)
        builder.row(InlineKeyboardButton(
            text=f"{status} {plain(BAG)} {p.name} — {p.price}₽",
            callback_data=f"admin_product_{p.id}"
        ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(ADD)} Подкатегория", callback_data=f"cat_add_sub_{cat_id}"),
        InlineKeyboardButton(text=f"{plain(ADD)} Товар", callback_data=f"cat_add_product_{cat_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="📥 Импорт товаров", callback_data=f"cat_import_{cat_id}"),
    )
    toggle_text = f"{plain(FAIL)} Скрыть" if is_active else f"{plain(OK)} Показать"
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data=f"admin_toggle_cat_{cat_id}"),
        InlineKeyboardButton(text=f"{plain(DELETE)} Удалить", callback_data=f"admin_delete_cat_{cat_id}"),
    )
    back_cb = f"cat_view_{parent_id}" if parent_id else "admin_catalog"
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data=back_cb),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_catalog_product_detail_kb(product_id: int, is_active: bool, cat_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = f"{plain(FAIL)} Отключить" if is_active else f"{plain(OK)} Включить"
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data=f"admin_toggle_product_{product_id}"),
        InlineKeyboardButton(text="💰 Цена", callback_data=f"admin_change_price_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(KEY)} Добавить ключи", callback_data=f"admin_add_keys_{product_id}"),
        InlineKeyboardButton(text=f"{plain(EDIT)} Ключи / Редактировать", callback_data=f"admin_keys_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(STATS)} Остатки", callback_data=f"admin_stock_{product_id}"),
        InlineKeyboardButton(text="🏷 Скидка", callback_data=f"admin_set_discount_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(DELETE)} Удалить товар", callback_data=f"admin_delete_product_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} В категорию", callback_data=f"cat_view_{cat_id}"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def catalog_skip_kb(skip_cb: str, cancel_cb: str = "admin_main") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="⏭ Пропустить", callback_data=skip_cb),
        InlineKeyboardButton(text="✕ Отмена", callback_data=cancel_cb),
    )
    return builder.as_markup()


def catalog_type_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{plain(BAG)} Обычный (конечный запас)", callback_data="cat_prod_type_normal"),
        InlineKeyboardButton(text="♾ Безлимитный", callback_data="cat_prod_type_unlimited"),
    )
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_main"))
    return builder.as_markup()


# ─── PRODUCTS LIST ────────────────────────────────────────────────────

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
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_catalog"),
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
        InlineKeyboardButton(text=f"{plain(EDIT)} Ключи / Редактировать", callback_data=f"admin_keys_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(STATS)} Остатки", callback_data=f"admin_stock_{product_id}"),
        InlineKeyboardButton(text="🏷 Скидка", callback_data=f"admin_set_discount_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(DELETE)} Удалить", callback_data=f"admin_delete_product_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_catalog"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


# ─── KEY MANAGEMENT ───────────────────────────────────────────────────

def admin_product_keys_kb(
    keys: list,
    product_id: int,
    page: int = 0,
    total: int = 0,
) -> InlineKeyboardMarkup:
    """Список ключей товара с пагинацией."""
    builder = InlineKeyboardBuilder()
    for item in keys:
        sold_icon = plain(FAIL) if item.is_sold else plain(OK)
        preview = item.data[:28] + "…" if len(item.data) > 30 else item.data
        builder.row(InlineKeyboardButton(
            text=f"{sold_icon} #{item.id} {preview}",
            callback_data=f"admin_key_{item.id}"
        ))
    # Навигация по страницам
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text=f"{plain(BACK)}", callback_data=f"admin_keys_{product_id}_pg_{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page+1}/{max(1,(total+KEYS_PAGE_SIZE-1)//KEYS_PAGE_SIZE)}", callback_data="noop"))
    if (page + 1) * KEYS_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"admin_keys_{product_id}_pg_{page+1}"))
    if nav:
        builder.row(*nav)
    builder.row(
        InlineKeyboardButton(text=f"{plain(ADD)} Добавить ключи", callback_data=f"admin_add_keys_{product_id}"),
    )
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} К товару", callback_data=f"admin_product_{product_id}"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_key_detail_kb(key_id: int, product_id: int, is_sold: bool) -> InlineKeyboardMarkup:
    """Детали одного ключа — редактировать и удалить."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{plain(EDIT)} Редактировать", callback_data=f"admin_key_edit_{key_id}"),
    )
    if not is_sold:
        builder.row(
            InlineKeyboardButton(text=f"{plain(DELETE)} Удалить ключ", callback_data=f"admin_key_del_{key_id}"),
        )
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} К списку", callback_data=f"admin_keys_{product_id}"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_confirm_key_del_kb(key_id: int, product_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления ключа."""
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{plain(OK)} Да, удалить", callback_data=f"confirm_key_del_{key_id}"),
        InlineKeyboardButton(text="✕ Отмена", callback_data=f"admin_key_{key_id}"),
    )
    return builder.as_markup()


# ─── ORDERS ──────────────────────────────────────────────────────────

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
        nav_row.append(InlineKeyboardButton(text=f"{plain(BACK)}", callback_data=f"admin_orders_page_{page-1}"))
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


# ─── CATEGORIES ──────────────────────────────────────────────────────

def admin_categories_kb(categories: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        status = plain(OK) if cat.is_active else plain(FAIL)
        builder.row(InlineKeyboardButton(
            text=f"{status} 📂 {cat.name}",
            callback_data=f"cat_view_{cat.id}"
        ))
    builder.row(InlineKeyboardButton(
        text=f"{plain(ADD)} Добавить главную категорию",
        callback_data="cat_add_root"
    ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_catalog"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_category_detail_kb(cat_id: int, is_active: bool, has_subcats: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = f"{plain(FAIL)} Скрыть" if is_active else f"{plain(OK)} Показать"
    builder.row(
        InlineKeyboardButton(text=toggle_text, callback_data=f"admin_toggle_cat_{cat_id}"),
        InlineKeyboardButton(text=f"{plain(DELETE)} Удалить", callback_data=f"admin_delete_cat_{cat_id}"),
    )
    builder.row(InlineKeyboardButton(
        text=f"{plain(ADD)} Добавить подкатегорию",
        callback_data=f"cat_add_sub_{cat_id}"
    ))
    if has_subcats:
        builder.row(InlineKeyboardButton(
            text="📁 Подкатегории",
            callback_data=f"cat_view_{cat_id}"
        ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_catalog"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


def admin_subcategories_kb(subcats: list, parent_cat_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in subcats:
        status = plain(OK) if cat.is_active else plain(FAIL)
        builder.row(InlineKeyboardButton(
            text=f"{status} 📁 {cat.name}",
            callback_data=f"cat_view_{cat.id}"
        ))
    builder.row(InlineKeyboardButton(
        text=f"{plain(ADD)} Добавить подкатегорию",
        callback_data=f"cat_add_sub_{parent_cat_id}"
    ))
    builder.row(InlineKeyboardButton(
        text=f"{plain(BACK)} Назад",
        callback_data=f"cat_view_{parent_cat_id}"
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
        callback_data=f"cat_view_{parent_cat_id}"
    ))
    return builder.as_markup()


# ─── USERS ───────────────────────────────────────────────────────────

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
    builder.row(InlineKeyboardButton(
        text="💰 Начислить баланс",
        callback_data=f"admin_add_balance_{user_id}"
    ))
    builder.row(
        InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="admin_users"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main_menu"),
    )
    return builder.as_markup()


# ─── PROMOS ──────────────────────────────────────────────────────────

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


# ─── MISC ─────────────────────────────────────────────────────────────

def cancel_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_main"))
    return builder.as_markup()


def admin_confirm_kb(action: str, entity_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=f"{plain(OK)} Да, удалить", callback_data=f"confirm_{action}_{entity_id}"),
        InlineKeyboardButton(text="✕ Отмена", callback_data="admin_main"),
    )
    return builder.as_markup()


def admin_select_category_kb(categories: list, action_prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(InlineKeyboardButton(
            text=f"{'📁' if cat.parent_id else '📂'} {cat.name}",
            callback_data=f"{action_prefix}{cat.id}"
        ))
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_catalog"))
    return builder.as_markup()
