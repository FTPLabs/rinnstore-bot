"""Вспомогательные утилиты для хэндлеров."""
import logging

logger = logging.getLogger(__name__)


def parse_callback_int(data: str, index: int) -> int | None:
    """
    Безопасно извлекает int из callback_data по индексу (разделитель '_').
    Возвращает None если индекс выходит за границы или значение не является числом.
    """
    try:
        parts = data.split("_")
        return int(parts[index])
    except (IndexError, ValueError, AttributeError) as e:
        logger.warning(f"Не удалось разобрать callback_data={data!r} index={index}: {e}")
        return None
