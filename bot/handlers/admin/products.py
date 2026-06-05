from decimal import Decimal, InvalidOperation
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ...models import User, Product, Category
from ...keyboards.admin import (
    admin_products_kb, admin_product_detail_kb, cancel_kb, admin_categories_kb
)
from ...services.admin_service import (
    is_admin, get_all_products, get_all_categories,
    create_category, create_product, toggle_product,
    add_product_keys, get_stock_for_product, log_action
)
from ...utils.emoji import (
    BAG, KEY, OK, FAIL, ADD, EDIT, STATS, BACK, CATALOG, TAG, STAR, plain
)

router = Router()


class ProductStates(StatesGroup):
    waiting_category_name = State()
    waiting_category_desc = State()
    waiting_product_category = State()
    waiting_product_name = State()
    waiting_product_desc = State()
    waiting_product_price = State()
    waiting_keys = State()
    waiting_keys_product_id = State()


@router.callback_query(F.data == "admin_products")
async def cb_admin_products(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    products = await get_all_products(session)
    text = (
        f"{BAG} <b>Управление товарами</b>\n"
        f"{'━' * 16}\n\n"
        f"Всего товаров: <b>{len(products)}</b>"
    )
    await call.message.edit_text(text, reply_markup=admin_products_kb(products), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("admin_product_"))
async def cb_admin_product_detail(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    from ...utils.helpers import parse_callback_int
    product_id = parse_callback_int(call.data, 2)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if not product:
        return await call.answer("Товар не найден", show_alert=True)

    stock = await get_stock_for_product(session, product_id)
    status = f"{OK} Активен" if product.is_active else f"{FAIL} Отключён"
    text = (
        f"{BAG} <b>{product.name}</b>\n"
        f"{'━' * 16}\n\n"
        f"📌 Статус: {status}\n"
        f"💰 Цена: <b>{product.price} руб.</b>\n"
        f"{'━' * 16}\n"
        f"{KEY} Всего ключей: <b>{stock['total']}</b>\n"
        f"{OK} Доступно: <b>{stock['available']}</b>\n"
        f"{FAIL} Продано: <b>{stock['sold']}</b>\n"
        f"{'━' * 16}\n"
        f"📝 {product.description or 'Без описания'}"
    )
    await call.message.edit_text(
        text,
        reply_markup=admin_product_detail_kb(product_id, product.is_active),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.startswith("admin_toggle_product_"))
async def cb_toggle_product(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    new_status = await toggle_product(session, product_id)
    await log_action(session, user.id, "toggle_product", "product", product_id, {"active": new_status})
    status_text = f"{plain(OK)} включён" if new_status else f"{plain(FAIL)} отключён"
    await call.answer(f"Товар {status_text}", show_alert=True)
    call.data = f"admin_product_{product_id}"
    await cb_admin_product_detail(call, session, user)


@router.callback_query(F.data.startswith("admin_stock_"))
async def cb_admin_stock(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    from ...utils.helpers import parse_callback_int
    product_id = parse_callback_int(call.data, 2)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    stock = await get_stock_for_product(session, product_id)
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"{plain(ADD)} Добавить ключи",
        callback_data=f"admin_add_keys_{product_id}"
    ))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data=f"admin_product_{product_id}"))
    text = (
        f"{STATS} <b>Остатки товара #{product_id}</b>\n"
        f"{'━' * 16}\n\n"
        f"{KEY} Всего загружено: <b>{stock['total']}</b>\n"
        f"{OK} Доступно: <b>{stock['available']}</b>\n"
        f"{FAIL} Продано: <b>{stock['sold']}</b>"
    )
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data.startswith("admin_add_keys_"))
async def cb_admin_add_keys_start(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    product_id = parse_callback_int(call.data, 3)
    if product_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    await state.set_state(ProductStates.waiting_keys)
    await state.update_data(keys_product_id=product_id)
    await call.message.edit_text(
        f"{KEY} <b>Добавление ключей</b>\n"
        f"{'━' * 16}\n\n"
        f"Отправьте ключи — каждый с новой строки.\n\n"
        f"Пример:\n<code>KEY-1234-ABCD\nKEY-5678-EFGH</code>",
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
    keys = [line.strip() for line in message.text.splitlines() if line.strip()]
    count = await add_product_keys(session, product_id, keys)
    await log_action(session, user.id, "add_keys", "product", product_id, {"count": count})
    await state.clear()
    await message.answer(
        f"{OK} <b>Загружено {count} ключей</b> для товара #{product_id}",
        parse_mode="HTML"
    )


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
        builder.row(InlineKeyboardButton(
            text=cat.name,
            callback_data=f"select_cat_{cat.id}"
        ))
    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Отмена", callback_data="admin_products"))
    await call.message.edit_text(
        f"{ADD} <b>Новый товар</b>\n\nВыберите категорию:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
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
        f"{ADD} <b>Название товара</b>\n\nВведите название:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(ProductStates.waiting_product_name)
async def process_product_name(message: Message, state: FSMContext):
    await state.update_data(product_name=message.text.strip())
    await state.set_state(ProductStates.waiting_product_desc)
    await message.answer(
        f"{EDIT} <b>Описание товара</b>\n\nВведите описание (или отправьте «-» чтобы пропустить):",
        parse_mode="HTML"
    )


@router.message(ProductStates.waiting_product_desc)
async def process_product_desc(message: Message, state: FSMContext):
    desc = message.text.strip()
    if desc == "-":
        desc = ""
    await state.update_data(product_desc=desc)
    await state.set_state(ProductStates.waiting_product_price)
    await message.answer(
        f"💰 <b>Цена товара</b>\n\nВведите цену в рублях (например: <code>499</code>):",
        parse_mode="HTML"
    )


@router.message(ProductStates.waiting_product_price)
async def process_product_price(message: Message, session: AsyncSession, user: User, state: FSMContext):
    try:
        price = Decimal(message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        await message.answer(f"{FAIL} Введите корректную цену (число больше 0):", parse_mode="HTML")
        return

    data = await state.get_data()
    product = await create_product(
        session,
        category_id=data["product_category_id"],
        name=data["product_name"],
        description=data.get("product_desc", ""),
        price=price,
    )
    await log_action(session, user.id, "create_product", "product", product.id)
    await state.clear()
    await message.answer(
        f"{OK} <b>Товар создан!</b>\n\n"
        f"{TAG} Название: <b>{product.name}</b>\n"
        f"💰 Цена: <b>{product.price} руб.</b>\n\n"
        f"Теперь добавьте ключи через меню товара.",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_categories")
async def cb_admin_categories(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    categories = await get_all_categories(session)
    text = (
        f"{CATALOG} <b>Категории</b>\n"
        f"{'━' * 16}\n\n"
        f"Всего: <b>{len(categories)}</b>"
    )
    await call.message.edit_text(text, reply_markup=admin_categories_kb(categories), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "admin_add_category")
async def cb_add_category(call: CallbackQuery, state: FSMContext, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
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
    cat = await create_category(session, name)
    await log_action(session, user.id, "create_category", "category", cat.id)
    await state.clear()
    await message.answer(
        f"{OK} Категория <b>{cat.name}</b> создана!",
        parse_mode="HTML"
    )
