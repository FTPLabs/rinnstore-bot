from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import User
from ..keyboards.user import cart_kb, payment_method_kb, back_to_menu_kb
from ..services.catalog_service import get_product, get_stock_count
from ..services.cart_service import CartService
from ..services.order_service import create_order
from ..utils.helpers import parse_callback_int

router = Router()


def format_cart(cart: CartService) -> str:
    if cart.is_empty():
        return "🛒 <b>Корзина пуста</b>"
    lines = ["<b>Корзина</b>\n"]
    for item in cart.items():
        lines.append(f"{item['name']} × {item['qty']} — <b>{item['price'] * item['qty']:.0f} ₽</b>")
    lines.append(f"\nИтого: <b>{cart.total():.0f} ₽</b>")
    return "\n".join(lines)


@router.callback_query(F.data.startswith("add_cart_"))
async def cb_add_to_cart(call: CallbackQuery, session: AsyncSession, state: FSMContext):
    product_id = parse_callback_int(call.data, 2)
    if product_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    product = await get_product(session, product_id)
    if not product or not product.is_active:
        await call.answer("Товар недоступен", show_alert=True)
        return

    stock = await get_stock_count(session, product_id)
    if stock == 0:
        await call.answer("Нет в наличии", show_alert=True)
        return

    data = await state.get_data()
    cart = CartService(data)
    current_qty = sum(item["qty"] for item in cart.items() if item["product_id"] == product_id)
    if current_qty >= stock:
        await call.answer(f"Доступно: {stock} шт.", show_alert=True)
        return

    cart.add(product_id, float(product.price), product.name)
    await state.set_data(data)
    await call.answer(f"✅ {product.name} добавлен")


@router.callback_query(F.data.startswith("rem_cart_"))
async def cb_remove_from_cart(call: CallbackQuery, state: FSMContext):
    product_id = parse_callback_int(call.data, 2)
    if product_id is None:
        await call.answer("Ошибка данных", show_alert=True)
        return

    data = await state.get_data()
    cart = CartService(data)
    cart.remove(product_id)
    await state.set_data(data)
    await call.answer("Убрано")
    await call.message.edit_text(format_cart(cart), reply_markup=cart_kb(not cart.is_empty()))


@router.callback_query(F.data == "cart")
async def cb_cart(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = CartService(data)
    await call.message.edit_text(format_cart(cart), reply_markup=cart_kb(not cart.is_empty()))
    await call.answer()


@router.callback_query(F.data == "clear_cart")
async def cb_clear_cart(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = CartService(data)
    cart.clear()
    await state.set_data(data)
    await call.message.edit_text("Корзина очищена.", reply_markup=back_to_menu_kb())
    await call.answer()


@router.callback_query(F.data == "checkout")
async def cb_checkout(call: CallbackQuery, session: AsyncSession, state: FSMContext, user: User):
    data = await state.get_data()
    cart = CartService(data)

    if cart.is_empty():
        await call.answer("Корзина пуста", show_alert=True)
        return

    for item in cart.items():
        stock = await get_stock_count(session, item["product_id"])
        if stock < item["qty"]:
            await call.answer(f"«{item['name']}» — только {stock} шт.", show_alert=True)
            return

    promo_code = data.get("promo_code")
    order = await create_order(session, user.id, cart.items(), promo_code)
    cart.clear()
    data.pop("promo_code", None)
    await state.set_data(data)

    discount_text = (
        f"\nСкидка: <b>{order.discount_amount} ₽</b>"
        if order.discount_amount and float(order.discount_amount) > 0
        else ""
    )
    text = (
        f"<b>Заказ #{order.id}</b>\n\n"
        f"Сумма: <b>{order.total_amount} ₽</b>{discount_text}\n\n"
        f"Выберите способ оплаты:"
    )
    await call.message.edit_text(text, reply_markup=payment_method_kb(order.id))
    await call.answer()
