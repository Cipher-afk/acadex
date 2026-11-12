from sqlmodel import (
    SQLModel,
    Field,
    Column,
    String,
    BOOLEAN,
    text,
    DateTime,
    Relationship,
)
from datetime import datetime
import sqlalchemy.dialects.postgresql as pg
from typing import Optional, List


class User(SQLModel, table=True):
    __tablename__ = "users"
    telegram_id: str = Field(
        sa_column=Column(pg.VARCHAR, nullable=False, primary_key=True)
    )
    user_id: str
    is_paid: bool = Field(sa_column=Column(pg.BOOLEAN, server_default=text("False")))
    level: int
    referrer: Optional[str] = Field(
        foreign_key="marketer.marketer_username", nullable=True
    )
    expiry: datetime = Field(
        sa_column=Column(pg.DATE, nullable=True, server_default=None)
    )
    marketer: "Marketer" = Relationship(
        back_populates="users", sa_relationship_kwargs={"lazy": "selectin"}
    )


class Marketer(SQLModel, table=True):
    __tablename__ = "marketer"
    telegram_id: str = Field(
        sa_column=Column(pg.VARCHAR, nullable=False, primary_key=True)
    )
    username: str = Field(sa_column=Column(pg.VARCHAR, nullable=False, unique=True))
    password: str
    university: str = Field(sa_column=Column(pg.VARCHAR, server_default="FUO"))
    amount_paid: int = Field(default=0)
    subscribed: bool = Field(default=False)
    users: List[User] = Relationship(
        back_populates="marketer", sa_relationship_kwargs={"lazy": "selectin"}
    )
