from bot.keyboards.admin import admin_main_kb, cancel_kb
from bot.keyboards.user import main_menu_kb


def test_support_is_direct_red_url_button() -> None:
    support = main_menu_kb(support_url="https://t.me/rinnn12333").inline_keyboard[2][0]
    assert support.url == "https://t.me/rinnn12333"
    assert support.callback_data is None
    assert support.style == "danger"


def test_admin_panel_is_red() -> None:
    admin_button = main_menu_kb(is_admin=True).inline_keyboard[-1][0]
    assert admin_button.callback_data == "admin_main"
    assert admin_button.style == "danger"


def test_admin_cancel_is_red() -> None:
    cancel = cancel_kb().inline_keyboard[0][0]
    assert cancel.text == "✕ Отмена"
    assert cancel.style == "danger"


def test_admin_menu_contains_full_test_purchase() -> None:
    buttons = [button for row in admin_main_kb().inline_keyboard for button in row]
    assert any(button.callback_data == "admin_full_test_purchase" for button in buttons)
