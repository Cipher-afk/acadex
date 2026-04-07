from sqlmodel import SQLModel, Field, Column, String, BOOLEAN, text, DateTime
from datetime import datetime
import sqlalchemy.dialects.postgresql as pg


class User(SQLModel, table=True):
    telegram_id: str = Field(
        sa_column=Column(pg.VARCHAR, nullable=False, primary_key=True)
    )
    user_id: str
    is_paid: bool = Field(sa_column=Column(pg.BOOLEAN, server_default=text("False")))
    level: str
    expiry: datetime = Field(
        sa_column=Column(pg.DATE, nullable=True, server_default=None)
    )
