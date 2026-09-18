from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    Base,
    OptimisticLockMixin,
    TimestampMixin,
    ULIDPrimaryKeyMixin,
)


class Organization(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )


class User(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "users"

    organization_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("organizations.id"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    is_teacher: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )


class AuthSession(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "auth_sessions"

    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (
        Index("ix_auth_sessions_user_active", "user_id", "expires_at"),
    )


class Course(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "courses"

    organization_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("organizations.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    term: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="Asia/Shanghai",
        server_default="Asia/Shanghai",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )
    created_by: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)


class CourseMember(Base, ULIDPrimaryKeyMixin, OptimisticLockMixin, TimestampMixin):
    __tablename__ = "course_members"

    course_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("courses.id"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", server_default="active"
    )

    __table_args__ = (
        UniqueConstraint("course_id", "user_id", name="uq_course_members_course_user"),
        CheckConstraint("role IN ('teacher','student','assistant')", name="ck_course_members_role"),
        CheckConstraint("status IN ('active','removed')", name="ck_course_members_status"),
    )


class AuditLog(Base, ULIDPrimaryKeyMixin):
    __tablename__ = "audit_logs"

    actor_id: Mapped[str | None] = mapped_column(String(26), ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False)
    resource_id: Mapped[str | None] = mapped_column(String(26))
    course_id: Mapped[str | None] = mapped_column(String(26))
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IdempotencyRecord(Base, ULIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "idempotency_records"

    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    user_id: Mapped[str] = mapped_column(String(26), ForeignKey("users.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(200), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            "user_id",
            "endpoint",
            name="uq_idempotency_key_user_endpoint",
        ),
    )
