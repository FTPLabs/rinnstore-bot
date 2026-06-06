"""
Единый каталог: категории + подкатегории + товары.
Кнопка «📚 Каталог» → admin_catalog

Флоу добавления (минималистичный):
  ➕ Категорию   → название (1 шаг)
  ➕ Подкатегорию → выбор родителя → название (2 шага)
  ➕ Товар        → (выбор категории если из корня) → название → цена → тип (3–4 шага)
  📥 Импорт       → вставить текст в формате «Название | цена\nключ1\nключ2»
"""

import logging
from decimal import Decimal, InvalidOperation
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...models import User, Category, Product
from ...services.admin_service import (
    is_admin, get_root_categories, get_subcategories_admin, get_all_categories,
    create_category, create_product, add_product_keys,
    delete_product, delete_category, toggle_product, log_action,
)
from ...utils.helpers import parse_callback_int
from ...utils.emoji import OK, FAIL, ADD, KEY, STATS, plain

logger = logging.getLogger(__name__)
router = Router()

CANCEL_CB = "admin_catalog"


class CatalogState(StatesGroup):
    cat_name     = State()   # название новой категории
    subcat_name  = State()   # название новой подкатегории (parent уже в data)
    prod_name    = State()   # название товара (cat_id уже в data)
    prod_price   = State()   # цена товара
    prod_keys    = State()   # ключи после создания
    mass_import  = State()   # массовый импорт (cat_id в data)


# ─────────────────────────────────────────────────────────────────────
# ВСПОМОГАТЕЛЬНЫЕ КЛАВИАТУРЫ (локальные, чтобы не перегружать keyboards/admin.py)
# ─────────────────────────────────────────────────────────────────────

def _cancel_kb(back_cb: str = CANCEL_CB) -> object:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✕ Отмена", callback_data=back_cb))
    return b.as_markup()


def _skip_cancel_kb(skip_cb: str, back_cb: str = CANCEL_CB) -> object:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="⏭ Пропустить", callback_data=skip_cb),
        InlineKeyboardButton(text="✕ Отмена", callback_data=back_cb),
    )
    return b.as_markup()


def _catalog_root_kb(root_cats: list) -> object:
    b = InlineKeyboardBuilder()
    for cat in root_cats:
        icon = "✅" if cat.is_active else "🚫"
        b.row(InlineKeyboardButton(text=f"{icon} 📂 {cat.name}", callback_data=f"cat_view_{cat.id}"))
    b.row(
        InlineKeyboardButton(text="➕ Категорию", callback_data="cat_add_root"),
        InlineKeyboardButton(text="➕ Подкатегорию", callback_data="cat_add_sub_pick"),
        InlineKeyboardButton(text="➕ Товар", callback_data="cat_add_prod_pick"),
    )
    b.row(InlineKeyboardButton(text="◀️ Меню", callback_data="admin_main"))
    return b.as_markup()


def _cat_view_kb(cat_id: int, is_active: bool, subcats: list, products: list, parent_id) -> object:
    b = InlineKeyboardBuilder()
    for sc in subcats:
        icon = "✅" if sc.is_active else "🚫"
        b.row(InlineKeyboardButton(text=f"{icon} 📁 {sc.name}", callback_data=f"cat_view_{sc.id}"))
    for p in products:
        icon = "✅" if p.is_active else "🚫"
        b.row(InlineKeyboardButton(text=f"{icon} 📦 {p.name} — {p.price}₽", callback_data=f"admin_product_{p.id}"))
    b.row(
        InlineKeyboardButton(text="➕ Подкатегорию", callback_data=f"cat_add_sub_{cat_id}"),
        InlineKeyboardButton(text="➕ Товар", callback_data=f"cat_add_prod_{cat_id}"),
        InlineKeyboardButton(text="📥 Импорт", callback_data=f"cat_import_{cat_id}"),
    )
    toggle = "🚫 Скрыть" if is_active else "✅ Показать"
    b.row(
        InlineKeyboardButton(text=toggle, callback_data=f"admin_toggle_cat_{cat_id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"admin_delete_cat_{cat_id}"),
    )
    back_cb = f"cat_view_{parent_id}" if parent_id else "admin_catalog"
    b.row(InlineKeyboardButton(text="◀️ Назад", callback_data=back_cb))
    return b.as_markup()


def _pick_parent_kb(root_cats: list) -> object:
    """Выбор родительской категории для подкатегории."""
    b = InlineKeyboardBuilder()
    for cat in root_cats:
        b.row(InlineKeyboardButton(text=f"📂 {cat.name}", callback_data=f"cat_sub_parent_{cat.id}"))
    b.row(InlineKeyboardButton(text="✕ Отмена", callback_data=CANCEL_CB))
    return b.as_markup()


def _pick_cat_for_prod_kb(all_cats: list) -> object:
    """Плоский список всех категорий и подкатегорий для выбора при добавлении товара."""
    b = InlineKeyboardBuilder()
    for cat in all_cats:
        prefix = "  📁" if cat.parent_id else "📂"
        b.row(InlineKeyboardButton(text=f"{prefix} {cat.name}", callback_data=f"cat_prod_in_{cat.id}"))
    b.row(InlineKeyboardButton(text="✕ Отмена", callback_data=CANCEL_CB))
    return b.as_markup()


def _prod_type_kb(cat_id: int) -> object:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📦 Обычный", callback_data="cat_prod_type_normal"),
        InlineKeyboardButton(text="♾ Безлимитный", callback_data="cat_prod_type_unlimited"),
    )
    b.row(InlineKeyboardButton(text="✕ Отмена", callback_data=f"cat_view_{cat_id}"))
    return b.as_markup()


def _keys_kb(product_id: int, cat_id: int) -> object:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Готово (без ключей)", callback_data=f"cat_keys_done_{product_id}_{cat_id}"),
    )
    return b.as_markup()


# ─────────────────────────────────────────────────────────────────────
# КОРЕНЬ КАТАЛОГА
# ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_catalog")
async def cb_catalog(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()
    cats = await get_root_categories(session)
    count_line = f"Категорий: <b>{len(cats)}</b>" if cats else "Категорий пока нет — создайте первую ➕"
    await call.message.edit_text(
        f"📚 <b>Каталог</b>\n{count_line}",
        reply_markup=_catalog_root_kb(cats),
        parse_mode="HTML",
    )
    await call.answer()


# ─────────────────────────────────────────────────────────────────────
# ПРОСМОТР КАТЕГОРИИ / ПОДКАТЕГОРИИ
# ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^cat_view_\d+$"))
async def cb_cat_view(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()

    cat_id = parse_callback_int(call.data, 2)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)

    result = await session.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return await call.answer("Категория не найдена", show_alert=True)

    subcats  = await get_subcategories_admin(session, cat_id)
    prod_res = await session.execute(
        select(Product).where(Product.category_id == cat_id).order_by(Product.sort_order, Product.name)
    )
    products = prod_res.scalars().all()

    icon = "📁" if cat.parent_id else "📂"
    status = "✅" if cat.is_active else "🚫"
    parts = [f"{icon} <b>{cat.name}</b> {status}"]
    if cat.description:
        parts.append(cat.description)
    parts.append(f"Подкатегорий: {len(subcats)} · Товаров: {len(products)}")

    await call.message.edit_text(
        "\n".join(parts),
        reply_markup=_cat_view_kb(cat_id, cat.is_active, subcats, products, cat.parent_id),
        parse_mode="HTML",
    )
    await call.answer()


# ─────────────────────────────────────────────────────────────────────
# ➕ КАТЕГОРИЯ (корневая) — 1 шаг: только название
# ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cat_add_root")
async def cb_add_root_cat(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.update_data(cat_parent_id=None)
    await state.set_state(CatalogState.cat_name)
    await call.message.edit_text(
        "📂 <b>Новая категория</b>\n\nВведите название:",
        reply_markup=_cancel_kb(),
        parse_mode="HTML",
    )
    await call.answer()


@router.message(CatalogState.cat_name)
async def process_cat_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if not (2 <= len(name) <= 255):
        return await message.answer(f"{FAIL} Название: 2–255 символов.", reply_markup=_cancel_kb())
    data = await state.get_data()
    cat = await create_category(session, name, parent_id=data.get("cat_parent_id"))
    await log_action(session, user.id, "create_category", "category", cat.id)
    await state.clear()
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📂 Открыть", callback_data=f"cat_view_{cat.id}"))
    b.row(InlineKeyboardButton(text="◀️ К каталогу", callback_data="admin_catalog"))
    await message.answer(f"✅ Категория <b>{cat.name}</b> создана.", reply_markup=b.as_markup(), parse_mode="HTML")


# ─────────────────────────────────────────────────────────────────────
# ➕ ПОДКАТЕГОРИЯ — 2 шага: выбор родителя → название
# ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cat_add_sub_pick")
async def cb_add_sub_pick(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    """Нажата ➕ Подкатегорию из корня каталога — показываем выбор родителя."""
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    root_cats = await get_root_categories(session)
    if not root_cats:
        return await call.answer("Сначала создайте главную категорию.", show_alert=True)
    await call.message.edit_text(
        "📁 <b>Новая подкатегория</b>\n\nВыберите родительскую категорию:",
        reply_markup=_pick_parent_kb(root_cats),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^cat_add_sub_\d+$"))
async def cb_add_sub_in_cat(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    """Нажата ➕ Подкатегорию внутри категории — родитель уже известен."""
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    parent_id = parse_callback_int(call.data, 3)
    if parent_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Category).where(Category.id == parent_id))
    parent = result.scalar_one_or_none()
    if not parent:
        return await call.answer("Категория не найдена", show_alert=True)
    await state.update_data(cat_parent_id=parent_id, cat_parent_name=parent.name)
    await state.set_state(CatalogState.subcat_name)
    await call.message.edit_text(
        f"📁 <b>Подкатегория в «{parent.name}»</b>\n\nВведите название:",
        reply_markup=_cancel_kb(f"cat_view_{parent_id}"),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^cat_sub_parent_\d+$"))
async def cb_sub_parent_chosen(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    """Выбрана родительская категория из пикера."""
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    parent_id = parse_callback_int(call.data, 3)
    if parent_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Category).where(Category.id == parent_id))
    parent = result.scalar_one_or_none()
    if not parent:
        return await call.answer("Категория не найдена", show_alert=True)
    await state.update_data(cat_parent_id=parent_id, cat_parent_name=parent.name)
    await state.set_state(CatalogState.subcat_name)
    await call.message.edit_text(
        f"📁 <b>Подкатегория в «{parent.name}»</b>\n\nВведите название:",
        reply_markup=_cancel_kb(f"cat_view_{parent_id}"),
        parse_mode="HTML",
    )
    await call.answer()


@router.message(CatalogState.subcat_name)
async def process_subcat_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if not (2 <= len(name) <= 255):
        return await message.answer(f"{FAIL} Название: 2–255 символов.", reply_markup=_cancel_kb())
    data = await state.get_data()
    parent_id = data.get("cat_parent_id")
    parent_name = data.get("cat_parent_name", "")
    cat = await create_category(session, name, parent_id=parent_id)
    await log_action(session, user.id, "create_subcategory", "category", cat.id, {"parent_id": parent_id})
    await state.clear()
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="📁 Открыть", callback_data=f"cat_view_{cat.id}"),
        InlineKeyboardButton(text="◀️ В категорию", callback_data=f"cat_view_{parent_id}"),
    )
    await message.answer(
        f"✅ Подкатегория <b>{cat.name}</b> создана в «{parent_name}».",
        reply_markup=b.as_markup(), parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────
# ➕ ТОВАР — умный флоу
# ─────────────────────────────────────────────────────────────────────

def _sorted_cats_for_picker(all_cats: list) -> list:
    """Сортировка: сначала корневые, затем их подкатегории — для пикера товара."""
    roots = [c for c in all_cats if not c.parent_id]
    ordered = []
    for root in roots:
        ordered.append(root)
        ordered.extend([c for c in all_cats if c.parent_id == root.id])
    return ordered


@router.callback_query(F.data == "cat_add_prod_pick")
async def cb_add_prod_pick(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    """➕ Товар из корня каталога — показываем выбор категории (плоский список)."""
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    all_cats = await get_all_categories(session)
    active_cats = [c for c in all_cats if c.is_active]
    if not active_cats:
        return await call.answer("Сначала создайте категорию.", show_alert=True)
    await call.message.edit_text(
        "📦 <b>Новый товар</b>\n\nВыберите категорию:",
        reply_markup=_pick_cat_for_prod_kb(_sorted_cats_for_picker(active_cats)),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^cat_prod_in_\d+$"))
async def cb_prod_cat_chosen(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    """Категория выбрана из пикера — идём к названию товара."""
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return await call.answer("Категория не найдена", show_alert=True)
    await state.update_data(prod_cat_id=cat_id, prod_cat_name=cat.name)
    await state.set_state(CatalogState.prod_name)
    await call.message.edit_text(
        f"📦 <b>Новый товар в «{cat.name}»</b>\n\nНазвание:",
        reply_markup=_cancel_kb(f"cat_view_{cat_id}"),
        parse_mode="HTML",
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^cat_add_prod_\d+$"))
async def cb_add_prod_in_cat(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    """➕ Товар внутри конкретной категории — категория уже известна."""
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 3)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return await call.answer("Категория не найдена", show_alert=True)
    await state.update_data(prod_cat_id=cat_id, prod_cat_name=cat.name)
    await state.set_state(CatalogState.prod_name)
    await call.message.edit_text(
        f"📦 <b>Новый товар в «{cat.name}»</b>\n\nНазвание:",
        reply_markup=_cancel_kb(f"cat_view_{cat_id}"),
        parse_mode="HTML",
    )
    await call.answer()


@router.message(CatalogState.prod_name)
async def process_prod_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if not (2 <= len(name) <= 255):
        return await message.answer(f"{FAIL} Название: 2–255 символов.", reply_markup=_cancel_kb())
    await state.update_data(prod_name_val=name)
    await state.set_state(CatalogState.prod_price)
    await message.answer("💰 Цена (₽):", reply_markup=_cancel_kb())


@router.message(CatalogState.prod_price)
async def process_prod_price(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    try:
        price = Decimal(message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        return await message.answer(f"{FAIL} Введите число > 0:", reply_markup=_cancel_kb())
    await state.update_data(prod_price_val=str(price))
    data = await state.get_data()
    cat_id = data.get("prod_cat_id", 0)
    await message.answer(
        "📦 <b>Тип товара:</b>\n"
        "• <b>Обычный</b> — каждый ключ = один покупатель\n"
        "• <b>Безлимитный</b> — один ключ для всех",
        reply_markup=_prod_type_kb(cat_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.in_({"cat_prod_type_normal", "cat_prod_type_unlimited"}))
async def process_prod_type(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    data = await state.get_data()
    if "prod_cat_id" not in data:
        return await call.answer("Сессия устарела, начните заново.", show_alert=True)
    is_unlimited = (call.data == "cat_prod_type_unlimited")
    product = await create_product(
        session,
        category_id=data["prod_cat_id"],
        name=data["prod_name_val"],
        description="",
        price=Decimal(data["prod_price_val"]),
        is_unlimited=is_unlimited,
    )
    await log_action(session, user.id, "create_product", "product", product.id)
    await state.update_data(new_prod_id=product.id)
    await state.set_state(CatalogState.prod_keys)

    kind = "♾ безлимитный" if is_unlimited else "📦 обычный"
    cat_id = data["prod_cat_id"]
    await call.message.edit_text(
        f"✅ <b>{product.name}</b> создан ({kind}) — {product.price} ₽\n\n"
        f"Отправьте ключи (каждый с новой строки) или нажмите <b>Готово</b>:",
        reply_markup=_keys_kb(product.id, cat_id),
        parse_mode="HTML",
    )
    await call.answer()


@router.message(CatalogState.prod_keys)
async def process_prod_keys(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    data = await state.get_data()
    product_id = data.get("new_prod_id")
    cat_id = data.get("prod_cat_id", 0)
    if not product_id:
        await state.clear()
        return await message.answer(f"{FAIL} Сессия устарела, начните заново.")

    keys = [k.strip() for k in message.text.split("\n") if k.strip()]
    if not keys:
        return await message.answer(f"{FAIL} Нет ключей. Введите или нажмите Готово.")

    count = await add_product_keys(session, product_id, keys)
    await log_action(session, user.id, "add_keys", "product", product_id, {"count": count})
    await state.clear()

    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Ещё ключи", callback_data=f"admin_add_keys_{product_id}"),
        InlineKeyboardButton(text="◀️ К категории", callback_data=f"cat_view_{cat_id}"),
    )
    await message.answer(
        f"✅ Добавлено <b>{count}</b> ключей.",
        reply_markup=b.as_markup(), parse_mode="HTML",
    )


@router.callback_query(F.data.regexp(r"^cat_keys_done_\d+_\d+$"))
async def cb_keys_done(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()
    parts = call.data.split("_")
    product_id = int(parts[3])
    cat_id = int(parts[4])
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="➕ Добавить ключи", callback_data=f"admin_add_keys_{product_id}"),
        InlineKeyboardButton(text="◀️ К категории", callback_data=f"cat_view_{cat_id}"),
    )
    await call.message.edit_text(
        "✅ Товар сохранён. Ключи можно добавить в любой момент.",
        reply_markup=b.as_markup(),
    )
    await call.answer()


# ─────────────────────────────────────────────────────────────────────
# 📥 МАССОВЫЙ ИМПОРТ
# ─────────────────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^cat_import_\d+$"))
async def cb_cat_import(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    cat_id = parse_callback_int(call.data, 2)
    if cat_id is None:
        return await call.answer("Ошибка данных", show_alert=True)
    result = await session.execute(select(Category).where(Category.id == cat_id))
    cat = result.scalar_one_or_none()
    if not cat:
        return await call.answer("Категория не найдена", show_alert=True)

    await state.update_data(import_cat_id=cat_id, import_cat_name=cat.name)
    await state.set_state(CatalogState.mass_import)
    await call.message.edit_text(
        f"📥 <b>Импорт в «{cat.name}»</b>\n\n"
        "Формат — блоки через пустую строку:\n"
        "<code>Название | цена</code>\n"
        "<code>ключ1</code>\n"
        "<code>ключ2</code>\n\n"
        "<code>Другой товар [∞] | 500</code>\n"
        "<code>общий_ключ</code>\n\n"
        "<b>[∞]</b> = безлимитный товар. Ключи необязательны.",
        reply_markup=_cancel_kb(f"cat_view_{cat_id}"),
        parse_mode="HTML",
    )
    await call.answer()


@router.message(CatalogState.mass_import)
async def process_mass_import(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    data = await state.get_data()
    cat_id = data.get("import_cat_id")
    cat_name = data.get("import_cat_name", "")
    await state.clear()

    text = (message.text or "").strip()
    if not text:
        return await message.answer(f"{FAIL} Пустое сообщение.")

    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    created = 0
    total_keys = 0
    errors = []

    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue
        parts = [p.strip() for p in lines[0].split("|")]
        if len(parts) < 2:
            errors.append(f"«{lines[0][:35]}» — нет цены")
            continue
        raw_name = parts[0]
        is_unlimited = "[∞]" in raw_name or "[inf]" in raw_name.lower()
        name = raw_name.replace("[∞]", "").replace("[inf]", "").strip()
        try:
            price = Decimal(parts[1].replace(",", "."))
            if price <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            errors.append(f"«{name[:30]}» — некорректная цена")
            continue
        desc = parts[2].strip() if len(parts) >= 3 else ""
        try:
            product = await create_product(
                session, category_id=cat_id, name=name,
                description=desc, price=price, is_unlimited=is_unlimited,
            )
        except Exception as e:
            errors.append(f"«{name[:30]}» — ошибка: {e}")
            continue
        keys = lines[1:]
        if keys:
            total_keys += await add_product_keys(session, product.id, keys)
        created += 1
        await log_action(session, user.id, "mass_import", "product", product.id,
                         {"keys": len(keys), "unlimited": is_unlimited})

    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="◀️ К категории", callback_data=f"cat_view_{cat_id}"))
    err_text = ""
    if errors:
        err_text = "\n⚠️ " + "\n⚠️ ".join(errors[:5])
        if len(errors) > 5:
            err_text += f"\n...и ещё {len(errors)-5}"
    await message.answer(
        f"✅ <b>Импорт в «{cat_name}»</b>\n"
        f"Создано: <b>{created}</b> товаров · <b>{total_keys}</b> ключей"
        + err_text,
        reply_markup=b.as_markup(), parse_mode="HTML",
    )


# ─────────────────────────────────────────────────────────────────────
# TOGGLE / DELETE — делегируется в products.py (admin_toggle_cat_ / admin_delete_cat_)
# ─────────────────────────────────────────────────────────────────────
