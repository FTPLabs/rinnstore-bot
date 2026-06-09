from aiogram import Router, F
from aiogram.types import CallbackQuery
from ..keyboards.user import back_to_menu_kb
from ..utils.emoji import BAG

router = Router()


@router.callback_query(F.data == "cart")
async def cb_cart(call: CallbackQuery):
    await call.message.edit_text(
        f"{BAG} Покупка происходит сразу из карточки товара.",
        reply_markup=back_to_menu_kb(), parse_mode="HTML"
    )
    await call.answer()
