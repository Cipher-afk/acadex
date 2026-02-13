from sqlmodel import SQLModel, Field, Column, String, BOOLEAN, text


class User(SQLModel, table=True):
    telegram_id: str = Field(sa_column=Column(String, nullable=False, primary_key=True))
    is_paid: bool = Field(sa_column=Column(BOOLEAN, server_default=text("False")))
    level: str
