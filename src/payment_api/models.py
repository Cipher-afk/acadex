from pydantic import BaseModel


class InitPayment(BaseModel):
    user_id: str
    telegram_id: str
    level: int
