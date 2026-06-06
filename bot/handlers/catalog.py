from decimal import Decimal
  from datetime import datetime, timezone
  from aiogram import Router, F
  from aiogram.types import CallbackQuery
  from aiogram.utils.keyboard import InlineKeyboardBuilder
  from aiogram.types import InlineKeyboardButton
  from sqlalchemy.ext.asyncio import AsyncSession
  from ..keyboards.user import (
      catalog_kb, subcatalog_kb, products_kb,
      back_to_menu_kb, payment_method_kb
  )
  from ..services.catalog_service import (
      get_root_categories, get_subcategories, get_category,
      get_products_in_category, get_product,
      get_stock_count, get_product_category_id, UNLIMITED_STOCK
  )
  from ..services.order_service import create_order
  from ..models import User
  from ..utils.helpers import parse_callback_int

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
          d100 = Decimal("100")
          sale = product.price * (d100 - product.discount_percent) / d100
          price_line = (
              f"Цена: <s>{product.price} ₽</s> → <b>{sale:.2f} ₽</b>"
              f"  🏷 -{product.discount_percent}%"
          )
          unit_price = sale
      else:
          price_line = f"Цена: <b>{product.price} ₽</b>"
          unit_price = product.price

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

          buy_text = f"🛒 Купить {qty} шт." if qty > 1 else "🛒 Купить"
          builder.row(InlineKeyboardButton(
              text=buy_text,
              callback_data=f"buy_{product_id}_{qty}"
          ))

      builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data=f"cat_back_{product_id}"))
      return builder.as_markup()


  async def _show_product(call: CallbackQuery, session: AsyncSession, product_id: int, qty: int = 1):
      product = await get_product(session, product_id)
      if not product:
          await call.answer("Товар не найден", show_alert=True)
          return None, 0

      stock = await get_stock_count(session, product_id)
      max_qty = min(stock, MAX_QTY_BUTTONS) if stock < UNLIMITED_STOCK else MAX_QTY_BUTTONS
      if qty > max_qty:
          qty = 1

      text = _product_text(product, stock, qty)
      kb = _product_kb(product_id, stock, qty)
      try:
          await call.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
      except Exception:
          await call.message.answer(text, reply_markup=kb, parse_mode="HTML")
      return product, stock


  # === Noop — заглушка для неактивных кнопок ===
  @router.callback_query(F.data == "noop")
  async def cb_noop(call: CallbackQuery):
      await call.answer()


  # === Каталог — корневые категории ===
  @router.callback_query(F.data == "catalog")
  async def cb_catalog(call: CallbackQuery, session: AsyncSession, user: User):
      cats = await get_root_categories(session)
      if not cats:
          await call.message.edit_text("Каталог пуст.", reply_markup=back_to_menu_kb())
          await call.answer()
          return
      await call.message.edit_text(
          "<b>🛍 Каталог</b>\n\nВыберите категорию:",
          reply_markup=catalog_kb(cats),
          parse_mode="HTML"
      )
      await call.answer()


  # === Клик по категории (корневой) ===
  @router.callback_query(F.data.regexp(r"^cat_\d+$"))
  async def cb_cat(call: CallbackQuery, session: AsyncSession, user: User):
      cat_id = parse_callback_int(call.data, 1)
      if cat_id is None:
          await call.answer("Ошибка", show_alert=True)
          return

      category = await get_category(session, cat_id)
      if not category or not category.is_active:
          await call.answer("Категория не найдена", show_alert=True)
          return

      # Проверяем подкатегории
      subcats = await get_subcategories(session, cat_id)
      if subcats:
          await call.message.edit_text(
              f"<b>📂 {category.name}</b>\n\nВыберите подкатегорию:",
              reply_markup=subcatalog_kb(subcats, cat_id),
              parse_mode="HTML"
          )
          await call.answer()
          return

      # Нет подкатегорий — показываем товары напрямую
      product_list = await get_products_in_category(session, cat_id)
      if not product_list:
          await call.message.edit_text(
              f"<b>{category.name}</b>\n\nТоваров пока нет.",
              reply_markup=products_kb([], cat_id),
              parse_mode="HTML"
          )
          await call.answer()
          return

      await call.message.edit_text(
          f"<b>📂 {category.name}</b>\n\nВыберите товар:",
          reply_markup=products_kb(product_list, cat_id),
          parse_mode="HTML"
      )
      await call.answer()


  # === Клик по подкатегории ===
  @router.callback_query(F.data.regexp(r"^subcat_\d+$"))
  async def cb_subcat(call: CallbackQuery, session: AsyncSession, user: User):
      cat_id = parse_callback_int(call.data, 1)
      if cat_id is None:
          await call.answer("Ошибка", show_alert=True)
          return

      category = await get_category(session, cat_id)
      if not category or not category.is_active:
          await call.answer("Категория не найдена", show_alert=True)
          return

      product_list = await get_products_in_category(session, cat_id)
      parent_cat_id = category.parent_id

      await call.message.edit_text(
          f"<b>📁 {category.name}</b>\n\nВыберите товар:",
          reply_markup=products_kb(product_list, cat_id, parent_cat_id=parent_cat_id),
          parse_mode="HTML"
      )
      await call.answer()


  # === Клик по товару из списка ===
  @router.callback_query(F.data.regexp(r"^prod_\d+$"))
  async def cb_product(call: CallbackQuery, session: AsyncSession, user: User):
      product_id = parse_callback_int(call.data, 1)
      if product_id is None:
          await call.answer("Ошибка", show_alert=True)
          return
      await _show_product(call, session, product_id)
      await call.answer()


  # === Выбор количества ===
  @router.callback_query(F.data.startswith("setqty_"))
  async def cb_setqty(call: CallbackQuery, session: AsyncSession, user: User):
      parts = call.data.split("_")
      if len(parts) < 3:
          await call.answer()
          return
      try:
          product_id = int(parts[1])
          qty = int(parts[2])
      except ValueError:
          await call.answer()
          return
      await _show_product(call, session, product_id, qty)
      await call.answer()


  # === Кнопка "Назад" из карточки товара ===
  @router.callback_query(F.data.startswith("cat_back_"))
  async def cb_cat_back(call: CallbackQuery, session: AsyncSession, user: User):
      product_id = parse_callback_int(call.data, 2)
      if product_id is None:
          await cb_catalog(call, session, user)
          return

      cat_id = await get_product_category_id(session, product_id)
      if cat_id is None:
          await cb_catalog(call, session, user)
          return

      category = await get_category(session, cat_id)
      if not category:
          await cb_catalog(call, session, user)
          return

      product_list = await get_products_in_category(session, cat_id)
      await call.message.edit_text(
          f"<b>{'📁' if category.parent_id else '📂'} {category.name}</b>\n\nВыберите товар:",
          reply_markup=products_kb(product_list, cat_id, parent_cat_id=category.parent_id),
          parse_mode="HTML"
      )
      await call.answer()


  # === Купить товар ===
  @router.callback_query(F.data.startswith("buy_"))
  async def cb_buy(call: CallbackQuery, session: AsyncSession, user: User):
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
          await call.answer("Товар закончился", show_alert=True)
          return

      if stock < UNLIMITED_STOCK and qty > stock:
          await call.answer(f"Доступно только {stock} шт.", show_alert=True)
          return

      now = datetime.now(timezone.utc)
      has_discount = (
          product.discount_percent
          and (not product.discount_expires_at or product.discount_expires_at > now)
      )
      if has_discount:
          d100 = Decimal("100")
          unit_price = product.price * (d100 - product.discount_percent) / d100
      else:
          unit_price = product.price

      cart_items = [{"product_id": product_id, "qty": qty, "price": unit_price}]
      order = await create_order(session, user.id, cart_items)

      await call.message.edit_text(
          f"🛒 <b>Заказ #{order.id} создан</b>\n\n"
          f"{product.name} × {qty}\n"
          f"Итого: <b>{order.total_amount} ₽</b>\n\n"
          f"Выберите способ оплаты:",
          reply_markup=payment_method_kb(order.id),
          parse_mode="HTML"
      )
      await call.answer()
  