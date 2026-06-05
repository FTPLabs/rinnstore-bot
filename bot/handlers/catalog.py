from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from ..keyboards.user import catalog_kb, product_kb, back_to_menu_kb
from ..services.catalog_service import (
    get_active_categories, get_category,
    get_products_in_category, get_product,
    get_stock_count, get_product_category_id
)
from ..utils.emoji import plain, BACK, OK, FAIL, STAR

router = Router()


@router.callback_query(F.data == "catalog")
async def cb_catalog(call: CallbackQuery, session: AsyncSession):
    categories = await get_active_categories(session)
    if not categories:
        await call.message.edit_text(
            "Каталог пуст. Загляните позже.",
            reply_markup=back_to_menu_kb(),
        )
        await call.answer()
        return

    await call.message.edit_text(
        "<b>Каталог</b>\n\nВыберите категорию:",
        reply_markup=catalog_kb(categories),
    )
    await call.answer()


@router.callback_query(F.data.startswith("cat_") & ~F.data.startswith("cat_back_"))
async def cb_category(call: CallbackQuery, session: AsyncSession):
    cat_id = int(call.data.split("_")[1])
    category = await get_category(session, cat_id)
    if not category:
        await call.answer("Категория не найдена", show_alert=True)
        return

    products = await get_products_in_category(session, cat_id)
    if not products:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="catalog"))
        await call.message.edit_text(
            f"<b>{category.name}</b>\n\nТоваров пока нет.",
            reply_markup=builder.as_markup(),
        )
        await call.answer()
        return

    builder = InlineKeyboardBuilder()
    for p in products:
        stock = await get_stock_count(session, p.id)
        prefix = "" if stock > 0 else "✕ "
        builder.row(InlineKeyboardButton(
            text=f"{prefix}{p.name} — {p.price} ₽",
            callback_data=f"product_{p.id}"
        ))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="catalog"))

    await call.message.edit_text(
        f"<b>{category.name}</b>",
        reply_markup=builder.as_markup(),
    )
    await call.answer()


@router.callback_query(F.data.startswith("product_"))
async def cb_product(call: CallbackQuery, session: AsyncSession):
    product_id = int(call.data.split("_")[1])
    product = await get_product(session, product_id)
    if not product:
        await call.answer("Товар не найден", show_alert=True)
        return

    stock = await get_stock_count(session, product_id)
    stock_line = f"В наличии: <b>{stock} шт.</b>" if stock > 0 else "<b>Нет в наличии</b>"

    desc = f"\n{product.description}\n" if product.description else "\n"
    text = (
        f"<b>{product.name}</b>{desc}\n"
        f"Цена: <b>{product.price} ₽</b>\n"
        f"{stock_line}"
    )
    await call.message.edit_text(text, reply_markup=product_kb(product_id, stock))
    await call.answer()


@router.callback_query(F.data.startswith("cat_back_"))
async def cb_back_to_category(call: CallbackQuery, session: AsyncSession):
    product_id = int(call.data.split("_")[2])
    cat_id = await get_product_category_id(session, product_id)
    if cat_id:
        call.data = f"cat_{cat_id}"
        await cb_category(call, session)
    else:
        call.data = "catalog"
        await cb_catalog(call, session)


@router.callback_query(F.data == "no_stock")
async def cb_no_stock(call: CallbackQuery):
    await call.answer("Нет в наличии", show_alert=True)
