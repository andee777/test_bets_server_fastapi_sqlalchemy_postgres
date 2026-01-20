import asyncio
import logging
from app.config import API_URLS
from app.database import async_session
from app.utils import fetch_data, prepare_odds_data, get_match_time
from app.models import Match, Odds
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import select, update, not_, or_
from sqlalchemy.ext.asyncio import AsyncSession
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

async def upsert_matches(session: AsyncSession, matches: list, category: str):
    match_data_list = []
    for match in matches:
        match_id = match.get("match_id")
        if not match_id:
            continue

        match_time = get_match_time(match.get("event_status"), match.get("match_time"))
        match_data = {
            "match_id": str(match_id),
            "competition_name": match.get("competition_name"),
            "category": category,
            "country": match.get("category"),
            "event_status": match.get("event_status"),
            "live": True,
            "home_team": match.get("home_team").strip(),
            "away_team": match.get("away_team").strip(),
            "start_time": datetime.fromisoformat(match["start_time"]) if match.get("start_time") else None,
            "match_time": match_time,
        }
        match_data_list.append(match_data)

    if match_data_list:
        # logger.info(f"Upserting {len(match_data_list)} live matches.")
        stmt = insert(Match).values(match_data_list)
        stmt = stmt.on_conflict_do_update(
            index_elements=["match_id"],
            set_={col.name: getattr(stmt.excluded, col.name) for col in Match.__table__.columns if col.name != "match_id"}
        )
        await session.execute(stmt)

async def update_missing_live_matches(session: AsyncSession, matches: list, category: str):
    api_match_ids = {str(m.get("match_id")) for m in matches if m.get("match_id")}
    # logger.info(f"update_missing_live_matches(): Fetched {len(api_match_ids)} live matches.")

    result = await session.execute(
        select(Match.match_id, Match.live, Match.event_status, Match.match_time).where(
            Match.category == category,
            not_(or_(
                Match.event_status.ilike("pregame"),
                Match.event_status.ilike("ended")
            ))
        )
    )
    db_matches = result.fetchall()
    # logger.info(f"update_missing_live_matches(): Comparing with {len(db_matches)} matches in database.")

    to_false, to_ended = [], []
    for match_id, live, status, match_time in db_matches:
        if str(match_id) not in api_match_ids:
            if match_time == "90:00":
                to_ended.append(match_id)
            else:
                to_false.append(match_id)

    # logger.info(f"update_missing_live_matches() - to_ended: {to_ended}")
    if to_false:
        await session.execute(update(Match).where(Match.match_id.in_(to_false)).values(live=False, event_status="pending"))
    if to_ended:
        await session.execute(update(Match).where(Match.match_id.in_(to_ended)).values(live=False, event_status="ended"))
    await session.commit()


async def check_ended(session: AsyncSession, match_ids: list[int]):
    """
    Check if matches have ended by verifying scores from FotMob.
    Compares matches based on country, home team, and away team names.
    Updates matches that have ended to live=False and event_status="ended".
    """
    if not match_ids:
        return
    
    try:
        # Fetch match details from database
        result = await session.execute(
            select(
                Match.match_id,
                Match.country,
                Match.home_team,
                Match.away_team
            ).where(Match.match_id.in_(match_ids))
        )
        
        db_matches = {}
        for match_id, country, home_team, away_team in result.fetchall():
            # Normalize for comparison
            key = (
                (country or "").strip().lower(),
                (home_team or "").strip().lower(),
                (away_team or "").strip().lower()
            )
            db_matches[key] = match_id
        
        # Get current date in the format FotMob expects (YYYYMMDD)
        date_str = datetime.now().strftime("%Y%m%d")
        url = f"https://www.fotmob.com/api/matches?date={date_str}"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()
        
        # Find finished matches that match our database records
        to_ended = []
        
        leagues = data.get("leagues", [])
        for league in leagues:
            country = league.get("name", "")  # or use "ccode" for country code
            matches = league.get("matches", [])
            
            for match in matches:
                status = match.get("status", {})
                finished = status.get("finished", False)
                
                if not finished:
                    continue
                
                home_team = match.get("home", {}).get("name", "")
                away_team = match.get("away", {}).get("name", "")
                
                # Normalize for comparison
                key = (
                    country.strip().lower(),
                    home_team.strip().lower(),
                    away_team.strip().lower()
                )
                
                # Check if this match is in our to_check_ended list
                if key in db_matches:
                    to_ended.append(db_matches[key])
        
        if to_ended:
            await session.execute(
                update(Match)
                .where(Match.match_id.in_(to_ended))
                .values(live=False, event_status="ended")
            )
            # logger.info(f"Marked {len(to_ended)} matches as ended: {to_ended}")
    
    except Exception as e:
        # logger.error(f"Error checking ended matches: {e}")
        pass  # Don't fail the whole process if FotMob check fails

async def handle_missing_live_matches(session: AsyncSession, category: str):
    # logger.info(f"handle_missing_live_matches(): Checking for pending games")
    result = await session.execute(
        select(Match.match_id, Match.live, Match.event_status, Match.match_time).where(
            Match.category == category,
            not_(or_(
                Match.event_status.ilike("pregame"),
                Match.event_status.ilike("ended")
            ))
        )
    )
    to_false, to_check_ended = [], []
    for match_id, live, status, match_time in result.fetchall():
        if live and (status or "").lower() != "pregame":
            if match_time == "90:00":
                to_check_ended.append(match_id)
            else:
                to_false.append(match_id)

    if to_false:
        await session.execute(update(Match).where(Match.match_id.in_(to_false)).values(live=False, event_status="pending"))
    if to_check_ended:
        await session.execute(update(Match).where(Match.match_id.in_(to_check_ended)).values(live=False, event_status="ended"))
        # await check_ended(to_check_ended)
    await session.commit()

async def fetch_and_store_live_data(url: str, category: str):
    # logger.info(f"Fetching live data for category: {category}")
    matches = await fetch_data(url)

    async with async_session() as session:
        if matches:
            await upsert_matches(session, matches, category)
            await update_missing_live_matches(session, matches, category)
            odds = await prepare_odds_data(matches, "live")
            if odds:
                await session.execute(insert(Odds).values(odds))
            await session.commit()
        else:
            # logger.info(f"**** No live data was fetched for category: {category} ****")
            await handle_missing_live_matches(session, category)

async def periodic_fetch_live():
    while True:
        # logger.info(f"---- In periodic_fetch_live()")
        try:
            await fetch_and_store_live_data(API_URLS["live"], "football")
        except Exception as e:
            logger.error(f"Error in periodic_fetch_live: {e}")
        await asyncio.sleep(10)
