# app/main.py
import os
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager
from collections import defaultdict

from fastapi import FastAPI, HTTPException
from sqlalchemy import select, func as sql_func, and_
from rapidfuzz import fuzz

from app.database import engine, Base, async_session
from app.triggers import create_trigger_functions
from app.tasks.fetch_pregame_odds import periodic_fetch_pregame, fetch_and_store_pregame_data
from app.tasks.fetch_live_odds import periodic_fetch_live, fetch_and_store_live_data
from app.tasks.cleanup import periodic_cleanup
from app.tasks.archive_ended_matches import periodic_archive_ended_matches
from app.tasks.run_user_bots import periodic_run_all_bots
from app.config import API_URLS
from datetime import datetime, timedelta, date, timezone
from curl_cffi.requests import AsyncSession
from app.models import SofascoreFt, League, LeagueAlias, Team, TeamAlias, LeagueTeam

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")
logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_trigger_functions(conn)
    tasks = [
        asyncio.create_task(periodic_fetch_live()),
        asyncio.create_task(periodic_fetch_pregame()),
        asyncio.create_task(periodic_cleanup()),
        asyncio.create_task(periodic_archive_ended_matches()),
        asyncio.create_task(periodic_run_all_bots()),
    ]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

app = FastAPI(lifespan=lifespan)

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


async def find_league_id(db_session, league_name: str, country_code: str):
    """
    Find league_id by exact match on league name or league alias.
    When checking league aliases, ensure country_code matches.
    Returns league_id or None.
    """
    # First try exact match on league.name
    result = await db_session.execute(
        select(League.league_id).where(
            and_(
                League.name == league_name,
                League.country_code == country_code
            )
        )
    )
    league = result.first()
    if league:
        logger.debug(f"Found league via exact name match: {league_name} -> league_id {league[0]}")
        return league[0]
    
    # Try exact match on league_alias.alias with country_code verification
    result = await db_session.execute(
        select(LeagueAlias.league_id, League.country_code)
        .join(League, League.league_id == LeagueAlias.league_id)
        .where(LeagueAlias.alias == league_name)
    )
    aliases = result.all()
    
    for alias_league_id, alias_country_code in aliases:
        if alias_country_code == country_code:
            logger.debug(f"Found league via alias match: {league_name} -> league_id {alias_league_id}")
            return alias_league_id
    
    logger.debug(f"No league found for: {league_name} (country_code: {country_code})")
    return None


async def find_team_id(db_session, team_name: str, league_id: int):
    """
    Find team_id by exact match on team name or team alias.
    The team must be associated with the given league_id in league_team table.
    Returns team_id or None.
    """
    # First try exact match on team.name
    result = await db_session.execute(
        select(Team.team_id)
        .join(LeagueTeam, LeagueTeam.team_id == Team.team_id)
        .where(
            and_(
                Team.name == team_name,
                LeagueTeam.league_id == league_id
            )
        )
    )
    team = result.first()
    if team:
        logger.debug(f"Found team via exact name match: {team_name} -> team_id {team[0]} (league_id: {league_id})")
        return team[0]
    
    # Try exact match on team_alias.alias
    result = await db_session.execute(
        select(TeamAlias.team_id)
        .join(LeagueTeam, LeagueTeam.team_id == TeamAlias.team_id)
        .where(
            and_(
                TeamAlias.alias == team_name,
                LeagueTeam.league_id == league_id
            )
        )
    )
    alias = result.first()
    if alias:
        logger.debug(f"Found team via alias match: {team_name} -> team_id {alias[0]} (league_id: {league_id})")
        return alias[0]
    
    logger.debug(f"No team found for: {team_name} in league_id {league_id}")
    return None


async def fetch_sofa_day(session: AsyncSession, date_str: str):
    """Fetches and merges normal and inverse events for a single date."""
    urls = [
        f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}",
        f"https://www.sofascore.com/api/v1/sport/football/scheduled-events/{date_str}/inverse"
    ]
    
    tasks = [session.get(url, impersonate="chrome") for url in urls]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    events = []
    seen_ids = set()
    
    for resp in responses:
        if isinstance(resp, Exception) or resp.status_code != 200:
            continue
        data = resp.json()
        for event in data.get("events", []):
            event_id = event.get("id")
            if event_id not in seen_ids:
                events.append(event)
                seen_ids.add(event_id)
            else:
                logger.debug(f"Duplicate event ID {event_id} found in API response (within same date)")
    return events


@app.get("/fetch-sofascore-range")
async def fetch_sofascore_range(start_date: str, end_date: str):
    """
    Route to fetch SofaScore results for a range and save to sofascore_ft.
    Example: /fetch-sofascore-range?start_date=2026-01-10&end_date=2026-01-15
    """
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Use YYYY-MM-DD format")

    date_list = []
    curr = start
    while curr <= end:
        date_list.append(curr.strftime("%Y-%m-%d"))
        curr += timedelta(days=1)

    all_match_objects = []
    seen_sofascore_ids = set()
    duplicate_count = 0
    skipped_count = 0
    league_not_found_count = 0
    home_team_not_found_count = 0
    away_team_not_found_count = 0
    fully_matched_count = 0
    
    async with AsyncSession() as s:
        # Fetch all days in the range
        for d_str in date_list:
            logger.info(f"Fetching SofaScore data for {d_str}")
            day_events = await fetch_sofa_day(s, d_str)
            logger.info(f"num day_events: {len(day_events)}")
            
            for ev in day_events:
                sofascore_id = ev.get("id")
                
                # Check for duplicates across all fetched data
                if sofascore_id in seen_sofascore_ids:
                    duplicate_count += 1
                    logger.warning(
                        f"DUPLICATE FOUND - ID: {sofascore_id}, "
                        f"Match: {ev.get('homeTeam', {}).get('name')} vs {ev.get('awayTeam', {}).get('name')}, "
                        f"Date: {d_str}"
                    )
                    continue
                
                # Only store matches that have finished (have scores)
                try:
                    home_score = ev.get("homeScore", {}).get("normaltime")
                    away_score = ev.get("awayScore", {}).get("normaltime")
                    
                    # Skip if no scores available
                    if home_score is None or away_score is None:
                        skipped_count += 1
                        logger.debug(f"Skipped match {sofascore_id} - no scores available")
                        continue
                    
                    match_obj = SofascoreFt(
                        sofascore_id=sofascore_id,
                        competition_name=ev.get("tournament", {}).get("name"),
                        category=ev.get("tournament", {}).get("category", {}).get("sport", {}).get("name"),
                        country=ev.get("tournament", {}).get("category", {}).get("name"),
                        country_code=ev.get("tournament", {}).get("category", {}).get("alpha2") or "INT",
                        home_team=ev.get("homeTeam", {}).get("name"),
                        home_score=int(home_score),
                        away_team=ev.get("awayTeam", {}).get("name"),
                        away_score=int(away_score),
                        start_time=datetime.fromtimestamp(ev.get("startTimestamp", 0), timezone.utc).replace(tzinfo=None),
                        league_id=None,
                        home_team_id=None,
                        away_team_id=None
                    )
                    
                    all_match_objects.append(match_obj)
                    seen_sofascore_ids.add(sofascore_id)
                    logger.debug(f"Added match_obj id: {sofascore_id}")

                except Exception as e:
                    logger.error(f"Error processing event {sofascore_id}: {e}")
                    continue
            
            logger.info(f"Total unique matches collected: {len(all_match_objects)}")

    logger.info(
        f"Data collection complete - "
        f"Total matches: {len(all_match_objects)}, "
        f"Duplicates skipped: {duplicate_count}, "
        f"No scores skipped: {skipped_count}"
    )

    # Database operations: check duplicates and match leagues/teams
    async with async_session() as db_session:
        try:
            # Query existing sofascore_ids
            existing_ids_result = await db_session.execute(
                select(SofascoreFt.sofascore_id).where(
                    SofascoreFt.sofascore_id.in_(seen_sofascore_ids)
                )
            )
            existing_ids = {row[0] for row in existing_ids_result.fetchall()}
            
            # Filter out matches that already exist in DB and match leagues/teams
            db_duplicate_count = 0
            matches_to_insert = []
            
            for match in all_match_objects:
                if match.sofascore_id in existing_ids:
                    db_duplicate_count += 1
                    logger.warning(
                        f"DB DUPLICATE FOUND - ID: {match.sofascore_id}, "
                        f"Match: {match.home_team} vs {match.away_team}"
                    )
                    continue
                
                # Try to find league_id
                league_id = await find_league_id(
                    db_session, 
                    match.competition_name, 
                    match.country_code
                )
                
                if league_id is None:
                    league_not_found_count += 1
                    logger.info(
                        f"League not found - sofascore_id: {match.sofascore_id}, "
                        f"league: {match.competition_name}, country_code: {match.country_code}"
                    )
                    # Still insert the match, just without league_id
                    matches_to_insert.append(match)
                    continue
                
                match.league_id = league_id
                
                # Try to find home_team_id (requires league_id)
                home_team_id = await find_team_id(
                    db_session,
                    match.home_team,
                    league_id
                )
                
                if home_team_id is None:
                    home_team_not_found_count += 1
                    logger.info(
                        f"Home team not found - sofascore_id: {match.sofascore_id}, "
                        f"team: {match.home_team}, league_id: {league_id}"
                    )
                else:
                    match.home_team_id = home_team_id
                
                # Try to find away_team_id (requires league_id)
                away_team_id = await find_team_id(
                    db_session,
                    match.away_team,
                    league_id
                )
                
                if away_team_id is None:
                    away_team_not_found_count += 1
                    logger.info(
                        f"Away team not found - sofascore_id: {match.sofascore_id}, "
                        f"team: {match.away_team}, league_id: {league_id}"
                    )
                else:
                    match.away_team_id = away_team_id
                
                # Track fully matched records
                if match.league_id and match.home_team_id and match.away_team_id:
                    fully_matched_count += 1
                    logger.debug(
                        f"Fully matched - sofascore_id: {match.sofascore_id}, "
                        f"league_id: {match.league_id}, home_team_id: {match.home_team_id}, "
                        f"away_team_id: {match.away_team_id}"
                    )
                
                matches_to_insert.append(match)
            
            # Insert only new matches
            if matches_to_insert:
                db_session.add_all(matches_to_insert)
                await db_session.commit()
                logger.info(f"Successfully inserted {len(matches_to_insert)} new matches")
            else:
                logger.info("No new matches to insert")
            
            return {
                "status": "success",
                "matches_fetched": len(all_match_objects),
                "matches_inserted": len(matches_to_insert),
                "duplicates_in_fetch": duplicate_count,
                "duplicates_in_db": db_duplicate_count,
                "skipped_no_scores": skipped_count,
                "matching_stats": {
                    "fully_matched": fully_matched_count,
                    "league_not_found": league_not_found_count,
                    "home_team_not_found": home_team_not_found_count,
                    "away_team_not_found": away_team_not_found_count
                }
            }
            
        except Exception as e:
            await db_session.rollback()
            logger.error(f"DB Error: {e}")
            raise HTTPException(status_code=500, detail=f"Database insertion failed: {str(e)}")
        

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)