"""
Единый обработчик каталога: категории + подкатегории + товары в одном месте.
Вход: кнопка «📚 Каталог» в админ-меню → callback_data = "admin_catalog".

Поддерживаемые операции:
  - Просмотр дерева категорий (cat_view_{id})
  - Добавить корневую категорию (cat_add_root)
  - Добавить подкатегорию (cat_add_sub_{parent_id})
  - Добавить товар в категорию (cat_add_product_{cat_id})
  - Массовый импорт товаров (cat_import_{cat_id})

Формат массового импорта (каждый блок = один товар):
  Название товара | цена | описание (описание можно пропустить)
  ключ1
  ключ2
  ...
  <пустая строка>
  Следующий товар | цена
  ключ3
  ...

Для безлимитного товара — добавьте [∞] в конец названия:
  Безлимит-ключ [∞] | 500
  общий_ключ_для_всех
"""

import logging
from decimal import Decimal, InvalidOperation
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...models import User, Category, Product, ProductItem
from ...keyboards.admin import (
    admin_catalog_root_kb, admin_catalog_cat_kb, cancel_kb,
    catalog_skip_kb, catalog_type_kb, admin_confirm_kb,
    admin_catalog_product_detail_kb,
)
from ...services.admin_service import (
    is_admin, get_root_categories, get_subcategories_admin,
    create_category, create_product, add_product_keys,
    get_stock_for_product, toggle_product, delete_product,
    delete_category, log_action,
)
from ...utils.helpers import parse_callback_int
from ...utils.emoji import OK, FAIL, ADD, STATS, KEY, plain

logger = logging.getLogger(__name__)
router = Router()


class CatalogState(StatesGroup):
    # Категория
    cat_name = State()
    cat_desc = State()
    # Подкатегория
    subcat_name = State()
    subcat_desc = State()
    # Товар (пошаговый)
    prod_name = State()
    prod_desc = State()
    prod_price = State()
    prod_type = State()
    prod_keys = State()
    # Массовый импорт
    mass_import = State()


# ─── КОРЕНЬ КАТАЛОГА ─────────────────────────────────────────────────

@router.callback_query(F.data == "admin_catalog")
async def cb_admin_catalog(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()
    cats = await get_root_categories(session)
    text = (
        "📚 <b>Каталог</b>\n"
        f"{'━' * 16}\n\n"
        f"Категорий: <b>{len(cats)}</b>\n\n"
        "Нажмите на категорию для управления.\n"
        "Используйте <b>➕ Товар</b> внутри категории для добавления.\n"
        "Используйте <b>📥 Импорт</b> для массового добавления товаров."
    )
    await call.message.edit_text(text, reply_markup=admin_catalog_root_kb(cats), parse_mode="HTML")
    await call.answer()


# ─── ПРОСМОТР КАТЕГОРИИ (единый хэндлер для корневых и подкатегорий) ─

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

    subcats = await get_subcategories_admin(session, cat_id)
    prod_result = await session.execute(
        select(Product).where(Product.category_id == cat_id).order_by(Product.sort_order, Product.name)
    )
    products = prod_result.scalars().all()

    status = "✅ Активна" if cat.is_active else "🚫 Скрыта"
    is_sub = cat.parent_id is not None
    icon = "📁" if is_sub else "📂"

    text = (
        f"{icon} <b>{cat.name}</b>\n"
        f"{'━' * 16}\n"
        f"Статус: {status}\n"
    )
    if cat.description:
        text += f"Описание: {cat.description}\n"
    text += f"\n📁 Подкатегорий: <b>{len(subcats)}</b>\n📦 Товаров: <b>{len(products)}</b>"

    await call.message.edit_text(
        text,
        reply_markup=admin_catalog_cat_kb(cat_id, cat.is_active, subcats, products, parent_id=cat.parent_id),
        parse_mode="HTML"
    )
    await call.answer()


# ─── ДОБАВИТЬ КОРНЕВУЮ КАТЕГОРИЮ ─────────────────────────────────────

@router.callback_query(F.data == "cat_add_root")
async def cb_cat_add_root(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.update_data(cat_parent_id=None)
    await state.set_state(CatalogState.cat_name)
    await call.message.edit_text(
        f"{ADD} <b>Новая категория</b>\n\nВведите название:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


# ─── ДОБАВИТЬ ПОДКАТЕГОРИЮ ────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^cat_add_sub_\d+$"))
async def cb_cat_add_sub(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
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
        f"{ADD} <b>Подкатегория в «{parent.name}»</b>\n\nВведите название:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(CatalogState.subcat_name)
async def process_subcat_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if len(name) < 2 or len(name) > 255:
        await message.answer(f"{FAIL} Название: 2–255 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(cat_name_val=name)
    await state.set_state(CatalogState.subcat_desc)
    await message.answer(
        "📝 Введите описание (или пропустите):",
        reply_markup=catalog_skip_kb("cat_subcat_desc_skip")
    )


@router.callback_query(F.data == "cat_subcat_desc_skip")
async def cb_subcat_desc_skip(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await _finish_create_cat(call.message, session, user, state, desc="", is_edit=True)
    await call.answer()


@router.message(CatalogState.subcat_desc)
async def process_subcat_desc(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await _finish_create_cat(message, session, user, state, desc=desc, is_edit=False)


# ─── ОБРАБОТКА НАЗВАНИЯ КАТЕГОРИИ ────────────────────────────────────

@router.message(CatalogState.cat_name)
async def process_cat_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if len(name) < 2 or len(name) > 255:
        await message.answer(f"{FAIL} Название: 2–255 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(cat_name_val=name)
    await state.set_state(CatalogState.cat_desc)
    await message.answer(
        "📝 Введите описание (или пропустите):",
        reply_markup=catalog_skip_kb("cat_root_desc_skip")
    )


@router.callback_query(F.data == "cat_root_desc_skip")
async def cb_cat_desc_skip(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await _finish_create_cat(call.message, session, user, state, desc="", is_edit=True)
    await call.answer()


@router.message(CatalogState.cat_desc)
async def process_cat_desc(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await _finish_create_cat(message, session, user, state, desc=desc, is_edit=False)


async def _finish_create_cat(msg_or_call, session, user, state, desc: str, is_edit: bool):
    data = await state.get_data()
    name = data.get("cat_name_val", "")
    parent_id = data.get("cat_parent_id")
    parent_name = data.get("cat_parent_name", "")

    cat = await create_category(session, name, description=desc, parent_id=parent_id)
    await log_action(session, user.id, "create_category", "category", cat.id, {"parent_id": parent_id})
    await state.clear()

    kind = f"подкатегория в «{parent_name}»" if parent_id else "категория"
    text = f"{plain(OK)} Создана {kind}: <b>{cat.name}</b>"
    if is_edit:
        await msg_or_call.edit_text(text, parse_mode="HTML")
    else:
        await msg_or_call.answer(text, parse_mode="HTML")


# ─── ДОБАВИТЬ ТОВАР В КАТЕГОРИЮ ──────────────────────────────────────

@router.callback_query(F.data.regexp(r"^cat_add_product_\d+$"))
async def cb_cat_add_product(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
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
        f"{ADD} <b>Новый товар в «{cat.name}»</b>\n\nВведите название товара:",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
    )
    await call.answer()


@router.message(CatalogState.prod_name)
async def process_prod_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    name = message.text.strip()
    if len(name) < 2 or len(name) > 255:
        await message.answer(f"{FAIL} Название: 2–255 символов.", reply_markup=cancel_kb())
        return
    await state.update_data(prod_name_val=name)
    await state.set_state(CatalogState.prod_desc)
    await message.answer(
        "📝 Введите описание (или пропустите):",
        reply_markup=catalog_skip_kb("cat_prod_desc_skip")
    )


@router.callback_query(F.data == "cat_prod_desc_skip")
async def cb_prod_desc_skip(call: CallbackQuery, state: FSMContext):
    await state.update_data(prod_desc_val="")
    await state.set_state(CatalogState.prod_price)
    await call.message.edit_text("💰 Введите цену товара (в рублях):", reply_markup=cancel_kb())
    await call.answer()


@router.message(CatalogState.prod_desc)
async def process_prod_desc(message: Message, state: FSMContext):
    desc = "" if message.text.strip() == "-" else message.text.strip()
    await state.update_data(prod_desc_val=desc)
    await state.set_state(CatalogState.prod_price)
    await message.answer("💰 Введите цену товара (в рублях):", reply_markup=cancel_kb())


@router.message(CatalogState.prod_price)
async def process_prod_price(message: Message, state: FSMContext):
    try:
        price = Decimal(message.text.strip().replace(",", "."))
        if price <= 0:
            raise ValueError()
    except (InvalidOperation, ValueError):
        await message.answer(f"{FAIL} Введите корректную цену (число > 0):", reply_markup=cancel_kb())
        return
    await state.update_data(prod_price_val=str(price))
    await state.set_state(CatalogState.prod_type)
    await message.answer(
        "📦 <b>Тип товара:</b>\n\n"
        "• <b>Обычный</b> — каждый ключ выдаётся одному покупателю (конечный запас)\n"
        "• <b>Безлимитный</b> — один ключ выдаётся всем (например, общий доступ)",
        reply_markup=catalog_type_kb(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.in_({"cat_prod_type_normal", "cat_prod_type_unlimited"}))
async def process_prod_type(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    is_unlimited = call.data == "cat_prod_type_unlimited"
    data = await state.get_data()

    product = await create_product(
        session,
        category_id=data["prod_cat_id"],
        name=data["prod_name_val"],
        description=data.get("prod_desc_val", ""),
        price=Decimal(data["prod_price_val"]),
        is_unlimited=is_unlimited,
    )
    await log_action(session, user.id, "create_product", "product", product.id)
    await state.update_data(new_prod_id=product.id)
    await state.set_state(CatalogState.prod_keys)

    kind = "♾ безлимитный" if is_unlimited else "📦 обычный"
    hint = (
        "Введите <b>один или несколько ключей</b>, каждый с новой строки.\n\n"
        "Или нажмите <b>⏭ Пропустить</b>, чтобы добавить ключи позже."
    )
    await call.message.edit_text(
        f"{plain(OK)} <b>Товар создан!</b> ({kind})\n"
        f"<b>{product.name}</b> — {product.price} ₽\n\n"
        f"{hint}",
        reply_markup=catalog_skip_kb(f"cat_prod_keys_skip_{product.id}", cancel_cb=f"cat_view_{data['prod_cat_id']}"),
        parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data.regexp(r"^cat_prod_keys_skip_\d+$"))
async def cb_prod_keys_skip(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("🚫 Нет доступа", show_alert=True)
    await state.clear()
    data_parts = call.data.split("_")
    product_id = int(data_parts[-1])
    result = await session.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    cat_id = product.category_id if product else 0
    await call.message.edit_text(
        f"{plain(OK)} Товар сохранён. Ключи можно добавить позже из карточки товара.",
        parse_mode="HTML"
    )
    await call.answer("Товар создан без ключей")


@router.message(CatalogState.prod_keys)
async def process_prod_keys(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    data = await state.get_data()
    product_id = data.get("new_prod_id")
    if not product_id:
        await message.answer(f"{FAIL} Ошибка состояния. Начните заново.")
        await state.clear()
        return

    keys = [k.strip() for k in message.text.split("\n") if k.strip()]
    if not keys:
        await message.answer(f"{FAIL} Нет ключей. Введите хотя бы один или нажмите Пропустить.")
        return

    count = await add_product_keys(session, product_id, keys)
    await log_action(session, user.id, "add_keys", "product", product_id, {"count": count})
    await state.clear()
    await message.answer(
        f"{plain(OK)} Добавлено <b>{count}</b> ключей к товару.",
        parse_mode="HTML"
    )


# ─── МАССОВЫЙ ИМПОРТ ─────────────────────────────────────────────────

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
        f"📥 <b>Массовый импорт в «{cat.name}»</b>\n"
        f"{'━' * 16}\n\n"
        "Отправьте текст в формате:\n\n"
        "<code>Название товара | цена | описание</code>\n"
        "<code>ключ1</code>\n"
        "<code>ключ2</code>\n"
        "<code>(пустая строка)</code>\n"
        "<code>Другой товар | 500</code>\n"
        "<code>ключ3</code>\n\n"
        "• Описание — необязательно\n"
        "• Добавьте <b>[∞]</b> в название для безлимитного товара\n"
        "• Ключи можно не указывать (добавите потом)\n\n"
        "Пример:\n"
        "<code>Steam ключ | 299 | Игра\nABCD-EFGH-1234\nXYZW-QRST-5678</code>",
        reply_markup=cancel_kb(),
        parse_mode="HTML"
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

    text = message.text or ""
    if not text.strip():
        await message.answer(f"{FAIL} Пустой текст.")
        return

    # Парсим блоки (разделитель — пустая строка)
    blocks = [b.strip() for b in text.strip().split("\n\n") if b.strip()]
    if not blocks:
        await message.answer(f"{FAIL} Не удалось распознать формат.")
        return

    created_products = 0
    total_keys = 0
    errors = []

    for block in blocks:
        lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
        if not lines:
            continue

        header = lines[0]
        parts = [p.strip() for p in header.split("|")]
        if len(parts) < 2:
            errors.append(f"Строка «{header[:40]}» — нет цены")
            continue

        raw_name = parts[0].strip()
        is_unlimited = "[∞]" in raw_name or "[inf]" in raw_name.lower()
        name = raw_name.replace("[∞]", "").replace("[inf]", "").strip()

        try:
            price = Decimal(parts[1].strip().replace(",", "."))
            if price <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            errors.append(f"«{name[:30]}» — некорректная цена «{parts[1]}»")
            continue

        description = parts[2].strip() if len(parts) >= 3 else ""

        # Создаём товар
        try:
            product = await create_product(
                session,
                category_id=cat_id,
                name=name,
                description=description,
                price=price,
                is_unlimited=is_unlimited,
            )
        except Exception as e:
            errors.append(f"«{name[:30]}» — ошибка создания: {e}")
            continue

        # Ключи — все строки кроме первой
        keys = lines[1:]
        if keys:
            count = await add_product_keys(session, product.id, keys)
            total_keys += count

        created_products += 1
        await log_action(session, user.id, "mass_import_product", "product", product.id,
                         {"keys": len(keys), "unlimited": is_unlimited})

    result_lines = [
        f"{plain(OK)} <b>Импорт завершён</b>",
        f"{'━' * 16}",
        f"📦 Создано товаров: <b>{created_products}</b>",
        f"🔑 Добавлено ключей: <b>{total_keys}</b>",
    ]
    if errors:
        result_lines.append(f"\n⚠️ Ошибок: <b>{len(errors)}</b>")
        for err in errors[:5]:
            result_lines.append(f"  • {err}")
        if len(errors) > 5:
            result_lines.append(f"  ... и ещё {len(errors) - 5}")

    await message.answer("\n".join(result_lines), parse_mode="HTML")


# ─── TOGGLE / DELETE (делегируем к admin_toggle_cat_ / admin_delete_cat_) ──
# Эти хэндлеры уже есть в products.py, здесь дублировать не нужно.
# cat_view callback обновит страницу автоматически после действия.
