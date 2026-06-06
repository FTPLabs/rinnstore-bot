from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...models import User, Product, Category, ProductItem
from ...keyboards.admin import (
    admin_products_kb, admin_product_detail_kb, cancel_kb,
    admin_categories_kb, admin_category_detail_kb, admin_confirm_kb
)
from ...services.admin_service import (
    is_admin, get_all_products, get_all_categories,
    create_category, create_product, toggle_product,
    add_product_keys, get_stock_for_product, log_action,
    delete_product, delete_category, update_product_price, set_product_discount
)
from ...utils.helpers import parse_callback_int
from ...utils.emoji import (
    BAG, KEY, OK, FAIL, ADD, EDIT, STATS, BACK, CATALOG, TAG, plain
)

router = Router()


class ProductStates(StatesGroup):
    waiting_category_name = State()
    waiting_product_category = State()
    waiting_product_name = State()
    waiting_product_desc = State()
    waiting_product_price = State()
    waiting_product_unlimited = State()
    waiting_keys = State()
    waiting_new_price = State()
    waiting_discount_percent = State()
    waiting_discount_days = State()


# ─── PRODUCTS LIST ───────────────────────────────────────────────────

@router.callback_query(F.data == "admin_products")
async def cb_admin_products(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()
    products = await get_all_products(session)
    text = (
        f"{BAG} <b>Товары</b>\n"
        f"{'━' * 16}\n\n"
        f"Всего: <b>{len(products)}</b>"
    )
    await call.message.edit_text(text, reply_markup=admin_products_kb(products), parse_mode="HTML")
    await call.answer()


# ─── PRODUCT DETAIL ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_product_") & ~F.data.startswith("admin_product_category_"))
async def cb_admin_product_detail(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 2)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)

    stock = await get_stock_for_product(session, product_id)
    kind = "♾ Безлимитный" if product.is_unlimited else "📦 Обычный"
    status = f"{plain(OK)} Активен" if product.is_active else f"{plain(FAIL)} Скрыт"

    disc_text = ""
    if product.discount_percent:
        exp = ""
        if product.discount_expires_at:
            exp = f" до {product.discount_expires_at.strftime('%d.%m.%Y %H:%M')}"
        disc_text = f"\n🏷 Скидка: <b>{product.discount_percent}%</b>{exp}"

    text = (
        f"{BAG} <b>{product.name}</b>\n"
        f"{'━' * 16}\n\n"
        f"📌 Статус: {status}\n"
        f"📂 Тип: {kind}\n"
        f"💰 Цена: <b>{product.price} ₽</b>{disc_text}\n"
        f"{'━' * 16}\n"
        f"{STATS} Всего: {stock['total']} | Доступно: {stock['available']} | Продано: {stock['sold']}"
    )
    await call.message.edit_text(
        text,
        reply_markup=admin_product_detail_kb(product_id, product.is_active),
        parse_mode="HTML"
    )
    await call.answer()


# ─── TOGGLE PRODUCT ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_toggle_product_"))
async def cb_toggle_product(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    new_active = await toggle_product(session, product_id)
    await log_action(session, user.id, "toggle_product", "product", product_id, {"active": new_active})
    status = f"{plain(OK)} включён" if new_active else f"{plain(FAIL)} скрыт"
    await call.answer(f"Товар {status}", show_alert=True)
    call.data = f"admin_product_{product_id}"
    await cb_admin_product_detail(call, session, user)


# ─── DELETE PRODUCT ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_delete_product_"))
async def cb_delete_product_confirm(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)

    await call.message.edit_text(
        f"⚠️ Удалить товар <b>{product.name}</b>?\n\n"
        f"Все ключи будут помечены как проданные.",
        reply_markup=admin_confirm_kb("del_product", product_id),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("confirm_del_product_"))
async def cb_delete_product_do(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    await delete_product(session, product_id)
    await log_action(session, user.id, "delete_product", "product", product_id)
    await call.answer(f"{plain(OK)} Товар удалён", show_alert=True)
    call.data = "admin_products"
    await cb_admin_products(call, session, user, state=None)


# ─── CHANGE PRICE ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_change_price_"))
async def cb_change_price_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)

    await state.update_data(price_product_id=product_id)
    await state.set_state(ProductStates.waiting_new_price)
    await call.message.edit_text(
        f"💰 <b>{product.name}</b>\n\nТекущая цена: <b>{product.price} ₽</b>\n\nВведите новую цену:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(ProductStates.waiting_new_price)
async def process_new_price(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    try:
        price = Decimal(message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        await message.answer(f"{FAIL} Введите корректную цену (число > 0):", reply_markup=cancel_kb())
        return

    data = await state.get_data()
    product_id = data.get("price_product_id")
    await update_product_price(session, product_id, price)
    await log_action(session, user.id, "change_price", "product", product_id, {"price": str(price)})
    await state.clear()
    await message.answer(f"{plain(OK)} Цена обновлена: <b>{price} ₽</b>", parse_mode="HTML")


# ─── DISCOUNT ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_set_discount_"))
async def cb_set_discount_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)

    await state.update_data(discount_product_id=product_id)
    await state.set_state(ProductStates.waiting_discount_percent)
    await call.message.edit_text(
        f"🏷 <b>Скидка на {product.name}</b>\n\nВведите процент скидки (1-99) или 0 для отмены скидки:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(ProductStates.waiting_discount_percent)
async def process_discount_percent(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    try:
        pct = Decimal(message.text.strip().replace(",", "."))
        if pct < 0 or pct > 99:
            raise ValueError()
    except (InvalidOperation, ValueError):
        await message.answer(f"{FAIL} Введите число от 0 до 99:", reply_markup=cancel_kb())
        return

    data = await state.get_data()
    product_id = data.get("discount_product_id")

    if pct == 0:
        await set_product_discount(session, product_id, None, None)
        await log_action(session, user.id, "remove_discount", "product", product_id)
        await state.clear()
        await message.answer(f"{plain(OK)} Скидка удалена.", parse_mode="HTML")
        return

    await state.update_data(discount_percent=pct)
    await state.set_state(ProductStates.waiting_discount_days)
    await message.answer(
        "⏱ Введите длительность скидки в часах (0 = бессрочно):",
        reply_markup=cancel_kb()
    )


@router.message(ProductStates.waiting_discount_days)
async def process_discount_days(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    try:
        hours = int(message.text.strip())
        if hours < 0:
            raise ValueError()
    except ValueError:
        await message.answer(f"{FAIL} Введите число часов (0 = бессрочно):", reply_markup=cancel_kb())
        return

    data = await state.get_data()
    product_id = data.get("discount_product_id")
    pct = data.get("discount_percent")
    expires_at = datetime.now(timezone.utc) + timedelta(hours=hours) if hours > 0 else None

    await set_product_discount(session, product_id, pct, expires_at)
    await log_action(session, user.id, "set_discount", "product", product_id, {"pct": str(pct), "hours": hours})
    await state.clear()
    exp_str = f"до {expires_at.strftime('%d.%m.%Y %H:%M')}" if expires_at else "бессрочно"
    await message.answer(
        f"{plain(OK)} Скидка <b>{pct}%</b> установлена ({exp_str}).",
        parse_mode="HTML"
    )


# ─── STOCK ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_stock_"))
async def cb_admin_stock(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 2)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)

    stock = await get_stock_for_product(session, product_id)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"{plain(BAG)} Назад к товару",
        callback_data=f"admin_product_{product_id}"
    ))

    text = (
        f"{STATS} <b>Остатки: {product.name}</b>\n"
        f"{'━' * 16}\n\n"
        f"📦 Всего ключей: <b>{stock['total']}</b>\n"
        f"✅ Доступно: <b>{stock['available']}</b>\n"
        f"📤 Продано: <b>{stock['sold']}</b>"
    )
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()


# ─── ADD KEYS ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_add_keys_"))
async def cb_admin_add_keys_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)

    await state.update_data(keys_product_id=product_id)
    await state.set_state(ProductStates.waiting_keys)

    hint = (
        "Это <b>безлимитный</b> товар — загрузите один ключ/данные.\nОн будет выдаваться всем покупателям."
        if product.is_unlimited else
        "Введите ключи/данные — по одному на строку."
    )
    await call.message.edit_text(
        f"{KEY} <b>Ключи для {product.name}</b>\n\n{hint}",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(ProductStates.waiting_keys)
async def process_keys(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    data = await state.get_data()
    product_id = data.get("keys_product_id")

    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()

    if product and product.is_unlimited:
        from sqlalchemy import delete as sa_delete
        await session.execute(sa_delete(ProductItem).where(ProductItem.product_id == product_id))
        await session.commit()
        keys = [message.text.strip()]
    else:
        keys = [line.strip() for line in message.text.splitlines() if line.strip()]

    count = await add_product_keys(session, product_id, keys)
    await log_action(session, user.id, "add_keys", "product", product_id, {"count": count})
    await state.clear()

    kind_note = " (безлимитный, 1 ключ)" if product and product.is_unlimited else ""
    await message.answer(
        f"{plain(OK)} Добавлено <b>{count}</b> ключей{kind_note}.",
        parse_mode="HTML"
    )


# ─── CATEGORIES ──────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_categories")
async def cb_admin_categories(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()
    categories = await get_all_categories(session)
    text = (
        f"{CATALOG} <b>Категории</b>\n"
        f"{'━' * 16}\n\n"
        f"Всего: <b>{len(categories)}</b>"
    )
    await call.message.edit_text(text, reply_markup=admin_categories_kb(categories), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("admin_cat_"))
async def cb_admin_cat_detail(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 2)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return await call.answer("Категория не найдена", show_alert=True)

    status = f"{plain(OK)} Активна" if cat.is_active else f"{plain(FAIL)} Скрыта"
    text = (
        f"{CATALOG} <b>{cat.name}</b>\n"
        f"{'━' * 16}\n\n"
        f"📌 Статус: {status}\n"
        f"📝 Описание: {cat.description or '—'}"
    )
    await call.message.edit_text(
        text,
        reply_markup=admin_category_detail_kb(cat_id, cat.is_active),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_toggle_cat_"))
async def cb_toggle_cat(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return await call.answer("Категория не найдена", show_alert=True)
    cat.is_active = not cat.is_active
    await session.commit()
    await log_action(session, user.id, "toggle_cat", "category", cat_id, {"active": cat.is_active})
    status = "показана" if cat.is_active else "скрыта"
    await call.answer(f"Категория {status}", show_alert=True)
    call.data = f"admin_cat_{cat_id}"
    await cb_admin_cat_detail(call, session, user)


@router.callback_query(F.data.startswith("admin_delete_cat_"))
async def cb_delete_cat_confirm(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return await call.answer("Категория не найдена", show_alert=True)

    await call.message.edit_text(
        f"⚠️ Удалить категорию <b>{cat.name}</b>?\n\nВсе товары категории будут скрыты.",
        reply_markup=admin_confirm_kb("del_cat", cat_id),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("confirm_del_cat_"))
async def cb_delete_cat_do(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    await delete_category(session, cat_id)
    await log_action(session, user.id, "delete_category", "category", cat_id)
    await call.answer(f"{plain(OK)} Категория удалена", show_alert=True)
    call.data = "admin_categories"
    await cb_admin_categories(call, session, user, state)


# ─── ADD CATEGORY ────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_add_category")
async def cb_admin_add_category(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()
    await state.set_state(ProductStates.waiting_category_name)
    await call.message.edit_text(
        f"{ADD} <b>Новая категория</b>\n\nВведите название:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(ProductStates.waiting_category_name)
async def process_category_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым.", reply_markup=cancel_kb())
        return
    cat = await create_category(session, name)
    await log_action(session, user.id, "create_category", "category", cat.id, {"name": name})
    await state.clear()
    await message.answer(
        f"{plain(OK)} Категория <b>{cat.name}</b> создана!",
        parse_mode="HTML"
    )


# ─── ADD PRODUCT FLOW ────────────────────────────────────────────────

@router.callback_query(F.data == "admin_add_product")
async def cb_admin_add_product(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()

    categories = await get_all_categories(session)
    active_cats = [c for c in categories if c.is_active]
    if not active_cats:
        await call.answer("Сначала создайте категорию!", show_alert=True)
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for cat in active_cats:
        builder.row(InlineKeyboardButton(
            text=cat.name,
            callback_data=f"admin_product_category_{cat.id}"
        ))
    builder.row(InlineKeyboardButton(text=f"{plain(FAIL)} Отмена", callback_data="admin_cancel_state"))

    await state.set_state(ProductStates.waiting_product_category)
    await call.message.edit_text(
        f"{ADD} <b>Новый товар</b>\n\nВыберите категорию:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_product_category_"), ProductStates.waiting_product_category)
async def cb_product_category_select(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    await state.update_data(new_product_category_id=cat_id)
    await state.set_state(ProductStates.waiting_product_name)
    await call.message.edit_text(
        f"{ADD} Введите название товара:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(ProductStates.waiting_product_name)
async def process_product_name(message: Message, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if not name:
        await message.answer("Название не может быть пустым.", reply_markup=cancel_kb())
        return
    await state.update_data(new_product_name=name)
    await state.set_state(ProductStates.waiting_product_desc)
    await message.answer(
        "📝 Введите описание товара (или «-» чтобы пропустить):",
        reply_markup=cancel_kb()
    )


@router.message(ProductStates.waiting_product_desc)
async def process_product_desc(message: Message, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return
    desc = message.text.strip()
    if desc == "-":
        desc = ""
    await state.update_data(new_product_desc=desc)
    await state.set_state(ProductStates.waiting_product_price)
    await message.answer("💰 Введите цену в рублях:", reply_markup=cancel_kb())


@router.message(ProductStates.waiting_product_price)
async def process_product_price(message: Message, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return
    try:
        price = Decimal(message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        await message.answer(f"{FAIL} Введите корректную цену (число > 0):", reply_markup=cancel_kb())
        return

    await state.update_data(new_product_price=price)
    await state.set_state(ProductStates.waiting_product_unlimited)

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="♾ Безлимитный", callback_data="product_type_unlimited"),
        InlineKeyboardButton(text="📦 Обычный", callback_data="product_type_regular"),
    )
    builder.row(InlineKeyboardButton(text=f"{plain(FAIL)} Отмена", callback_data="admin_cancel_state"))
    await message.answer(
        "📦 Выберите тип товара:\n\n"
        "♾ <b>Безлимитный</b> — один ключ выдаётся всем покупателям\n"
        "📦 <b>Обычный</b> — каждый ключ выдаётся только один раз",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "product_type_unlimited", ProductStates.waiting_product_unlimited)
async def cb_product_type_unlimited(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    data = await state.get_data()
    product = await create_product(
        session,
        category_id=data["new_product_category_id"],
        name=data["new_product_name"],
        description=data.get("new_product_desc", ""),
        price=data["new_product_price"],
        is_unlimited=True,
    )
    await log_action(session, user.id, "create_product", "product", product.id, {"name": product.name, "unlimited": True})
    await state.clear()
    await call.message.edit_text(
        f"{plain(OK)} Товар <b>{product.name}</b> создан (безлимитный)!\n\n"
        f"Теперь добавьте ключ/данные через кнопку «Добавить ключи».",
        parse_mode="HTML"
    )
    await call.answer("Товар создан!")


@router.callback_query(F.data == "product_type_regular", ProductStates.waiting_product_unlimited)
async def cb_product_type_regular(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    data = await state.get_data()
    product = await create_product(
        session,
        category_id=data["new_product_category_id"],
        name=data["new_product_name"],
        description=data.get("new_product_desc", ""),
        price=data["new_product_price"],
        is_unlimited=False,
    )
    await log_action(session, user.id, "create_product", "product", product.id, {"name": product.name, "unlimited": False})
    await state.clear()
    await call.message.edit_text(
        f"{plain(OK)} Товар <b>{product.name}</b> создан!\n\n"
        f"Добавьте ключи через кнопку «Добавить ключи».",
        parse_mode="HTML"
    )
    await call.answer("Товар создан!")
