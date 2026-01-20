import asyncio
import logging
from datetime import datetime
from app.config import API_URLS
from app.database import async_session
from app.utils import fetch_data, prepare_odds_data
from app.models import Match, Odds
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

async def upsert_pregame_matches(session: AsyncSession, matches: list, category: str):
    match_data_list = []
    for match in matches:
        match_id = match.get("match_id")
        if not match_id:
            continue

        match_data = {
            "match_id": str(match_id),
            "competition_name": match.get("competition_name"),
            "category": category,
            "country": match.get("category"),
            "event_status": "pregame",
            "live": False,
            "home_team": match.get("home_team"),
            "away_team": match.get("away_team"),
            "start_time": datetime.fromisoformat(match["start_time"]) if match.get("start_time") else None,
            "match_time": "00:00",
        }
        match_data_list.append(match_data)

    if match_data_list:
        # logger.info(f"Upserting {len(match_data_list)} pregame matches.")
        stmt = insert(Match).values(match_data_list)
        stmt = stmt.on_conflict_do_update(
            index_elements=["match_id"],
            set_={col.name: getattr(stmt.excluded, col.name) for col in Match.__table__.columns if col.name != "match_id"}
        )
        await session.execute(stmt)

async def fetch_and_store_pregame_data(url: str, category: str):
    # logger.info(f"Fetching pregame data for category: {category}")
    matches = await fetch_data(url)

    async with async_session() as session:
        if matches:
            await upsert_pregame_matches(session, matches, category)
            odds = await prepare_odds_data(matches, "pregame")
            if odds:
                await session.execute(insert(Odds).values(odds))
            await session.commit()
        else:
            logger.info(f"No pregame matches fetched for {category}")

async def periodic_fetch_pregame():
    while True:
        try:
            await fetch_and_store_pregame_data(API_URLS["football"], "football")
            await fetch_and_store_pregame_data(API_URLS["basketball"], "basketball")
        except Exception as e:
            logger.error(f"Error in periodic_fetch_others: {e}")
        await asyncio.sleep(300)
