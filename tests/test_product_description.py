from bot.utils.product_description import product_description_to_html


def test_legacy_unicode_emoji_are_upgraded_to_telegram_custom_emoji() -> None:
    rendered = product_description_to_html("🔥 Сертификат ✅\n📱 Помощь ⏳")
    assert '<tg-emoji emoji-id="5893185207355315979">🔥</tg-emoji>' in rendered
    assert '<tg-emoji emoji-id="5895514131896733546">✅</tg-emoji>' in rendered
    assert '<tg-emoji emoji-id="5895652322469482989">📱</tg-emoji>' in rendered
    assert '<tg-emoji emoji-id="5893100690988863311">⏳</tg-emoji>' not in rendered
    assert "⏳" in rendered


def test_existing_custom_emoji_tags_are_not_nested() -> None:
    stored = 'telegram-html:v1:<tg-emoji emoji-id="123">🔥</tg-emoji> ✅'
    rendered = product_description_to_html(stored)
    assert rendered.count("<tg-emoji") == 2
    assert '<tg-emoji emoji-id="123">🔥</tg-emoji>' in rendered
    assert '<tg-emoji emoji-id="5895514131896733546">✅</tg-emoji>' in rendered
