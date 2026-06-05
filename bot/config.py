import os
import logging
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    telegram_bot_token: str
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    cryptobot_token: str = ""
    cryptobot_testnet: bool = False
    rollypay_api_key: str = ""
    rollypay_secret: str = ""
    admin_ids: str = ""
    webhook_host: str = ""
    webhook_path: str = "/webhook/bot"
    port: int = 9000
    session_secret: str = ""
    support_username: str = "support"

    @property
    def admin_list(self) -> list[int]:
        if not self.admin_ids:
            return []
        result = []
        for x in self.admin_ids.split(","):
            x = x.strip()
            if not x:
                continue
            try:
                result.append(int(x))
            except ValueError:
                logger.warning(f"Некорректный admin_id в ADMIN_IDS: {x!r} — пропускаем")
        return result

    @property
    def cryptobot_api_url(self) -> str:
        if self.cryptobot_testnet:
            return "https://testnet-pay.crypt.bot/api"
        return "https://pay.crypt.bot/api"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
