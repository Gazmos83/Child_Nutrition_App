"""Reading and appending food-table revisions (food-table-admin design Decisions 1-2)."""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from backend.models.food_table_revision import FoodTableRevision
from backend.nutrition.foods import LoadedFoodTable, table_from_revision

logger = logging.getLogger(__name__)


class RevisionConflict(Exception):
    """Another write landed first; the caller's table is stale."""


async def load_latest(db: AsyncSession) -> FoodTableRevision | None:
    result = await db.execute(
        select(FoodTableRevision).order_by(FoodTableRevision.revision.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def load_latest_table(engine: AsyncEngine) -> LoadedFoodTable | None:
    """The served table from the newest revision, or None when the table has no rows."""
    async with AsyncSession(engine) as db:
        latest = await load_latest(db)
    if latest is None:
        return None
    return table_from_revision(latest.revision, latest.table)


async def insert_revision(
    db: AsyncSession, payload: dict, actor_user_id: uuid.UUID | None, summary: str
) -> int:
    """Append ``payload`` as the next revision and commit; ``RevisionConflict`` on a race."""
    latest = await load_latest(db)
    revision = (latest.revision if latest is not None else 0) + 1
    db.add(
        FoodTableRevision(
            revision=revision, table=payload, actor_user_id=actor_user_id, summary=summary
        )
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise RevisionConflict(f"revision {revision} was written by someone else") from exc
    logger.info("food_table_revision", extra={"revision": revision, "summary": summary})
    return revision
