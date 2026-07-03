from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SessionMetricsIn(BaseModel):
    """Payload posted by the Focus-State Engine to /ingest/session-metrics.

    Mirrors Seam 2 of the locked contract (DATA_CONTRACT.md). The engine
    computes these; the API only validates and stores them — it never
    recomputes a metric it receives.
    """

    session_id: UUID
    user_id: UUID
    ts_start: datetime
    ts_end: datetime
    switching_rate: float = Field(ge=0, le=1)
    avg_focus_block_minutes: float = Field(ge=0)
    fragmentation: float = Field(ge=0, le=1)
    distraction_ratio: float = Field(ge=0, le=1)


class SessionMetricsOut(BaseModel):
    id: UUID
    user_id: UUID
    ts_start: datetime
    ts_end: datetime | None
    switching_rate: float | None
    avg_focus_block_minutes: float | None
    fragmentation: float | None
    distraction_ratio: float | None
    risk_score: float | None

    model_config = {"from_attributes": True}
