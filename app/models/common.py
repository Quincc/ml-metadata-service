from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


LOCAL_TIMEZONE = ZoneInfo("Asia/Yekaterinburg")


class TimeStampMixin:
    """Общие поля времени для моделей."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    def mark_deleted(self) -> None:
        self.deleted_at = datetime.now(UTC)

    def restore(self) -> None:
        self.deleted_at = None

    @staticmethod
    def _to_local(dt: datetime | None) -> datetime | None:
        if dt is None:
            return None
        return dt.astimezone(LOCAL_TIMEZONE)

    @property
    def local_created_at(self) -> datetime | None:
        """Локальная дата создания."""
        return self._to_local(self.created_at)

    @property
    def local_updated_at(self) -> datetime | None:
        """Локальная дата обновления."""
        return self._to_local(self.updated_at)

    @property
    def local_deleted_at(self) -> datetime | None:
        """Локальная дата удаления."""
        return self._to_local(self.deleted_at)


TimestampMixin = TimeStampMixin
