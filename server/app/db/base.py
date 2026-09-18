from datetime import datetime

import ulid
from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_ulid() -> str:
    return str(ulid.ULID())


class Base(DeclarativeBase):
    pass


class ULIDPrimaryKeyMixin:
    id: Mapped[str] = mapped_column(
        String(26), primary_key=True, default=new_ulid, sort_order=-100
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class OptimisticLockMixin:
    version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
