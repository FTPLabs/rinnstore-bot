from decimal import Decimal
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from ..keyboards.user import catalog_kb, back_to_menu_kb
from ..services.catalog_service import (
    get_active_categories, get_category,
    get_products_in_category, get_product,
    get_stock_count, get_product_category_id, UNLIMITED_STOCK
)
from ..services.order_service import create_order
from ..models import User
from ..utils.helpers import parse_callback_int
from datetime import datetime, timezone

router = Router()

MAX_QTY_BUTTONS = 5


def _product_text(product, stock: int, qty: int = 1) -> str:
    stock_line = "♾ Безлимитно" if stock >= UNLIMITED_STOCK else f"В наличии: <b>{stock} шт.</b>"
    if stock == 0:
        stock_line = "<b>❌ Нет в наличии</b>"

    now = datetime.now(timezone.utc)
    has_discount = (
        product.discount_percent
        and (not product.discount_expires_at or product.discount_expires_at > now)
    )
    if has_discount:
        sale = product.price * (1 - product.discount_percent / 100)
        price_line = (
            f"Цена: <s>{product.price} ₽</s> → <b>{sale:.2f} ₽</b>"
            f"  🏷 -{product.discount_percent}%"
        )
        unit_price = float(sale)
    else:
        price_line = f"Цена: <b>{product.price} ₽</b>"
        unit_price = float(product.price)

    desc = f"\n{product.description}\n" if product.description else "\n"
    total_line = ""
    if qty > 1:
        total_line = f"\nИтого за {qty} шт.: <b>{unit_price * qty:.2f} ₽</b>"
    return (
        f"<b>{product.name}</b>{desc}\n"
        f"{price_line}\n"
        f"{stock_line}"
        f"{total_line}"
    )


def _product_kb(product_id: int, stock: int, qty: int = 1) -> object:
    builder = InlineKeyboardBuilder()

    if stock == 0:
        builder.row(InlineKeyboardButton(text="❌ Нет в наличии", callback_data="noop"))
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

        buy_text = f"🛒 Купить {qty} шт. · {_get_total_text(product_id, qty)}" if qty > 1 else "🛒 Купить"
        builder.row(InlineKeyboardButton(
            text=buy_text,
            callback_data=f"buy_{product_id}_{qty}"
        ))

    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"cat_back_{product_id}"))
    return builder.as_markup()


def _get_total_text(product_id: int, qty: int) -> str:
    return f"{qty} шт."


async def _show_product(call: CallbackQuery, session: AsyncSession, product_id: int, qty: int = 1):
    product = await get_product(session, product_id)
    if not product:
        await call.answer("Товар не найден", show_alert=True)
        return None, 0

    stock = await get_stock_count(session, product_id)
    if qty > (min(stock, MAX_QTY_BUTTONS) if stock < UNLIMITED_STOCK else MAX_QTY_BUTTONS):
        qty = 1

    text = _product_text(product, stock, qty)
    kb = _product_kb(product_id, stock, qty)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    except Exception:
        await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
    return product, stock


@router.callback_query(F.data == "catalog")
async def cb_catalog(call: CallbackQuery, session: AsyncSession):
    categories = await get_active_categories(session)
    if not categories:
        await call.message.edit_text("Каталог пуст. Загляните позже.", reply_markup=back_to_menu_kb())
        await call.answer()
        return
    await call.message.edit_text("<b>Каталог</b>\n\nВыберите категорию:", reply_markup=catalog_kb(categories), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("cat_") & ~F.data.startswith("cat_back_"))
async def cb_category(call: CallbackQuery, session: AsyncSession):
    cat_id = parse_callback_int(call.data, 1)
    if cat_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    category = await get_category(session, cat_id)
    if not category:
        await call.answer("Категория не найдена", show_alert=True)
        return

    products = await get_products_in_category(session, cat_id)
    if not products:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="catalog"))
        await call.message.edit_text(f"<b>{category.name}</b>\n\nТоваров пока нет.", reply_markup=builder.as_markup(), parse_mode="HTML")
        await call.answer()
        return

    builder = InlineKeyboardBuilder()
    for p in products:
        stock = await get_stock_count(session, p.id)
        if stock == 0:
            prefix = "❌ "
        elif stock >= UNLIMITED_STOCK:
            prefix = "♾ "
        else:
            prefix = ""
        builder.row(InlineKeyboardButton(
            text=f"{prefix}{p.name} — {p.price} ₽",
            callback_data=f"product_{p.id}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="catalog"))
    await call.message.edit_text(f"<b>{category.name}</b>", reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("product_"))
async def cb_product(call: CallbackQuery, session: AsyncSession):
    product_id = parse_callback_int(call.data, 1)
    if product_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return
    await _show_product(call, session, product_id, qty=1)
    await call.answer()


@router.callback_query(F.data.startswith("setqty_"))
async def cb_set_qty(call: CallbackQuery, session: AsyncSession):
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
    await _show_product(call, session, product_id, qty=qty)
    await call.answer()


@router.callback_query(F.data.startswith("buy_"))
async def cb_buy(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
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

    product = await get_product(session, product_id)
    if not product or not product.is_active:
        await call.answer("Товар недоступен", show_alert=True)
        return

    stock = await get_stock_count(session, product_id)
    if stock == 0:
        await call.answer("❌ Нет в наличии", show_alert=True)
        return
    if stock < UNLIMITED_STOCK and qty > stock:
        await call.answer(f"Доступно только {stock} шт.", show_alert=True)
        return

    now = datetime.now(timezone.utc)
    has_discount = (
        product.discount_percent
        and (not product.discount_expires_at or product.discount_expires_at > now)
    )
    unit_price = float(product.price * (1 - product.discount_percent / 100)) if has_discount else float(product.price)

    fsm_data = await state.get_data()
    promo_code = fsm_data.get("promo_code")

    cart_items = [{"product_id": product_id, "qty": qty, "price": unit_price, "name": product.name}]
    order = await create_order(session, user.id, cart_items, promo_code)

    if promo_code:
        fsm_data.pop("promo_code", None)
        await state.set_data(fsm_data)

    discount_text = (
        f"\nСкидка: <b>-{order.discount_amount} ₽</b>"
        if order.discount_amount and float(order.discount_amount) > 0
        else ""
    )
    qty_text = f"{qty} шт. × {unit_price:.2f} ₽" if qty > 1 else f"{unit_price:.2f} ₽"
    text = (
        f"<b>Заказ #{order.id}</b>\n\n"
        f"📦 {product.name}\n"
        f"🔢 {qty_text}\n"
        f"💰 Итого: <b>{order.total_amount} ₽</b>{discount_text}\n\n"
        f"Выберите способ оплаты:"
    )
    from ..keyboards.user import payment_method_kb
    await call.message.edit_text(text, reply_markup=payment_method_kb(order.id), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("cat_back_"))
async def cb_back_to_category(call: CallbackQuery, session: AsyncSession):
    product_id = parse_callback_int(call.data, 2)
    if product_id is None:
        call.data = "catalog"
        await cb_catalog(call, session)
        return
    cat_id = await get_product_category_id(session, product_id)
    if cat_id:
        call.data = f"cat_{cat_id}"
        await cb_category(call, session)
    else:
        call.data = "catalog"
        await cb_catalog(call, session)


@router.callback_query(F.data == "noop")
async def cb_noop(call: CallbackQuery):
    await call.answer()
