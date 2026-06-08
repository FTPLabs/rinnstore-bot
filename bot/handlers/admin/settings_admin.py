import logging
from decimal import Decimal
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...models import User, Admin
from ...services.admin_service import is_admin, log_action
from ...services.settings_service import get_setting, set_setting, get_all_settings
from ...utils.backup import create_backup, list_backups
from ...config import settings as env_settings

logger = logging.getLogger(__name__)
router = Router()


class SettingsState(StatesGroup):
    cryptobot_token = State()
    rollypay_api_key = State()
    rollypay_terminal_id = State()
    rollypay_signing_secret = State()
    rollypay_webhook_host = State()
    support_username = State()
    required_channel = State()
    shop_name = State()
    backup_interval = State()
    add_admin_id = State()
    remove_admin_id = State()
    give_balance_id = State()
    give_balance_amount = State()


def settings_main_kb() -> object:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="₿ CryptoBot Token", callback_data="set_cryptobot_token"),
        InlineKeyboardButton(text="💳 RollyPay", callback_data="set_rollypay_menu"),
    )
    builder.row(
        InlineKeyboardButton(text="💬 Поддержка", callback_data="set_support_username"),
        InlineKeyboardButton(text="📢 Канал", callback_data="set_required_channel"),
    )
    builder.row(
        InlineKeyboardButton(text="🏪 Название магазина", callback_data="set_shop_name"),
    )
    builder.row(
        InlineKeyboardButton(text="👑 Добавить админа", callback_data="admin_add_admin"),
        InlineKeyboardButton(text="🗑 Убрать админа", callback_data="admin_remove_admin"),
    )
    builder.row(
        InlineKeyboardButton(text="💰 Выдать баланс", callback_data="admin_give_balance"),
    )
    builder.row(
        InlineKeyboardButton(text="💾 Резервная копия", callback_data="admin_backup_now"),
        InlineKeyboardButton(text="⏱ Интервал", callback_data="set_backup_interval"),
    )
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_main"))
    return builder.as_markup()


def rollypay_menu_kb() -> object:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔑 API Key", callback_data="set_rollypay_api_key"))
    builder.row(InlineKeyboardButton(text="🖥 Terminal ID", callback_data="set_rollypay_terminal_id"))
    builder.row(InlineKeyboardButton(text="🔐 Signing Secret", callback_data="set_rollypay_signing_secret"))
    builder.row(InlineKeyboardButton(text="🌐 Webhook Host", callback_data="set_rollypay_webhook_host"))
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_settings"))
    return builder.as_markup()


async def show_settings(call: CallbackQuery, session: AsyncSession):
    all_s = await get_all_settings(session)

    token = all_s.get("cryptobot_token", "")
    token_display = f"{token[:8]}..." if len(token) > 8 else ("✅" if token else "❌")

    rp_key = all_s.get("rollypay_api_key", "")
    rp_display = f"{rp_key[:8]}..." if len(rp_key) > 8 else ("✅" if rp_key else "❌")

    channel = all_s.get("required_channel", "") or "не задан"
    webhook_host = all_s.get("webhook_host", env_settings.webhook_host) or "не задан"

    text = (
        "<b>⚙️ Настройки</b>\n\n"
        f"₿ CryptoBot: <code>{token_display}</code>\n"
        f"💳 RollyPay API: <code>{rp_display}</code>\n"
        f"🌐 Webhook: {webhook_host}\n"
        f"💬 Поддержка: @{all_s.get('support_username', 'support')}\n"
        f"📢 Канал: {channel}\n"
        f"🏪 Магазин: {all_s.get('shop_name', 'RINN STORE')}\n"
        f"💾 Бэкап каждые: {all_s.get('backup_interval', '6')}ч"
    )
    await call.message.edit_text(text, reply_markup=settings_main_kb(), parse_mode="HTML")
    await call.answer()


@router.callback_query(F.data == "admin_settings")
async def cb_settings(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await show_settings(call, session)


def _cancel_kb(back_cb: str = "admin_settings"):
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data=back_cb))
    return builder.as_markup()


# ─── CRYPTOBOT ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_cryptobot_token")
async def cb_set_cryptobot(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(SettingsState.cryptobot_token)
    await call.message.edit_text(
        "Введите CryptoBot API Token:\n<i>(получить у @CryptoBot → My Apps → Create App)</i>",
        reply_markup=_cancel_kb(), parse_mode="HTML"
    )
    await call.answer()


@router.message(SettingsState.cryptobot_token)
async def msg_cryptobot_token(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    token = message.text.strip()
    await set_setting(session, "cryptobot_token", token)
    await log_action(session, user.id, "set_setting", "setting", None, {"key": "cryptobot_token"})
    await state.clear()
    await message.answer("✅ CryptoBot Token сохранён.", reply_markup=settings_main_kb())


# ─── ROLLYPAY ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_rollypay_menu")
async def cb_rollypay_menu(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await call.message.edit_text(
        "<b>💳 Настройки RollyPay</b>\n\n"
        "Выберите что настроить:",
        reply_markup=rollypay_menu_kb(), parse_mode="HTML"
    )
    await call.answer()


@router.callback_query(F.data == "set_rollypay_api_key")
async def cb_set_rp_api_key(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(SettingsState.rollypay_api_key)
    await call.message.edit_text(
        "Введите RollyPay API Key:\n<i>(из раздела «Интеграция» в личном кабинете)</i>",
        reply_markup=_cancel_kb("set_rollypay_menu"), parse_mode="HTML"
    )
    await call.answer()


@router.message(SettingsState.rollypay_api_key)
async def msg_rp_api_key(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    val = message.text.strip()
    await set_setting(session, "rollypay_api_key", val)
    await log_action(session, user.id, "set_setting", "setting", None, {"key": "rollypay_api_key"})
    await state.clear()
    await message.answer("✅ RollyPay API Key сохранён.", reply_markup=rollypay_menu_kb())


@router.callback_query(F.data == "set_rollypay_terminal_id")
async def cb_set_rp_terminal(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(SettingsState.rollypay_terminal_id)
    await call.message.edit_text(
        "Введите RollyPay Terminal ID:\n<i>(UUID из раздела «Интеграция»)</i>",
        reply_markup=_cancel_kb("set_rollypay_menu"), parse_mode="HTML"
    )
    await call.answer()


@router.message(SettingsState.rollypay_terminal_id)
async def msg_rp_terminal(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    val = message.text.strip()
    await set_setting(session, "rollypay_terminal_id", val)
    await state.clear()
    await message.answer("✅ RollyPay Terminal ID сохранён.", reply_markup=rollypay_menu_kb())


@router.callback_query(F.data == "set_rollypay_signing_secret")
async def cb_set_rp_secret(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(SettingsState.rollypay_signing_secret)
    await call.message.edit_text(
        "Введите RollyPay Signing Secret:\n<i>(из раздела «Интеграция» — используется для проверки подписи webhook)</i>",
        reply_markup=_cancel_kb("set_rollypay_menu"), parse_mode="HTML"
    )
    await call.answer()


@router.message(SettingsState.rollypay_signing_secret)
async def msg_rp_secret(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    val = message.text.strip()
    await set_setting(session, "rollypay_signing_secret", val)
    await log_action(session, user.id, "set_setting", "setting", None, {"key": "rollypay_signing_secret"})
    await state.clear()
    await message.answer("✅ Signing Secret сохранён.", reply_markup=rollypay_menu_kb())


@router.callback_query(F.data == "set_rollypay_webhook_host")
async def cb_set_rp_webhook(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    current = await get_setting(session, "webhook_host")
    await state.set_state(SettingsState.rollypay_webhook_host)
    await call.message.edit_text(
        f"Текущий: {current or 'не задан'}\n\n"
        "Введите HTTPS URL вашего сервера для webhook:\n"
        "<i>Пример: https://144.31.215.45:9000</i>\n\n"
        "RollyPay будет отправлять статус платежей на:\n"
        "<code>{ваш_host}/webhook/rollypay</code>",
        reply_markup=_cancel_kb("set_rollypay_menu"), parse_mode="HTML"
    )
    await call.answer()


@router.message(SettingsState.rollypay_webhook_host)
async def msg_rp_webhook_host(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    val = message.text.strip().rstrip("/")
    await set_setting(session, "webhook_host", val)
    await state.clear()
    await message.answer(
        f"✅ Webhook Host сохранён.\n\n"
        f"Укажите в RollyPay Callback URL:\n"
        f"<code>{val}/webhook/rollypay</code>",
        parse_mode="HTML", reply_markup=rollypay_menu_kb()
    )


# ─── ПРОЧИЕ НАСТРОЙКИ ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "set_support_username")
async def cb_set_support(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(SettingsState.support_username)
    current = await get_setting(session, "support_username")
    await call.message.edit_text(
        f"Текущий: @{current}\n\nВведите новый username поддержки (без @):",
        reply_markup=_cancel_kb()
    )
    await call.answer()


@router.message(SettingsState.support_username)
async def msg_support_username(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    val = message.text.strip().lstrip("@")
    await set_setting(session, "support_username", val)
    await state.clear()
    await message.answer(f"✅ Поддержка: @{val}", reply_markup=settings_main_kb())


@router.callback_query(F.data == "set_required_channel")
async def cb_set_channel(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(SettingsState.required_channel)
    current = await get_setting(session, "required_channel")
    await call.message.edit_text(
        f"Текущий канал: {current or 'не задан'}\n\n"
        "Введите @username канала или channel_id.\n"
        "<i>Отправьте «-» чтобы отключить проверку подписки.</i>",
        reply_markup=_cancel_kb(), parse_mode="HTML"
    )
    await call.answer()


@router.message(SettingsState.required_channel)
async def msg_required_channel(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    val = message.text.strip()
    if val == "-":
        val = ""
    await set_setting(session, "required_channel", val)
    await state.clear()
    await message.answer(f"✅ Подписка: {val or 'отключена'}", reply_markup=settings_main_kb())


@router.callback_query(F.data == "set_shop_name")
async def cb_set_shop_name(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(SettingsState.shop_name)
    current = await get_setting(session, "shop_name")
    await call.message.edit_text(
        f"Текущее: {current}\n\nВведите новое название магазина:",
        reply_markup=_cancel_kb()
    )
    await call.answer()


@router.message(SettingsState.shop_name)
async def msg_shop_name(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    val = message.text.strip()
    await set_setting(session, "shop_name", val)
    await state.clear()
    await message.answer(f"✅ Название: {val}", reply_markup=settings_main_kb())


@router.callback_query(F.data == "set_backup_interval")
async def cb_set_backup_interval(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="6ч", callback_data="backup_interval_6"),
        InlineKeyboardButton(text="12ч", callback_data="backup_interval_12"),
        InlineKeyboardButton(text="24ч", callback_data="backup_interval_24"),
    )
    builder.row(InlineKeyboardButton(text="✕ Отмена", callback_data="admin_settings"))
    await call.message.edit_text(
        "Выберите интервал резервного копирования:",
        reply_markup=builder.as_markup()
    )
    await call.answer()


@router.callback_query(F.data.startswith("backup_interval_"))
async def cb_backup_interval_set(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    hours = call.data.split("_")[-1]
    await set_setting(session, "backup_interval", hours)
    await call.answer(f"✅ Интервал: {hours}ч")
    await show_settings(call, session)


@router.callback_query(F.data == "admin_backup_now")
async def cb_backup_now(call: CallbackQuery, session: AsyncSession, user: User):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await call.answer("Создаю резервную копию...")
    backups = list_backups()
    backup_list = "\n".join(f"· {b['name']} ({b['size_kb']} KB)" for b in backups) or "нет"
    path = await create_backup(env_settings.database_url)
    if path:
        msg = f"✅ Создана:\n<code>{path}</code>\n\n<b>Все копии:</b>\n{backup_list}"
    else:
        msg = f"❌ Ошибка создания.\n\n<b>Существующие:</b>\n{backup_list}"
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="◀️ Назад", callback_data="admin_settings"))
    await call.message.edit_text(msg, reply_markup=builder.as_markup(), parse_mode="HTML")


@router.callback_query(F.data == "admin_add_admin")
async def cb_add_admin(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(SettingsState.add_admin_id)
    await call.message.edit_text(
        "Введите Telegram ID нового администратора:",
        reply_markup=_cancel_kb()
    )
    await call.answer()


@router.message(SettingsState.add_admin_id)
async def msg_add_admin(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    try:
        new_id = int(message.text.strip())
    except ValueError:
        await message.answer("Неверный ID. Введите число:", reply_markup=_cancel_kb())
        return
    result = await session.execute(select(Admin).where(Admin.user_id == new_id))
    if result.scalar_one_or_none():
        await state.clear()
        await message.answer("Этот пользователь уже администратор.", reply_markup=settings_main_kb())
        return
    from ...models import User as UserModel
    user_result = await session.execute(select(UserModel).where(UserModel.id == new_id))
    if not user_result.scalar_one_or_none():
        placeholder = UserModel(id=new_id, first_name=f"Admin{new_id}", referral_code=f"A{new_id}")
        session.add(placeholder)
        await session.flush()
    admin = Admin(user_id=new_id, role="manager", added_by=user.id)
    session.add(admin)
    await session.commit()
    await log_action(session, user.id, "add_admin", "admin", new_id, {})
    await state.clear()
    await message.answer(f"✅ Администратор {new_id} добавлен.", reply_markup=settings_main_kb())


@router.callback_query(F.data == "admin_remove_admin")
async def cb_remove_admin(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(SettingsState.remove_admin_id)
    result = await session.execute(select(Admin))
    admins = result.scalars().all()
    lines = "\n".join(f"· {a.user_id} ({a.role})" for a in admins)
    await call.message.edit_text(
        f"<b>Администраторы:</b>\n{lines}\n\nВведите ID для удаления:",
        reply_markup=_cancel_kb(), parse_mode="HTML"
    )
    await call.answer()


@router.message(SettingsState.remove_admin_id)
async def msg_remove_admin(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("Неверный ID.", reply_markup=_cancel_kb())
        return
    result = await session.execute(select(Admin).where(Admin.user_id == target_id))
    admin_row = result.scalar_one_or_none()
    if not admin_row:
        await state.clear()
        await message.answer("Администратор не найден.", reply_markup=settings_main_kb())
        return
    await session.delete(admin_row)
    await session.commit()
    await log_action(session, user.id, "remove_admin", "admin", target_id, {})
    await state.clear()
    await message.answer(f"✅ Администратор {target_id} удалён.", reply_markup=settings_main_kb())


@router.callback_query(F.data == "admin_give_balance")
async def cb_give_balance(call: CallbackQuery, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return await call.answer("Нет доступа", show_alert=True)
    await state.set_state(SettingsState.give_balance_id)
    await call.message.edit_text(
        "Введите Telegram ID пользователя для пополнения баланса:",
        reply_markup=_cancel_kb()
    )
    await call.answer()


@router.message(SettingsState.give_balance_id)
async def msg_give_balance_id(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    try:
        target_id = int(message.text.strip())
    except ValueError:
        await message.answer("Неверный ID.", reply_markup=_cancel_kb())
        return
    from ...models import User as UserModel
    result = await session.execute(select(UserModel).where(UserModel.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        await message.answer("Пользователь не найден.", reply_markup=_cancel_kb())
        return
    await state.update_data(give_balance_target_id=target_id)
    await state.set_state(SettingsState.give_balance_amount)
    await message.answer(
        f"Пользователь: {target.first_name or target_id} (баланс: {target.balance} ₽)\n\nВведите сумму:",
        reply_markup=_cancel_kb()
    )


@router.message(SettingsState.give_balance_amount)
async def msg_give_balance_amount(message: Message, session: AsyncSession, user: User, state: FSMContext):
    if not await is_admin(session, user.id):
        return
    try:
        amount = Decimal(message.text.strip().replace(",", "."))
        if amount <= 0:
            raise ValueError
    except Exception:
        await message.answer("Введите положительное число:", reply_markup=_cancel_kb())
        return
    data = await state.get_data()
    target_id = data.get("give_balance_target_id")
    from ...models import User as UserModel
    result = await session.execute(select(UserModel).where(UserModel.id == target_id))
    target = result.scalar_one_or_none()
    if not target:
        await state.clear()
        await message.answer("Пользователь не найден.", reply_markup=settings_main_kb())
        return
    target.balance = (target.balance or Decimal("0")) + amount
    await session.commit()
    await log_action(session, user.id, "give_balance", "user", target_id, {"amount": str(amount)})
    await state.clear()
    await message.answer(
        f"✅ Начислено {amount} ₽ пользователю {target.first_name or target_id}.\n"
        f"Новый баланс: {target.balance} ₽",
        reply_markup=settings_main_kb()
    )
