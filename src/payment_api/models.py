from pydantic import BaseModel


class InitPayment(BaseModel):
    user_id: str
    telegram_id: str
    level: int
    referrer:str

class MarketerModel(BaseModel):
    telegram_id:str
    username:str
    password:str

