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
from ..utils.emoji import (
    CATALOG, STAR, KEY, OK, FAIL, BACK, BAG, TAG, plain
)

router = Router()


@router.callback_query(F.data == "catalog")
async def cb_catalog(call: CallbackQuery, session: AsyncSession):
    categories = await get_active_categories(session)
    if not categories:
        await call.message.edit_text(
            f"{FAIL} <b>Каталог пуст</b>\n\nЗаходите позже — скоро добавим новые товары!",
            reply_markup=back_to_menu_kb(),
            parse_mode="HTML",
        )
        await call.answer()
        return

    text = (
        f"{CATALOG} <b>Каталог товаров</b>\n"
        f"{'━' * 16}\n\n"
        f"Выберите категорию:"
    )
    await call.message.edit_text(
        text,
        reply_markup=catalog_kb(categories),
        parse_mode="HTML",
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
        builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="catalog"))
        await call.message.edit_text(
            f"{STAR} <b>{category.name}</b>\n\n{FAIL} В этой категории пока нет товаров.",
            reply_markup=builder.as_markup(),
            parse_mode="HTML",
        )
        await call.answer()
        return

    lines = [f"{STAR} <b>{category.name}</b>", f"{'━' * 16}", ""]
    builder = InlineKeyboardBuilder()

    for p in products:
        stock = await get_stock_count(session, p.id)
        stock_icon = OK if stock > 0 else FAIL
        stock_text = f"{stock} шт." if stock > 0 else "нет"
        lines.append(f"{TAG} <b>{p.name}</b> — {p.price} руб. | {stock_icon} {stock_text}")

        status_prefix = "" if stock > 0 else f"{plain(FAIL)} "
        builder.row(InlineKeyboardButton(
            text=f"{status_prefix}{p.name} — {p.price} руб.",
            callback_data=f"product_{p.id}"
        ))

    builder.row(InlineKeyboardButton(text=f"{plain(BACK)} Назад", callback_data="catalog"))
    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="HTML",
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
    stock_text = f"{OK} В наличии: <b>{stock} шт.</b>" if stock > 0 else f"{FAIL} <b>Нет в наличии</b>"

    text = (
        f"{BAG} <b>{product.name}</b>\n"
        f"{'━' * 16}\n\n"
        f"{product.description or 'Описание отсутствует'}\n\n"
        f"{'━' * 16}\n"
        f"💰 Цена: <b>{product.price} руб.</b>\n"
        f"{stock_text}"
    )

    await call.message.edit_text(
        text,
        reply_markup=product_kb(product_id, stock),
        parse_mode="HTML",
    )
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
    await call.answer("❌ Товар закончился. Попробуйте позже.", show_alert=True)
