from decimal import Decimal
from datetime import datetime, timezone
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from ..keyboards.user import (
    catalog_kb, subcatalog_kb, products_kb, in_stock_categories_kb, in_stock_subcategories_kb,
    back_to_menu_kb, payment_method_kb
)
from ..services.catalog_service import (
    get_root_categories, get_subcategories, get_category,
    get_products_in_category, get_all_active_products, get_product,
    get_stock_count, get_product_category_id, UNLIMITED_STOCK
)
from ..services.order_service import create_order
from ..models import User
from ..utils.helpers import parse_callback_int
from ..utils.custom_emoji import emoji_id
from ..utils.emoji import e
from ..utils.i18n import t, localized_name, localized_description

router = Router()

MAX_QTY_BUTTONS = 5


async def _stock_map(session: AsyncSession, products: list) -> dict[int, int]:
    result = {}
    for product in products:
        result[product.id] = await get_stock_count(session, product.id)
    return result


def _product_text(product, stock: int, qty: int = 1, user=None) -> str:
    stock_line = f"{e('5893321843149902412', '📦')} <b>{t(user, 'unlimited')}</b>" if stock >= UNLIMITED_STOCK else f"{e('5893321843149902412', '📦')} <b>{t(user, 'stock')}: {stock}</b>"
    if stock == 0:
        stock_line = f"{e('5893163582194978381', '❌')} <b>{t(user, 'no_stock')}</b>"

    now = datetime.now(timezone.utc)
    has_discount = (
        product.discount_percent
        and (not product.discount_expires_at or product.discount_expires_at > now)
    )
    if has_discount:
        d100 = Decimal("100")
        sale = product.price * (d100 - product.discount_percent) / d100
        price_line = f"<b>{t(user, 'price')}: <s>{product.price} ₽</s> → {sale:.2f} ₽</b> {e('5893365462837760511', '🏷')}"
        unit_price = sale
    else:
        price_line = f"<b>{t(user, 'price')}: {product.price} ₽</b>"
        unit_price = product.price

    description = localized_description(product, user)
    desc = f"\n<b>{description}</b>\n" if description else "\n"
    total_line = ""
    if qty > 1:
        total_line = f"\n<b>{t(user, 'total')} ({qty}): {unit_price * qty:.2f} ₽</b>"

    return (
        f"{e('5893321843149902412', '📦')} <b>{localized_name(product, user)}</b>{desc}\n"
        f"{price_line}\n"
        f"{stock_line}"
        f"{total_line}"
    )


def _product_kb(product_id: int, stock: int, qty: int = 1, user=None) -> object:
    builder = InlineKeyboardBuilder()

    if stock == 0:
        builder.row(InlineKeyboardButton(text=t(user, "no_stock"), callback_data="noop", icon_custom_emoji_id=emoji_id("5893163582194978381"), style="danger"))
    else:
        max_qty = min(stock, MAX_QTY_BUTTONS) if stock < UNLIMITED_STOCK else MAX_QTY_BUTTONS

        if max_qty > 1:
            qty_buttons = []
            for q in range(1, max_qty + 1):
                label = f"[{q}]" if q == qty else str(q)
                qty_buttons.append(InlineKeyboardButton(
                    text=label,
                    callback_data=f"setqty_{product_id}_{q}"
                ))
            builder.row(*qty_buttons)

        buy_text = f"{t(user, 'buy')} ({qty})" if qty > 1 else t(user, "buy")
        builder.row(InlineKeyboardButton(
            text=buy_text,
            callback_data=f"buy_{product_id}_{qty}",
            icon_custom_emoji_id=emoji_id("5893311672667345793"),
            style="danger",
        ))

    builder.row(InlineKeyboardButton(text=t(user, "back"), callback_data=f"cat_back_{product_id}", icon_custom_emoji_id=emoji_id("5893311672667345793"), style="primary"))
    return builder.as_markup()


async def _show_product(call: CallbackQuery, session: AsyncSession, product_id: int, qty: int = 1, user=None):
    product = await get_product(session, product_id)
    if not product:
        await call.answer(t(user, "product_not_found"), show_alert=True)
        return None, 0

    stock = await get_stock_count(session, product_id)
    max_qty = min(stock, MAX_QTY_BUTTONS) if stock < UNLIMITED_STOCK else MAX_QTY_BUTTONS
    if qty > max_qty:
        qty = 1

    text = _product_text(product, stock, qty, user)
    kb = _product_kb(product_id, stock, qty, user)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    return product, stock


def _get_back_cb(category) -> str:
    if not category.parent_id:
        return "catalog"
    return f"subcat_{category.parent_id}"


async def _category_has_stock(session: AsyncSession, category_id: int, visited: set[int] | None = None) -> bool:
    """Return whether this category or any active descendant has stock."""
    visited = visited or set()
    if category_id in visited:
        return False
    visited.add(category_id)

    for product in await get_products_in_category(session, category_id):
        if await get_stock_count(session, product.id) > 0:
            return True
    for child in await get_subcategories(session, category_id):
        if await _category_has_stock(session, child.id, visited):
            return True
    return False


async def _show_stock_category(
    call: CallbackQuery,
    session: AsyncSession,
    user: User,
    category_id: int,
    back_cb: str,
) -> None:
    """Render only stocked descendants or direct stocked products."""
    category = await get_category(session, category_id)
    if not category or not await _category_has_stock(session, category_id):
        await call.answer("В этой категории доступных товаров нет", show_alert=True)
        return

    available_subcategories = [
        child for child in await get_subcategories(session, category_id)
        if await _category_has_stock(session, child.id)
    ]
    direct_products = []
    for product in await get_products_in_category(session, category_id):
        if await get_stock_count(session, product.id) > 0:
            direct_products.append(product)

    if available_subcategories:
        await call.message.edit_text(
            f"<b>{localized_name(category, user)}</b>\n\nВыберите подкатегорию:",
            reply_markup=in_stock_subcategories_kb(
                available_subcategories,
                back_cb=back_cb,
                language=user.language_code,
            ),
            parse_mode="HTML",
        )
    elif direct_products:
        stock_map = {p.id: await get_stock_count(session, p.id) for p in direct_products}
        await call.message.edit_text(
            f"<b>{localized_name(category, user)}</b>\n\nВыберите товар:",
            reply_markup=products_kb(
                direct_products,
                category_id,
                parent_cat_id=category.parent_id,
                stock_map=stock_map,
                language=user.language_code,
            ),
            parse_mode="HTML",
        )
    await call.answer()


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()


@router.callback_query(F.data == "catalog")
async def cb_catalog(call: CallbackQuery, session: AsyncSession, user: User):
    cats = await get_root_categories(session)
    if not cats:
        await call.message.edit_text(t(user, "catalog_empty"), reply_markup=back_to_menu_kb())
        await call.answer()
        return
    await call.message.edit_text(
        f"<b>\U0001f6cd {t(user, 'catalog')}</b>\n\n{t(user, 'choose_category')}",
        reply_markup=catalog_kb(cats, user.language_code),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data == "in_stock")
async def cb_in_stock(call: CallbackQuery, session: AsyncSession, user: User):
    # The availability view must include hidden roots: an admin can hide a
    # category from the regular catalog while its stock is still sellable.
    roots = await get_root_categories(session, include_inactive=True)
    available_roots = [
        category for category in roots
        if await _category_has_stock(session, category.id)
    ]
    if not available_roots:
        await call.message.edit_text(
            "<b>В наличии</b>\n\nСейчас доступных товаров нет.",
            reply_markup=back_to_menu_kb(), parse_mode="HTML",
        )
    else:
        await call.message.edit_text(
            "<b>В наличии</b>\n\nВыберите категорию:",
            reply_markup=in_stock_categories_kb(available_roots, user.language_code),
            parse_mode="HTML",
        )
    await call.answer()


@router.callback_query(F.data.regexp(r"^stock_cat_\d+$"))
async def cb_stock_category(call: CallbackQuery, session: AsyncSession, user: User):
    category_id = int(call.data.rsplit("_", 1)[1])
    await _show_stock_category(call, session, user, category_id, back_cb="in_stock")


@router.callback_query(F.data.regexp(r"^stock_subcat_\d+$"))
async def cb_stock_subcategory(call: CallbackQuery, session: AsyncSession, user: User):
    category_id = int(call.data.rsplit("_", 1)[1])
    category = await get_category(session, category_id)
    back_cb = f"stock_cat_{category.parent_id}" if category and category.parent_id else "in_stock"
    await _show_stock_category(call, session, user, category_id, back_cb=back_cb)


@router.callback_query(F.data.regexp(r"^cat_\d+$"))
async def cb_cat(call: CallbackQuery, session: AsyncSession, user: User):
    cat_id = parse_callback_int(call.data, 1)
    if cat_id is None:
        await call.answer("Ошибка", show_alert=True)
        return

    category = await get_category(session, cat_id)
    if not category or not category.is_active:
        await call.answer("Категория не найдена", show_alert=True)
        return

    subcats = await get_subcategories(session, cat_id)
    if subcats:
        await call.message.edit_text(
            f"<b>\U0001f4c2 {localized_name(category, user)}</b>\n\nВыберите подкатегорию:",
            reply_markup=subcatalog_kb(subcats, back_cb="catalog", language=user.language_code),
            parse_mode="HTML"
        )
        await call.answer()
        return

    product_list = await get_products_in_category(session, cat_id)
    if not product_list:
        await call.message.edit_text(
            f"<b>{localized_name(category, user)}</b>\n\nТоваров пока нет.",
            reply_markup=products_kb([], cat_id, language=user.language_code),
            parse_mode="HTML"
        )
        await call.answer()
        return

    stock_map = await _stock_map(session, product_list)
    await call.message.edit_text(
        f"<b>\U0001f4c2 {localized_name(category, user)}</b>\n\nВыберите товар:",
        reply_markup=products_kb(product_list, cat_id, stock_map=stock_map, language=user.language_code),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^subcat_\d+$"))
async def cb_subcat(call: CallbackQuery, session: AsyncSession, user: User):
    cat_id = parse_callback_int(call.data, 1)
    if cat_id is None:
        await call.answer("Ошибка", show_alert=True)
        return

    category = await get_category(session, cat_id)
    if not category or not category.is_active:
        await call.answer("Категория не найдена", show_alert=True)
        return

    subcats = await get_subcategories(session, cat_id)
    back_cb = _get_back_cb(category)

    if subcats:
        await call.message.edit_text(
            f"<b>\U0001f4c1 {localized_name(category, user)}</b>\n\nВыберите подкатегорию:",
            reply_markup=subcatalog_kb(subcats, back_cb=back_cb, language=user.language_code),
            parse_mode="HTML"
        )
        await call.answer()
        return

    product_list = await get_products_in_category(session, cat_id)
    if not product_list:
        await call.message.edit_text(
            f"<b>\U0001f4c1 {localized_name(category, user)}</b>\n\nТоваров пока нет.",
            reply_markup=products_kb([], cat_id, parent_cat_id=category.parent_id, language=user.language_code),
            parse_mode="HTML"
        )
        await call.answer()
        return

    stock_map = await _stock_map(session, product_list)
    await call.message.edit_text(
        f"<b>\U0001f4c1 {localized_name(category, user)}</b>\n\nВыберите товар:",
        reply_markup=products_kb(product_list, cat_id, parent_cat_id=category.parent_id, stock_map=stock_map, language=user.language_code),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^prod_\d+$"))
async def cb_product(call: CallbackQuery, session: AsyncSession, user: User):
    product_id = parse_callback_int(call.data, 1)
    if product_id is None:
        await call.answer("Ошибка", show_alert=True)
        return
    await _show_product(call, session, product_id, user=user)
    await call.answer()


@router.callback_query(F.data.startswith("setqty_"))
async def cb_setqty(call: CallbackQuery, session: AsyncSession, user: User):
    parts = call.data.split("_")
    if len(parts) < 3:
        await call.answer()
        return
    try:
        product_id = int(parts[1])
        qty = int(parts[2])
    except ValueError:
        await call.answer()
        return
    await _show_product(call, session, product_id, qty, user)
    await call.answer()


@router.callback_query(F.data.startswith("cat_back_"))
async def cb_cat_back(call: CallbackQuery, session: AsyncSession, user: User):
    product_id = parse_callback_int(call.data, 2)
    if product_id is None:
        await cb_catalog(call, session, user)
        return

    cat_id = await get_product_category_id(session, product_id)
    if cat_id is None:
        await cb_catalog(call, session, user)
        return

    category = await get_category(session, cat_id)
    if not category:
        await cb_catalog(call, session, user)
        return

    product_list = await get_products_in_category(session, cat_id)
    stock_map = await _stock_map(session, product_list)
    icon = "\U0001f4c1" if category.parent_id else "\U0001f4c2"
    await call.message.edit_text(
        f"<b>{icon} {localized_name(category, user)}</b>\n\nВыберите товар:",
        reply_markup=products_kb(product_list, cat_id, parent_cat_id=category.parent_id, stock_map=stock_map, language=user.language_code),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("buy_"))
async def cb_buy(call: CallbackQuery, session: AsyncSession, user: User):
    parts = call.data.split("_")
    if len(parts) < 3:
        await call.answer("Ошибка данных", show_alert=True)
        return
    try:
        product_id = int(parts[1])
        qty = int(parts[2])
    except ValueError:
        await call.answer("Ошибка данных", show_alert=True)
        return
    if qty < 1 or qty > 100:
        await call.answer("Можно купить от 1 до 100 шт.", show_alert=True)
        return

    product = await get_product(session, product_id)
    if not product or not product.is_active:
        await call.answer("Товар недоступен", show_alert=True)
        return

    stock = await get_stock_count(session, product_id)
    if stock == 0:
        await call.answer("Товар закончился", show_alert=True)
        return

    if stock < UNLIMITED_STOCK and qty > stock:
        await call.answer(f"Доступно только {stock} шт.", show_alert=True)
        return

    now = datetime.now(timezone.utc)
    has_discount = (
        product.discount_percent
        and (not product.discount_expires_at or product.discount_expires_at > now)
    )
    if has_discount:
        d100 = Decimal("100")
        unit_price = product.price * (d100 - product.discount_percent) / d100
    else:
        unit_price = product.price

    cart_items = [{"product_id": product_id, "qty": qty, "price": unit_price}]
    order = await create_order(session, user.id, cart_items)
    from ..services.settings_service import get_cached
    freekassa_enabled = bool(
        (get_cached("freekassa_shop_id") or "").strip()
        and (get_cached("freekassa_secret_word_1") or "").strip()
    )

    await call.message.edit_text(
        f"{e('5893311672667345793', '🔑')} <b>ЗАКАЗ #{order.id} СОЗДАН</b>\n\n"
        f"<b>{product.name} × {qty}</b>\n"
        f"<b>Итого: {order.total_amount} ₽</b>\n\n"
        f"<b>Выберите способ оплаты:</b>",
        reply_markup=payment_method_kb(order.id, user.balance, freekassa_enabled=freekassa_enabled, language=user.language_code),
        parse_mode="HTML"
    )
    await call.answer()
