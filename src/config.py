from pydantic_settings import BaseSettings, SettingsConfigDict
import os


class Settings(BaseSettings):
    DATABASE_URL: str
    BOT_TOKEN: str
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: str
    PAYMENT_SECRET_KEY: str
    PAYSTACK_LINK: str
    model_config = SettingsConfigDict(env_file="./.env", extra="ignore")


settings = Settings()
