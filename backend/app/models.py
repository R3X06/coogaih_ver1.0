import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Session(Base):
    """Mirrors the `sessions` table in db/schema.sql. Kept in sync by hand —
    schema.sql is the source of truth for migrations; this model is for
    querying/writing via the API.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    ts_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ts_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    switching_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_focus_block_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    fragmentation: Mapped[float | None] = mapped_column(Float, nullable=True)
    distraction_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
