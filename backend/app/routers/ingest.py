from fastapi import APIRouter, Depends
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models import Session as SessionModel
from app.schemas import SessionMetricsIn, SessionMetricsOut

router = APIRouter(prefix="/ingest", tags=["ingest"])


@router.post("/session-metrics", response_model=SessionMetricsOut, status_code=201)
async def ingest_session_metrics(
    payload: SessionMetricsIn,
    db: AsyncSession = Depends(get_db),
) -> SessionMetricsOut:
    """Receives computed metrics from the Focus-State Engine (Seam 2 of the
    locked contract) and upserts them onto the session row.

    Idempotent on session_id: if the engine retries or resends a correction
    for the same session, this updates in place rather than duplicating.
    """
    stmt = (
        insert(SessionModel)
        .values(
            id=payload.session_id,
            user_id=payload.user_id,
            ts_start=payload.ts_start,
            ts_end=payload.ts_end,
            switching_rate=payload.switching_rate,
            avg_focus_block_minutes=payload.avg_focus_block_minutes,
            fragmentation=payload.fragmentation,
            distraction_ratio=payload.distraction_ratio,
        )
        .on_conflict_do_update(
            index_elements=[SessionModel.id],
            set_={
                "ts_end": payload.ts_end,
                "switching_rate": payload.switching_rate,
                "avg_focus_block_minutes": payload.avg_focus_block_minutes,
                "fragmentation": payload.fragmentation,
                "distraction_ratio": payload.distraction_ratio,
            },
        )
        .returning(SessionModel)
    )
    result = await db.execute(stmt)
    row = result.scalar_one()
    await db.commit()
    return SessionMetricsOut.model_validate(row)
