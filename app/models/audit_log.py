from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.common import LOCAL_TIMEZONE


class AuditLog(Base):
    """Запись аудита: что произошло с какой сущностью и когда."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False, comment="created/archived/restored")
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, comment="Тип сущности")
    entity_id: Mapped[int] = mapped_column(nullable=False, comment="ID сущности")
    entity_name: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="Имя сущности (если есть)")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )

    @property
    def local_created_at(self) -> datetime | None:
        if self.created_at is None:
            return None
        return self.created_at.astimezone(LOCAL_TIMEZONE)
