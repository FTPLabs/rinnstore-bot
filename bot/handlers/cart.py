from aiogram import Router, F
from aiogram.types import CallbackQuery
from ..keyboards.user import back_to_menu_kb
from ..utils.emoji import BAG
from ..utils.i18n import t

router = Router()


@router.callback_query(F.data == "cart")
async def cb_cart(call: CallbackQuery, user):
    await call.message.edit_text(
        f"{BAG} {t(user, 'buy_from_product')}",
        reply_markup=back_to_menu_kb(user.language_code), parse_mode="HTML"
    )
    await call.answer()
