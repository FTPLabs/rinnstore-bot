import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    telegram_bot_token: str
    database_url: str
    cryptobot_token: str = ""
    cryptobot_testnet: bool = False
    rollypay_api_key: str = ""
    rollypay_secret: str = ""
    admin_ids: str = ""
    webhook_host: str = ""
    webhook_path: str = "/webhook/bot"
    port: int = 9000
    session_secret: str = ""

    @property
    def admin_list(self) -> list[int]:
        if not self.admin_ids:
            return []
        return [int(x.strip()) for x in self.admin_ids.split(",") if x.strip()]

    @property
    def cryptobot_api_url(self) -> str:
        if self.cryptobot_testnet:
            return "https://testnet-pay.crypt.bot/api"
        return "https://pay.crypt.bot/api"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
