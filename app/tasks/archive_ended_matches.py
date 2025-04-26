# app/tasks_archive.py
from sqlalchemy import select, insert, delete
from app.models import Match, EndedMatch
from app.database import async_session  # or your session factory
import logging
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio

logger = logging.getLogger(__name__)


async def archive_ended_matches():
    async with async_session() as session:
        result = await session.execute(
            select(Match).where(Match.event_status.ilike("ended"))
        )
        ended = result.scalars().all()

        if not ended:
            logger.info("\n*********************************************************************\n\n\t\t\tNo matches to archive.\n\n*********************************************************************")
            return

        # Convert Match rows to EndedMatch format
        ended_data = [
            {
                "match_id": m.match_id,
                "competition_name": m.competition_name,
                "category": m.category,
                "country": m.country,
                "home_team": m.home_team,
                "away_team": m.away_team,
                "event_status": m.event_status,
                "live": m.live,
                "start_time": m.start_time,
                "match_time": m.match_time
            }
            for m in ended
        ]
        # logger.info(f"------ archive_ended_matches(): len ended_data: {len(ended_data)}")

        try:
            await session.execute(insert(EndedMatch).values(ended_data))
            await session.execute(delete(Match).where(Match.match_id.in_([m.match_id for m in ended])))
            await session.commit()
            logger.info(f"\n*********************************************************************\n\n\t\tMoved {len(ended)} matches to ended_matches.\n\n*********************************************************************")

        except Exception as e:
            logger.error(f"archive_ended_matches() failed: {e}")
            await session.rollback()


async def periodic_archive_ended_matches():
    # logger.info(f"************* ---- In periodic_archive_ended_matches()")
    while True:
        await archive_ended_matches()
        await asyncio.sleep(3600)  # Every hour