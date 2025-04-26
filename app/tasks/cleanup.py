import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import update, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Match

logger = logging.getLogger(__name__)


async def cleanup_pending_matches(session: AsyncSession):
    """Update matches stuck in 'pending' status if they are past 3 hours from start_time."""
    now = datetime.utcnow()
    threshold_time = now - timedelta(hours=3)

    # logger.info(f"Cleaning up matches with 'pending' status before {threshold_time.isoformat()}")

    try:
        stmt = (
            update(Match)
            .where(
                and_(
                    Match.event_status == 'pending',
                    Match.start_time != None,
                    Match.start_time < threshold_time
                )
            )
            .values(event_status='ended', live=False)
        )

        result = await session.execute(stmt)
        await session.commit()

        # logger.info(f"Marked {result.rowcount} matches as ended.")
    except Exception as e:
        # logger.error(f"Error during cleanup of pending matches: {e}")
        await session.rollback()


async def periodic_cleanup():
    """Run cleanup every 10 minutes."""
    while True:
        # logger.info("Running pending match cleanup task.")
        async with async_session() as session:
            await cleanup_pending_matches(session)
        await asyncio.sleep(600)  # 10 minutes
