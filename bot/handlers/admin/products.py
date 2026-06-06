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
    admin_categories_kb, admin_category_detail_kb, admin_confirm_kb,
    admin_select_category_kb, admin_subcategories_kb, admin_subcategory_detail_kb
)
from ...services.admin_service import (
    is_admin, get_all_products, get_root_categories,
    get_subcategories_admin, get_all_categories,
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
    waiting_subcat_name = State()
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

@router.callback_query(F.data.regexp(r"^admin_product_\d+$"))
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
        f"⚠️ Удалить товар <b>{product.name}</b>?\n\nТовар и все ключи будут удалены безвозвратно.",
        reply_markup=admin_confirm_kb("del_product", product_id),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("confirm_del_product_"))
async def cb_delete_product_do(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    await delete_product(session, product_id)
    await log_action(session, user.id, "delete_product", "product", product_id)
    await call.answer("✅ Товар удалён", show_alert=True)
    await call.message.edit_text("✅ Товар удалён.")


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
        f"🏷 <b>Скидка на {product.name}</b>\n\nВведите процент (1-99) или 0 для отмены скидки:",
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
        await message.answer(f"{plain(OK)} Скидка удалена.")
        return

    await state.update_data(discount_percent=str(pct))
    await state.set_state(ProductStates.waiting_discount_days)
    await message.answer("⏱ Введите длительность скидки в часах (0 = бессрочно):", reply_markup=cancel_kb())


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
    pct = Decimal(data.get("discount_percent"))
    expires_at = datetime.now(timezone.utc) + timedelta(hours=hours) if hours > 0 else None

    await set_product_discount(session, product_id, pct, expires_at)
    await log_action(session, user.id, "set_discount", "product", product_id, {"pct": str(pct), "hours": hours})
    await state.clear()
    exp_str = f"до {expires_at.strftime('%d.%m.%Y %H:%M')}" if expires_at else "бессрочно"
    await message.answer(f"{plain(OK)} Скидка <b>{pct}%</b> ({exp_str}).", parse_mode="HTML")


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
    builder.row(InlineKeyboardButton(text=f"◀️ Назад к товару", callback_data=f"admin_product_{product_id}"))

    text = (
        f"{STATS} <b>Остатки: {product.name}</b>\n"
        f"{'━' * 16}\n\n"
        f"📦 Всего ключей: <b>{stock['total']}</b>\n"
        f"✅ Доступно: <b>{stock['available']}</b>\n"
        f"🔑 Продано: <b>{stock['sold']}</b>"
    )
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()


# ─── ADD KEYS ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_add_keys_"))
async def cb_add_keys_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
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
    await call.message.edit_text(
        f"{KEY} <b>Добавление ключей: {product.name}</b>\n\n"
        f"Отправьте ключи — каждый с новой строки:",
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
    keys = [k.strip() for k in message.text.split("\n") if k.strip()]
    if not keys:
        await message.answer(f"{FAIL} Нет ключей для добавления.")
        return
    count = await add_product_keys(session, product_id, keys)
    await log_action(session, user.id, "add_keys", "product", product_id, {"count": count})
    await state.clear()
    await message.answer(f"{plain(OK)} Добавлено <b>{count}</b> ключей.", parse_mode="HTML")


# ─── ADD PRODUCT ─────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_add_product")
async def cb_add_product_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    # Показываем все категории (корневые + подкатегории) для выбора
    all_cats = await get_all_categories(session)
    active_cats = [c for c in all_cats if c.is_active]
    if not active_cats:
        await call.answer("Сначала создайте категорию!", show_alert=True)
        return

    await state.set_state(ProductStates.waiting_product_category)
    await call.message.edit_text(
        f"{ADD} <b>Новый товар</b>\n\nВыберите категорию:",
        reply_markup=admin_select_category_kb(active_cats, "admin_product_category_"),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_product_category_"))
async def cb_product_category_chosen(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return await call.answer("Категория не найдена", show_alert=True)

    await state.update_data(product_category_id=cat_id)
    await state.set_state(ProductStates.waiting_product_name)
    await call.message.edit_text(
        f"{ADD} <b>Новый товар в «{cat.name}»</b>\n\nВведите название товара:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(ProductStates.waiting_product_name)
async def process_product_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if len(name) < 2 or len(name) > 255:
        await message.answer(f"{FAIL} Название: от 2 до 255 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(product_name=name)
    await state.set_state(ProductStates.waiting_product_desc)
    await message.answer("📝 Введите описание товара (или напишите - чтобы пропустить):", reply_markup=cancel_kb())


@router.message(ProductStates.waiting_product_desc)
async def process_product_desc(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(product_desc=desc)
    await state.set_state(ProductStates.waiting_product_price)
    await message.answer("💰 Введите цену товара (в рублях):", reply_markup=cancel_kb())


@router.message(ProductStates.waiting_product_price)
async def process_product_price(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    try:
        price = Decimal(message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        await message.answer(f"{FAIL} Введите корректную цену (число > 0):", reply_markup=cancel_kb())
        return
    await state.update_data(product_price=str(price))
    await state.set_state(ProductStates.waiting_product_unlimited)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📦 Обычный", callback_data="product_unlimited_no"),
        InlineKeyboardButton(text="♾ Безлимитный", callback_data="product_unlimited_yes"),
    )
    await message.answer("Тип товара:", reply_markup=builder.as_markup())


@router.callback_query(F.data.in_({"product_unlimited_yes", "product_unlimited_no"}))
async def process_product_unlimited(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    is_unlimited = call.data == "product_unlimited_yes"
    data = await state.get_data()
    product = await create_product(
        session,
        category_id=data["product_category_id"],
        name=data["product_name"],
        description=data.get("product_desc", ""),
        price=Decimal(data["product_price"]),
        is_unlimited=is_unlimited,
    )
    await log_action(session, user.id, "create_product", "product", product.id)
    await state.clear()
    kind = "♾ безлимитный" if is_unlimited else "📦 обычный"
    await call.message.edit_text(
        f"{plain(OK)} <b>Товар создан!</b>\n\n"
        f"ID: {product.id}\n"
        f"Название: {product.name}\n"
        f"Цена: {product.price} ₽\n"
        f"Тип: {kind}",
        parse_mode="HTML"
    )
    await call.answer()


# ─── CATEGORIES ──────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_categories")
async def cb_admin_categories(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()
    cats = await get_root_categories(session)
    text = f"{CATALOG} <b>Категории</b>\n{'━' * 16}\n\nГлавных категорий: <b>{len(cats)}</b>"
    await call.message.edit_text(text, reply_markup=admin_categories_kb(cats), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.regexp(r"^admin_cat_\d+$"))
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

    subcats = await get_subcategories_admin(session, cat_id)
    status = f"{plain(OK)} Активна" if cat.is_active else f"{plain(FAIL)} Скрыта"
    text = (
        f"{CATALOG} <b>{cat.name}</b>\n"
        f"{'━' * 16}\n\n"
        f"Статус: {status}\n"
        f"Описание: {cat.description or '—'}\n"
        f"Подкатегорий: <b>{len(subcats)}</b>"
    )
    await call.message.edit_text(
        text,
        reply_markup=admin_category_detail_kb(cat_id, cat.is_active, has_subcats=len(subcats) > 0),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_subcats_"))
async def cb_admin_subcats(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    parent_id = parse_callback_int(call.data, 2)
    if parent_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Category).where(Category.id == parent_id))
    parent = result.scalar_one_or_none()
    if not parent:
        return await call.answer("Категория не найдена", show_alert=True)

    subcats = await get_subcategories_admin(session, parent_id)
    text = f"📁 <b>Подкатегории «{parent.name}»</b>\n\nВсего: <b>{len(subcats)}</b>"
    await call.message.edit_text(
        text,
        reply_markup=admin_subcategories_kb(subcats, parent_id),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_subcat_detail_"))
async def cb_admin_subcat_detail(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return await call.answer("Категория не найдена", show_alert=True)

    status = f"{plain(OK)} Активна" if cat.is_active else f"{plain(FAIL)} Скрыта"
    text = (
        f"📁 <b>{cat.name}</b>\n"
        f"{'━' * 16}\n\n"
        f"Статус: {status}\n"
        f"Описание: {cat.description or '—'}"
    )
    await call.message.edit_text(
        text,
        reply_markup=admin_subcategory_detail_kb(cat_id, cat.is_active, cat.parent_id or 0),
        parse_mode="HTML"
    )
    await call.answer()


# ─── ADD CATEGORY (корневая) ─────────────────────────────────────────

@router.callback_query(F.data == "admin_add_category")
async def cb_add_category_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.update_data(category_parent_id=None)
    await state.set_state(ProductStates.waiting_category_name)
    await call.message.edit_text(
        f"{ADD} <b>Новая главная категория</b>\n\nВведите название:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


# ─── ADD SUBCATEGORY ─────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_add_subcat_"))
async def cb_add_subcat_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    parent_id = parse_callback_int(call.data, 3)
    if parent_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Category).where(Category.id == parent_id))
    parent = result.scalar_one_or_none()
    if not parent:
        return await call.answer("Категория не найдена", show_alert=True)

    await state.update_data(category_parent_id=parent_id, parent_name=parent.name)
    await state.set_state(ProductStates.waiting_subcat_name)
    await call.message.edit_text(
        f"{ADD} <b>Подкатегория в «{parent.name}»</b>\n\nВведите название подкатегории:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(ProductStates.waiting_subcat_name)
async def process_subcat_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if len(name) < 2 or len(name) > 255:
        await message.answer(f"{FAIL} Название: от 2 до 255 символов.", reply_markup=cancel_kb())
        return

    data = await state.get_data()
    parent_id = data.get("category_parent_id")
    parent_name = data.get("parent_name", "")

    cat = await create_category(session, name, parent_id=parent_id)
    await log_action(session, user.id, "create_subcategory", "category", cat.id, {"parent_id": parent_id})
    await state.clear()
    await message.answer(
        f"{plain(OK)} Подкатегория <b>{cat.name}</b> создана в «{parent_name}».",
        parse_mode="HTML"
    )


@router.message(ProductStates.waiting_category_name)
async def process_category_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if len(name) < 2 or len(name) > 255:
        await message.answer(f"{FAIL} Название: от 2 до 255 символов.", reply_markup=cancel_kb())
        return

    data = await state.get_data()
    parent_id = data.get("category_parent_id")

    cat = await create_category(session, name, parent_id=parent_id)
    await log_action(session, user.id, "create_category", "category", cat.id)
    await state.clear()
    kind = "подкатегория" if parent_id else "главная категория"
    await message.answer(
        f"{plain(OK)} Создана {kind}: <b>{cat.name}</b>",
        parse_mode="HTML"
    )


# ─── TOGGLE / DELETE CATEGORY ────────────────────────────────────────

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
    await log_action(session, user.id, "toggle_category", "category", cat_id, {"active": cat.is_active})
    status = f"{plain(OK)} показана" if cat.is_active else f"{plain(FAIL)} скрыта"
    await call.answer(f"Категория {status}", show_alert=True)

    # Обновляем отображение
    call.data = f"admin_cat_{cat_id}"
    await cb_admin_cat_detail(call, session, user)


@router.callback_query(F.data.startswith("admin_delete_cat_"))
async def cb_delete_cat(call: CallbackQuery, session: AsyncSession, user: User):
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
        f"⚠️ Удалить категорию <b>{cat.name}</b>?\n\nВсе товары и подкатегории будут удалены безвозвратно.",
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
    await call.answer("✅ Категория удалена", show_alert=True)
    await call.message.edit_text("✅ Категория удалена.")
