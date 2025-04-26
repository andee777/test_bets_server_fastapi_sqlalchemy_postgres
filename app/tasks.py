# app/tasks.py
import asyncio
import logging
from datetime import datetime

from app.config import API_URLS
from app.database import async_session
from app.utils import fetch_data, prepare_odds_data, get_match_time
from app.models import Match, Odds
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession  # Explicitly import AsyncSession if needed as a type hint

logger = logging.getLogger(__name__)

async def upsert_matches(session: AsyncSession, matches: list, category: str, fetch_event_status: str):
    match_data_list = []
    for match in matches:
        match_id = match.get("match_id")
        if not match_id:
            continue

        country = match.get("category")
        fetched_match_time = match.get("match_time")
        event_status = match.get("event_status")
        if fetch_event_status == "pregame":
            real_status = "pregame"
            match_time = "00:00"
            is_live = False
        else:
            real_status = event_status
            match_time = get_match_time(event_status, fetched_match_time)
            is_live = True if fetch_event_status == "live" else False

        match_data = {
            "match_id": str(match_id),
            "competition_name": match.get("competition_name"),
            "category": category,
            "country": country,
            "event_status": real_status,
            "live": is_live,
            "home_team": match.get("home_team"),
            "away_team": match.get("away_team"),
            "start_time": datetime.fromisoformat(match["start_time"]) if match.get("start_time") else None,
            "match_time": match_time,
        }
        match_data_list.append(match_data)

    if match_data_list:
        logger.info(f"Upserting {len(match_data_list)} matches into match table.")
        try:
            stmt = insert(Match).values(match_data_list)
            set_dict = {
                col.name: getattr(stmt.excluded, col.name)
                for col in Match.__table__.columns if col.name != "match_id"
            }
            stmt = stmt.on_conflict_do_update(
                index_elements=["match_id"],
                set_=set_dict
            )
            await session.execute(stmt)
        except Exception as e:
            logger.error(f"Error upserting matches: {e}")

async def update_missing_live_matches(session: AsyncSession, matches: list, category: str):
    api_match_ids = {str(match.get("match_id")) for match in matches if match.get("match_id")}
    logger.info(f"update_missing_live_matches(): Fetched {len(api_match_ids)} live matches.")

    result = await session.execute(
        select(Match.match_id, Match.live, Match.event_status, Match.match_time).where(Match.category == category)
    )
    db_records = result.fetchall()
    logger.info(f"update_missing_live_matches(): Comparing with {len(db_records)} matches in database.")

    to_update_ids_live_false = []
    to_update_ids_ended = []

    for match_id, live_flag, event_status, match_time in db_records:
        if str(match_id) not in api_match_ids:
            if (event_status or "").lower() != "pregame" or (event_status or "").lower() != "ended":
                if match_time == "90:00":
                    to_update_ids_ended.append(match_id)
                else:
                    to_update_ids_live_false.append(match_id)

    if to_update_ids_live_false:
        logger.info(f"update_missing_live_matches(): Updating {len(to_update_ids_live_false)} matches to not live (live=False, event_status=pending).")
        try:
            await session.execute(
                update(Match).where(Match.match_id.in_(to_update_ids_live_false)).values(live=False, event_status="pending")
            )
            await session.commit()
        except Exception as e:
            logger.error(f"Error updating missing live matches (live=False): {e}")
            await session.rollback()

    if to_update_ids_ended:
        logger.info(f"update_missing_live_matches(): Updating {len(to_update_ids_ended)} matches to ended (event_status='ended', live=False).")
        try:
            await session.execute(
                update(Match).where(Match.match_id.in_(to_update_ids_ended)).values(live=False, event_status="ended")
            )
            await session.commit()
        except Exception as e:
            logger.error(f"Error updating missing live matches (ended): {e}")
            await session.rollback()

async def handle_missing_live_matches(session: AsyncSession, category: str):
    result = await session.execute(
        select(Match.match_id, Match.live, Match.event_status, Match.match_time).where(Match.category == category)
    )
    db_records = result.fetchall()

    to_update_ids_live_false = []
    to_update_ids_ended = []

    for match_id, live_flag, db_status, match_time in db_records:
        if live_flag and (db_status or "").lower() != "pregame":
            logger.info(f"handle_missing_live_matches(): Considering match_id={match_id}, live={live_flag}, status={db_status}, time={match_time}")
            if match_time == "90:00":
                to_update_ids_ended.append(match_id)
            else:
                to_update_ids_live_false.append(match_id)

    if to_update_ids_live_false:
        logger.info(f"handle_missing_live_matches(): Updating {len(to_update_ids_live_false)} missing live matches to not live (live=False, event_status=pending).")
        try:
            await session.execute(
                update(Match).where(Match.match_id.in_(to_update_ids_live_false)).values(live=False, event_status="pending")
            )
            await session.commit()
        except Exception as e:
            logger.error(f"Error handling missing live matches (live=False): {e}")
            await session.rollback()

    if to_update_ids_ended:
        logger.info(f"handle_missing_live_matches(): Updating {len(to_update_ids_ended)} matches to ended (event_status='ended', live=False).")
        try:
            await session.execute(
                update(Match).where(Match.match_id.in_(to_update_ids_ended)).values(live=False, event_status="ended")
            )
            await session.commit()
        except Exception as e:
            logger.error(f"Error handling missing live matches (ended): {e}")
            await session.rollback()

async def fetch_and_store_data(url: str, category: str, fetch_event_status: str):
    logger.info(f"Fetching {category} data for status: {fetch_event_status}")
    matches = await fetch_data(url)

    async with async_session() as session:
        if matches:
            await upsert_matches(session, matches, category, fetch_event_status)
            if fetch_event_status == "live":
                await update_missing_live_matches(session, matches, category)
            odds_data_list = await prepare_odds_data(matches, fetch_event_status)
            if odds_data_list:
                try:
                    stmt = insert(Odds).values(odds_data_list)
                    await session.execute(stmt)
                except Exception as e:
                    logger.error(f"Error inserting odds data: {e}")
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Error committing data for {category}: {e}")
        else:
            if fetch_event_status == "live":
                await handle_missing_live_matches(session, category)

# Background tasks

async def periodic_fetch_live():
    while True:
        logger.info(f"- in periodic_fetch_live")
        try:
            await fetch_and_store_data(API_URLS["live"], "football", "live")
        except Exception as e:
            logger.error(f"Error in periodic_fetch_live: {e}")
        await asyncio.sleep(10)

async def periodic_fetch_others():
    while True:
        try:
            await fetch_and_store_data(API_URLS["football"], "football", "pregame")
            await fetch_and_store_data(API_URLS["basketball"], "basketball", "pregame")
        except Exception as e:
            logger.error(f"Error in periodic_fetch_others: {e}")
        await asyncio.sleep(300)