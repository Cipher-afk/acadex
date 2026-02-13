from pydantic import BaseModel


class InitPayment(BaseModel):
    telegram_id: str
    level: int
