from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command

router = Router()

@router.message(Command("privacy"))
async def privacy_cmd(message: Message):
    await message.answer("📜 **Пользовательское соглашение**\n\nВы можете ознакомиться с соглашением по ссылке:\nhttps://telegra.ph")
