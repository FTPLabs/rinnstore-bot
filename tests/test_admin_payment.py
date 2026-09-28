from bot.handlers.start import _support_url


def test_support_username_opens_direct_telegram_chat() -> None:
    assert _support_url("@rinnn12333") == "https://t.me/rinnn12333"
