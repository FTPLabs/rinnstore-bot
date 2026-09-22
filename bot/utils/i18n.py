from __future__ import annotations

from typing import Any

SUPPORTED_LANGUAGES = {"ru", "en"}

TEXTS = {
    "ru": {
        "catalog": "Каталог", "orders": "Мои заказы", "promo": "Промокод", "profile": "Профиль", "support": "Поддержка",
        "admin": "Админ-панель", "language": "Язык", "choose_language": "Выберите язык:", "language_changed": "Язык изменён.",
        "russian": "Русский", "english": "English", "back": "Назад", "menu": "Меню", "buy_key": "Купить свой ключ",
        "welcome_subtitle": "Цифровые товары · Крипто · Мгновенно", "welcome_access": "Для доступа к боту:",
        "subscribe": "Подпишитесь на наш канал", "terms_step": "Ознакомьтесь с условиями", "accept_step": "Нажмите «Принимаю»",
        "subscribe_channel": "Подписаться на канал", "terms": "Соглашение", "privacy": "Конфиденц.", "accept": "Принимаю условия",
        "captcha": "Введите цифры с картинки:", "captcha_wrong": "Неверно. Попробуйте снова:", "sub_required": "Для продолжения необходима подписка на канал:",
        "sub_check": "Проверить подписку", "sub_confirmed": "Подписка подтверждена!", "not_subscribed": "Вы ещё не подписались на канал.",
        "catalog_empty": "Каталог пуст.", "product_not_found": "Товар не найден", "choose_category": "Выберите категорию:", "choose_subcategory": "Выберите подкатегорию:",
        "choose_product": "Выберите товар:", "no_products": "Товаров пока нет.", "in_stock": "В наличии", "no_stock": "Нет в наличии",
        "price": "Цена", "stock": "В наличии", "unlimited": "Безлимитно", "buy": "Купить", "total": "Итого",
        "order": "Заказ", "orders_empty": "Заказов пока нет.", "my_orders": "Мои заказы", "status": "Статус", "paid": "Оплачен",
        "delivered": "Выдан", "pending": "Ожидает оплаты", "cancelled": "Отменён", "partial": "Частично выдан", "get_item": "Получить товар",
        "review_prompt": "Купленный товар: {product}\nСтоимость: {amount} ₽\nНомер заказа: #{order_id}\n\nОценка и отзыв:\nВыберите оценку от 1 до 5:",
        "review_rate": "Спасибо! Напишите отзыв одним сообщением или пропустите комментарий.", "skip_comment": "Пропустить комментарий",
        "review_saved": "Спасибо! Отзыв принят и будет опубликован в канале.", "buy_your_key": "🛒 Купить свой ключ",
        "review_unavailable": "Этот отзыв уже обработан или недоступен", "error": "Произошла ошибка.",
        "profile_title": "ПРОФИЛЬ", "name": "Имя", "level": "Уровень", "newcomer": "Новичок", "regular": "Постоянный", "vip": "VIP", "registered": "Регистрация", "spent": "Потрачено", "ref_bonus": "Реф. бонус", "ref_program": "РЕФЕРАЛЬНАЯ ПРОГРАММА", "invited": "Приглашено друзей", "your_code": "Ваш код", "link": "Ссылка", "role": "Роль", "administrator": "Администратор", "write_support": "Пишите нам", "buy_from_product": "Покупка происходит сразу из карточки товара.",
        "error_data": "Ошибка данных", "order_unavailable": "Заказ недоступен", "order_not_found": "Заказ не найден", "order_processed": "Заказ уже обработан", "payment_error": "Ошибка создания платежа. Попробуйте позже.", "create_invoice": "Создаю платёжную ссылку...", "payment_order": "Оплата заказа #{order_id}", "sum": "Сумма", "payable": "К оплате", "choose_payment": "Выберите способ оплаты:", "payment_success": "Оплата прошла успешно!", "payment_pending": "Оплата ещё не поступила.", "payment_not_found": "Платёж не найден", "data_delivery_error": "Ошибка выдачи товара. Напишите в поддержку.", "not_paid": "Заказ ещё не оплачен", "delivered_items": "Товары заказа", "cancel": "Отмена", "cancelled_order": "Заказ отменён", "back": "Назад", "success_title": "Оплата прошла успешно", "failure_title": "Оплата не завершена", "return_to_bot": "Вернитесь в Telegram-бот — заказ будет выдан после подтверждения.",
    },
    "en": {
        "catalog": "Catalog", "orders": "My orders", "promo": "Promo code", "profile": "Profile", "support": "Support",
        "admin": "Admin panel", "language": "Language", "choose_language": "Choose a language:", "language_changed": "Language changed.",
        "russian": "Русский", "english": "English", "back": "Back", "menu": "Menu", "buy_key": "Buy your key",
        "welcome_subtitle": "Digital goods · Crypto · Instant delivery", "welcome_access": "To access the bot:",
        "subscribe": "Subscribe to our channel", "terms_step": "Review the terms", "accept_step": "Press «Accept»",
        "subscribe_channel": "Subscribe to channel", "terms": "Terms", "privacy": "Privacy", "accept": "Accept terms",
        "captcha": "Enter the digits from the image:", "captcha_wrong": "Incorrect. Try again:", "sub_required": "You must subscribe to the channel to continue:",
        "sub_check": "Check subscription", "sub_confirmed": "Subscription confirmed!", "not_subscribed": "You have not subscribed yet.",
        "catalog_empty": "The catalog is empty.", "product_not_found": "Product not found", "choose_category": "Choose a category:", "choose_subcategory": "Choose a subcategory:",
        "choose_product": "Choose a product:", "no_products": "There are no products yet.", "in_stock": "In stock", "no_stock": "Out of stock",
        "price": "Price", "stock": "In stock", "unlimited": "Unlimited", "buy": "Buy", "total": "Total",
        "order": "Order", "orders_empty": "You have no orders yet.", "my_orders": "My orders", "status": "Status", "paid": "Paid",
        "delivered": "Delivered", "pending": "Awaiting payment", "cancelled": "Cancelled", "partial": "Partially delivered", "get_item": "Get product",
        "review_prompt": "Purchased product: {product}\nCost: {amount} RUB\nOrder number: #{order_id}\n\nRating and review:\nChoose a rating from 1 to 5:",
        "review_rate": "Thank you! Write a review in one message or skip the comment.", "skip_comment": "Skip comment",
        "review_saved": "Thank you! Your review was accepted and will be published in the channel.", "buy_your_key": "🛒 Buy your key",
        "review_unavailable": "This review has already been processed or is unavailable", "error": "Something went wrong.",
        "profile_title": "PROFILE", "name": "Name", "level": "Level", "newcomer": "Newcomer", "regular": "Regular", "vip": "VIP", "registered": "Registered", "spent": "Spent", "ref_bonus": "Referral bonus", "ref_program": "REFERRAL PROGRAM", "invited": "Friends invited", "your_code": "Your code", "link": "Link", "role": "Role", "administrator": "Administrator", "write_support": "Write to us", "buy_from_product": "Purchase is made directly from the product card.",
        "error_data": "Invalid data", "order_unavailable": "Order unavailable", "order_not_found": "Order not found", "order_processed": "Order already processed", "payment_error": "Payment creation failed. Please try again later.", "create_invoice": "Creating payment link...", "payment_order": "Payment for order #{order_id}", "sum": "Amount", "payable": "Payable", "choose_payment": "Choose a payment method:", "payment_success": "Payment completed successfully!", "payment_pending": "Payment has not arrived yet.", "payment_not_found": "Payment not found", "data_delivery_error": "Product delivery failed. Please contact support.", "not_paid": "The order has not been paid yet", "delivered_items": "Order products", "cancel": "Cancel", "cancelled_order": "Order cancelled", "back": "Back", "success_title": "Payment successful", "failure_title": "Payment not completed", "return_to_bot": "Return to the Telegram bot — your order will be delivered after confirmation.",
    },
}


def lang(value: Any) -> str:
    code = value if isinstance(value, str) else getattr(value, "language_code", "ru")
    return "en" if str(code or "").lower().startswith("en") else "ru"


def t(value: Any, key: str, **kwargs: Any) -> str:
    text = TEXTS[lang(value)].get(key, TEXTS["ru"].get(key, key))
    return text.format(**kwargs) if kwargs else text


def localized_name(obj: Any, value: Any) -> str:
    """Return the requested catalog language, falling back to the source name."""
    if lang(value) == "en" and getattr(obj, "name_en", None):
        return obj.name_en
    return getattr(obj, "name", "")


def localized_description(obj: Any, value: Any) -> str:
    if lang(value) == "en" and getattr(obj, "description_en", None):
        return obj.description_en
    return getattr(obj, "description", "") or ""
