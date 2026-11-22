from pydantic import BaseModel


class InitPayment(BaseModel):
    user_id: str
    telegram_id: str
    level: int
    referrer: str | None = None
    type: str | None = None


class MarketerModel(BaseModel):
    telegram_id: str
    username: str
    university: str
    password: str
