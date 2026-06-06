from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone, timedelta
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...models import User, Product, Category
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


@router.callback_query(F.data == "admin_products")
async def cb_admin_products(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()
    products = await get_all_products(session)
    text = (
        f"{BAG} <b>Управление товарами</b>\n"
        f"{'━' * 16}\n\nВсего товаров: <b>{len(products)}</b>"
    )
    await call.message.edit_text(text, reply_markup=admin_products_kb(products), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("admin_product_") & ~F.data.startswith("admin_product_toggle_"))
async def cb_admin_product_detail(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 2)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)

    stock = await get_stock_for_product(session, product_id)
    status = f"{OK} Активен" if product.is_active else f"{FAIL} Отключён"
    unlimited_line = "\n♾ <b>Безлимитный</b> — один ключ, продаётся бесконечно" if product.is_unlimited else ""

    discount_line = ""
    if product.discount_percent:
        now = datetime.now(timezone.utc)
        if not product.discount_expires_at or product.discount_expires_at > now:
            sale_price = product.price * (1 - product.discount_percent / 100)
            expires_str = product.discount_expires_at.strftime("%d.%m.%Y") if product.discount_expires_at else "∞"
            discount_line = f"\n🏷 Скидка: <b>{product.discount_percent}%</b> → {sale_price:.2f} ₽ (до {expires_str})"
        else:
            discount_line = "\n🏷 Скидка: истекла"

    if product.is_unlimited:
        stock_line = f"{KEY} Ключ: {'загружен' if stock['total'] > 0 else '⚠️ не загружен!'}"
    else:
        stock_line = (
            f"{KEY} Ключей всего: <b>{stock['total']}</b>\n"
            f"{OK} Доступно: <b>{stock['available']}</b>\n"
            f"{FAIL} Продано: <b>{stock['sold']}</b>"
        )

    text = (
        f"{BAG} <b>{product.name}</b>\n{'━' * 16}\n\n"
        f"📌 Статус: {status}{unlimited_line}\n"
        f"💰 Цена: <b>{product.price} ₽</b>{discount_line}\n"
        f"{'━' * 16}\n{stock_line}\n"
        f"{'━' * 16}\n📝 {product.description or 'Без описания'}"
    )
    await call.message.edit_text(
        text, reply_markup=admin_product_detail_kb(product_id, product.is_active), parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_toggle_product_"))
async def cb_toggle_product(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    new_status = await toggle_product(session, product_id)
    await log_action(session, user.id, "toggle_product", "product", product_id, {"active": new_status})
    await call.answer(f"Товар {'включён' if new_status else 'отключён'}", show_alert=True)
    call.data = f"admin_product_{product_id}"
    await cb_admin_product_detail(call, session, user)


@router.callback_query(F.data.startswith("admin_delete_product_"))
async def cb_delete_product_confirm(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)
    await call.message.edit_text(
        f"⚠️ <b>Удалить товар?</b>\n\n«{product.name}» будет скрыт.",
        reply_markup=admin_confirm_kb("del_product", product_id), parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("confirm_del_product_"))
async def cb_delete_product_do(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    ok = await delete_product(session, product_id)
    await log_action(session, user.id, "delete_product", "product", product_id)
    if ok:
        await call.answer("Товар удалён", show_alert=True)
        products = await get_all_products(session)
        await call.message.edit_text(
            f"{BAG} <b>Управление товарами</b>\n{'━'*16}\n\nТоваров: <b>{len(products)}</b>",
            reply_markup=admin_products_kb(products), parse_mode="HTML"
        )
    else:
        await call.answer("Ошибка удаления", show_alert=True)


@router.callback_query(F.data.startswith("admin_change_price_"))
async def cb_change_price_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)
    await state.set_state(ProductStates.waiting_new_price)
    await state.update_data(change_price_product_id=product_id)
    await call.message.edit_text(
        f"💰 <b>Изменение цены</b>\n\nТовар: <b>{product.name}</b>\n"
        f"Текущая цена: <b>{product.price} ₽</b>\n\nВведите новую цену:",
        reply_markup=cancel_kb(), parse_mode="HTML"
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
        await message.answer(f"{FAIL} Введите корректную цену:", reply_markup=cancel_kb())
        return
    data = await state.get_data()
    ok = await update_product_price(session, data.get("change_price_product_id"), price)
    await log_action(session, user.id, "change_price", "product", data.get("change_price_product_id"), {"price": str(price)})
    await state.clear()
    await message.answer(f"{OK} Цена обновлена: <b>{price} ₽</b>", parse_mode="HTML")


@router.callback_query(F.data.startswith("admin_set_discount_"))
async def cb_set_discount_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)
    await state.set_state(ProductStates.waiting_discount_percent)
    await state.update_data(discount_product_id=product_id)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="10%", callback_data="disc_pct_10"),
        InlineKeyboardButton(text="20%", callback_data="disc_pct_20"),
        InlineKeyboardButton(text="30%", callback_data="disc_pct_30"),
    )
    builder.row(
        InlineKeyboardButton(text="50%", callback_data="disc_pct_50"),
        InlineKeyboardButton(text="70%", callback_data="disc_pct_70"),
        InlineKeyboardButton(text="❌ Убрать скидку", callback_data="disc_pct_remove"),
    )
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_cancel_state"))
    current = f"{product.discount_percent}%" if product.discount_percent else "нет"
    await call.message.edit_text(
        f"🏷 <b>Скидка на «{product.name}»</b>\n\nТекущая: <b>{current}</b>\nВыберите % или введите своё:",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("disc_pct_"), ProductStates.waiting_discount_percent)
async def cb_discount_percent_choice(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    pct_str = call.data.replace("disc_pct_", "")
    data = await state.get_data()
    product_id = data.get("discount_product_id")
    if pct_str == "remove":
        await set_product_discount(session, product_id, None, None)
        await log_action(session, user.id, "remove_discount", "product", product_id)
        await state.clear()
        await call.message.edit_text(f"{OK} Скидка убрана", parse_mode="HTML")
        await call.answer("Скидка убрана!")
        return
    try:
        pct = Decimal(pct_str)
    except InvalidOperation:
        await call.answer("Ошибка", show_alert=True)
        return
    await state.update_data(discount_percent=pct)
    await state.set_state(ProductStates.waiting_discount_days)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 день", callback_data="disc_days_1"),
        InlineKeyboardButton(text="3 дня", callback_data="disc_days_3"),
        InlineKeyboardButton(text="7 дней", callback_data="disc_days_7"),
    )
    builder.row(
        InlineKeyboardButton(text="30 дней", callback_data="disc_days_30"),
        InlineKeyboardButton(text="♾ Бессрочно", callback_data="disc_days_0"),
    )
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_cancel_state"))
    await call.message.edit_text(f"📅 Скидка <b>{pct}%</b> — на сколько?", reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()


@router.message(ProductStates.waiting_discount_percent)
async def process_discount_percent_text(message: Message, state: FSMContext):
    try:
        pct = Decimal(message.text.strip().replace(",", "."))
        if pct <= 0 or pct > 100:
            raise ValueError()
    except (InvalidOperation, ValueError):
        await message.answer(f"{FAIL} Введите число от 1 до 100:", reply_markup=cancel_kb())
        return
    await state.update_data(discount_percent=pct)
    await state.set_state(ProductStates.waiting_discount_days)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="1 день", callback_data="disc_days_1"),
        InlineKeyboardButton(text="3 дня", callback_data="disc_days_3"),
        InlineKeyboardButton(text="7 дней", callback_data="disc_days_7"),
    )
    builder.row(
        InlineKeyboardButton(text="30 дней", callback_data="disc_days_30"),
        InlineKeyboardButton(text="♾ Бессрочно", callback_data="disc_days_0"),
    )
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_cancel_state"))
    await message.answer(f"📅 Скидка <b>{pct}%</b> — на сколько?", reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data.startswith("disc_days_"), ProductStates.waiting_discount_days)
async def cb_discount_days(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    days = int(call.data.replace("disc_days_", ""))
    data = await state.get_data()
    product_id = data.get("discount_product_id")
    pct = data.get("discount_percent")
    expires_at = datetime.now(timezone.utc) + timedelta(days=days) if days > 0 else None
    await set_product_discount(session, product_id, pct, expires_at)
    await log_action(session, user.id, "set_discount", "product", product_id, {"pct": str(pct), "days": days})
    await state.clear()
    expires_str = expires_at.strftime("%d.%m.%Y") if expires_at else "бессрочно"
    await call.message.edit_text(
        f"{OK} <b>Скидка установлена!</b>\n🏷 {pct}%\n📅 До: <b>{expires_str}</b>", parse_mode="HTML"
    )
    await call.answer("Скидка установлена!")


@router.callback_query(F.data.startswith("admin_stock_"))
async def cb_admin_stock(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 2)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    stock = await get_stock_for_product(session, product_id)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=f"{plain(ADD)} Добавить ключи", callback_data=f"admin_add_keys_{product_id}"))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data=f"admin_product_{product_id}"))
    if product and product.is_unlimited:
        stock_text = f"♾ Безлимитный товар\n{KEY} Ключ: {'загружен' if stock['total'] > 0 else '⚠️ не загружен'}"
    else:
        stock_text = (
            f"{KEY} Всего: <b>{stock['total']}</b>\n"
            f"{OK} Доступно: <b>{stock['available']}</b>\n"
            f"{FAIL} Продано: <b>{stock['sold']}</b>"
        )
    await call.message.edit_text(
        f"{STATS} <b>Остатки #{product_id}</b>\n{'━'*16}\n\n{stock_text}",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_add_keys_"))
async def cb_admin_add_keys_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    await state.set_state(ProductStates.waiting_keys)
    await state.update_data(keys_product_id=product_id)
    if product and product.is_unlimited:
        hint = (
            f"{KEY} <b>Загрузка данных (безлимитный)</b>\n\n"
            f"Отправьте <b>один</b> ключ/данные — они будут показываться каждому покупателю:"
        )
    else:
        hint = (
            f"{KEY} <b>Добавление ключей</b>\n\n"
            f"Каждый ключ — с новой строки:\n<code>KEY-1234\nKEY-5678</code>"
        )
    await call.message.edit_text(hint, reply_markup=cancel_kb(), parse_mode="HTML")
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
        from ...models import ProductItem
        await session.execute(sa_delete(ProductItem).where(ProductItem.product_id == product_id))
        keys = [message.text.strip()]
    else:
        keys = [line.strip() for line in message.text.splitlines() if line.strip()]

    count = await add_product_keys(session, product_id, keys)
    await log_action(session, user.id, "add_keys", "product", product_id, {"count": count})
    await state.clear()

    if product and product.is_unlimited:
        await message.answer(f"{OK} <b>Данные загружены!</b> Будут выдаваться каждому покупателю.", parse_mode="HTML")
    else:
        await message.answer(f"{OK} <b>Загружено {count} ключей</b>", parse_mode="HTML")


@router.callback_query(F.data == "admin_add_product")
async def cb_admin_add_product(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    categories = await get_all_categories(session)
    if not categories:
        await call.answer("❌ Сначала создайте категорию!", show_alert=True)
        return
    await state.set_state(ProductStates.waiting_product_category)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(InlineKeyboardButton(text=cat.name, callback_data=f"select_cat_{cat.id}"))
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_cancel_state"))
    await call.message.edit_text(
        f"{ADD} <b>Новый товар</b>\n\nВыберите категорию:", reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("select_cat_"), ProductStates.waiting_product_category)
async def cb_select_category(call: CallbackQuery, state: FSMContext):
    cat_id = parse_callback_int(call.data, 2)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    await state.update_data(product_category_id=cat_id)
    await state.set_state(ProductStates.waiting_product_name)
    await call.message.edit_text(
        f"{ADD} Введите <b>название</b> товара:", reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await call.answer()


@router.message(ProductStates.waiting_product_name)
async def process_product_name(message: Message, state: FSMContext):
    await state.update_data(product_name=message.text.strip())
    await state.set_state(ProductStates.waiting_product_desc)
    await message.answer(
        f"{EDIT} Введите <b>описание</b> (или «-» чтобы пропустить):", reply_markup=cancel_kb(), parse_mode="HTML"
    )


@router.message(ProductStates.waiting_product_desc)
async def process_product_desc(message: Message, state: FSMContext):
    desc = message.text.strip()
    if desc == "-":
        desc = ""
    await state.update_data(product_desc=desc)
    await state.set_state(ProductStates.waiting_product_price)
    await message.answer(
        f"💰 Введите <b>цену</b> в рублях:", reply_markup=cancel_kb(), parse_mode="HTML"
    )


@router.message(ProductStates.waiting_product_price)
async def process_product_price(message: Message, state: FSMContext):
    try:
        price = Decimal(message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        await message.answer(f"{FAIL} Введите корректную цену:", reply_markup=cancel_kb(), parse_mode="HTML")
        return
    await state.update_data(product_price=price)
    await state.set_state(ProductStates.waiting_product_unlimited)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="♾ Безлимитный (1 ключ навсегда)", callback_data="prod_unlimited_yes"),
        InlineKeyboardButton(text="📦 Обычный (ключи расходуются)", callback_data="prod_unlimited_no"),
    )
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_cancel_state"))
    await message.answer(
        f"<b>Тип товара:</b>\n\n"
        f"♾ <b>Безлимитный</b> — загружаете один ключ/данные, он выдаётся каждому покупателю (подходит для инструкций, промокодов, ссылок)\n\n"
        f"📦 <b>Обычный</b> — загружаете уникальные ключи, каждый выдаётся один раз",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )


@router.callback_query(
    F.data.in_({"prod_unlimited_yes", "prod_unlimited_no"}),
    ProductStates.waiting_product_unlimited,
)
async def process_product_unlimited(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    is_unlimited = call.data == "prod_unlimited_yes"
    data = await state.get_data()
    product = await create_product(
        session,
        category_id=data["product_category_id"],
        name=data["product_name"],
        description=data.get("product_desc", ""),
        price=data["product_price"],
        is_unlimited=is_unlimited,
    )
    await log_action(session, user.id, "create_product", "product", product.id)
    await state.clear()
    unlimited_hint = (
        "\n\n♾ Теперь загрузите <b>один ключ/данные</b> через «Добавить ключи»."
        if is_unlimited else
        "\n\nТеперь загрузите ключи через «Добавить ключи» / «Остатки»."
    )
    await call.message.edit_text(
        f"{OK} <b>Товар создан!</b>\n\n"
        f"{TAG} {product.name}\n"
        f"💰 {product.price} ₽\n"
        f"{'♾ Безлимитный' if is_unlimited else '📦 Обычный'}"
        f"{unlimited_hint}",
        parse_mode="HTML"
    )
    await call.answer("Создано!")


@router.callback_query(F.data == "admin_categories")
async def cb_admin_categories(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()
    categories = await get_all_categories(session)
    await call.message.edit_text(
        f"{CATALOG} <b>Категории</b>\n{'━'*16}\n\nВсего: <b>{len(categories)}</b>",
        reply_markup=admin_categories_kb(categories), parse_mode="HTML"
    )
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
    status = f"{OK} Активна" if cat.is_active else f"{FAIL} Скрыта"
    products_count = len(cat.products) if cat.products else 0
    await call.message.edit_text(
        f"{CATALOG} <b>{cat.name}</b>\n{'━'*16}\n\n📌 {status}\n{BAG} Товаров: <b>{products_count}</b>\n📝 {cat.description or 'Нет описания'}",
        reply_markup=admin_category_detail_kb(cat_id, cat.is_active), parse_mode="HTML"
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
    await call.answer(f"Категория {'показана' if cat.is_active else 'скрыта'}", show_alert=True)
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
        f"⚠️ <b>Удалить категорию «{cat.name}»?</b>\n\nВсе товары будут скрыты.",
        reply_markup=admin_confirm_kb("del_cat", cat_id), parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("confirm_del_cat_"))
async def cb_delete_cat_do(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    ok = await delete_category(session, cat_id)
    await log_action(session, user.id, "delete_category", "category", cat_id)
    if ok:
        await call.answer("Категория удалена", show_alert=True)
        categories = await get_all_categories(session)
        await call.message.edit_text(
            f"{CATALOG} <b>Категории</b>\n{'━'*16}\n\nВсего: <b>{len(categories)}</b>",
            reply_markup=admin_categories_kb(categories), parse_mode="HTML"
        )
    else:
        await call.answer("Ошибка удаления", show_alert=True)


@router.callback_query(F.data == "admin_add_category")
async def cb_add_category(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.set_state(ProductStates.waiting_category_name)
    await call.message.edit_text(
        f"{ADD} <b>Новая категория</b>\n\nВведите название:", reply_markup=cancel_kb(), parse_mode="HTML"
    )
    await call.answer()


@router.message(ProductStates.waiting_category_name)
async def process_category_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    cat = await create_category(session, message.text.strip())
    await log_action(session, user.id, "create_category", "category", cat.id)
    await state.clear()
    await message.answer(f"{OK} Категория <b>{cat.name}</b> создана!", parse_mode="HTML")
