from sqlmodel import SQLModel, Field, Column, String, BOOLEAN, text, DateTime
from datetime import datetime


class User(SQLModel, table=True):
    telegram_id: str = Field(sa_column=Column(String, nullable=False, primary_key=True))
    user_id: str
    is_paid: bool = Field(sa_column=Column(BOOLEAN, server_default=text("False")))
    level: str
    expiry: datetime = Field(
        sa_column=Column(DateTime, nullable=True, server_default=None)
    )
