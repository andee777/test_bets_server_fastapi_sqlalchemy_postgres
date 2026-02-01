import logging
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from sqlalchemy import select, and_, distinct, func
from curl_cffi.requests import AsyncSession as CurlSession

from app.database import async_session
from app.models import SofascoreFt, League, LeagueAlias, Team, TeamAlias, LeagueTeam, EndedMatch

# Configure logging for this module
logger = logging.getLogger("app.routers.sofascore")

router = APIRouter(
    prefix="/sofascore",
    tags=["sofascore"]
)

# --- Helper: Database Lookups ---

async def get_relevant_country_codes_for_date(db_session, date_str: str):
    """
    Queries the database to find all unique country codes associated with 
    leagues present in the ended_matches table for a SINGLE date.
    
    Timezone Logic:
    - Input date is UTC.
    - DB EndedMatch.start_time is Kenyan Time (UTC+3).
    - We convert the UTC date to Kenyan Time limits to query the DB efficiently.
    """
    try:
        # Parse UTC date (midnight)
        start_utc = datetime.strptime(date_str, "%Y-%m-%d")
        # End of day is the next day 00:00:00 as the exclusive upper bound
        end_utc_limit = start_utc + timedelta(days=1)
        
        # Shift to Kenyan Time (UTC+3)
        kenya_offset = timedelta(hours=3)
        start_db_time = start_utc + kenya_offset
        end_db_time = end_utc_limit + kenya_offset
        
        logger.debug(f"Filtering EndedMatches for {date_str} between {start_db_time} and {end_db_time} (Kenyan Time)")

        result = await db_session.execute(
            select(distinct(League.country_code))
            .join(EndedMatch, EndedMatch.competition_name == League.name)
            .where(
                and_(
                    League.country_code.isnot(None),
                    EndedMatch.start_time >= start_db_time,
                    EndedMatch.start_time < end_db_time
                )
            )
        )
        return {row[0] for row in result.fetchall()}
        
    except ValueError:
        logger.error(f"Invalid date format in get_relevant_country_codes_for_date: {date_str}")
        return set()

async def find_league_id(db_session, league_name: str, country_code: str):
    """Find league_id by exact match on league name or league alias."""
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
        return league[0]
    
    # Try exact match on league_alias.alias
    result = await db_session.execute(
        select(LeagueAlias.league_id, League.country_code)
        .join(League, League.league_id == LeagueAlias.league_id)
        .where(LeagueAlias.alias == league_name)
    )
    aliases = result.all()
    
    for alias_league_id, alias_country_code in aliases:
        if alias_country_code == country_code:
            return alias_league_id
    
    return None

async def find_team_id(db_session, team_name: str, league_id: int):
    """Find team_id by exact match on name or alias within a league (case-insensitive & trimmed)."""
    
    # 1. Pre-process the input name (Trim whitespace and convert to Uppercase)
    clean_name = team_name.strip().upper()

    # First try match on Team.name
    result = await db_session.execute(
        select(Team.team_id)
        .join(LeagueTeam, LeagueTeam.team_id == Team.team_id)
        .where(
            and_(
                # Trim and Upper the DB column to match the cleaned input
                func.upper(func.trim(Team.name)) == clean_name,
                LeagueTeam.league_id == league_id
            )
        )
    )
    team = result.first()
    if league_id == 276 : print(f'---------{team_name} - {team}')
    if team:
        return team[0]
    
    # Try match on TeamAlias.alias
    result = await db_session.execute(
        select(TeamAlias.team_id)
        .join(LeagueTeam, LeagueTeam.team_id == TeamAlias.team_id)
        .where(
            and_(
                # Trim and Upper the DB column here as well
                func.upper(func.trim(TeamAlias.alias)) == clean_name,
                LeagueTeam.league_id == league_id
            )
        )
    )
    alias = result.first()
    if league_id == 276 : print(f'---------{team_name} - {alias}')
    if alias:
        return alias[0]
    
    return None


# --- Helper: SofaScore API ---

# Cache for category mapping to avoid repeated API calls
_category_cache = None

async def fetch_sofascore_category_map(session: CurlSession, relevant_codes: set):
    """
    Fetches the list of all categories from SofaScore and filters them 
    to return a list of Category IDs that match our database's country codes.
    Uses caching to avoid repeated API calls.
    """
    global _category_cache
    
    # Fetch categories only once
    if _category_cache is None:
        url = "https://www.sofascore.com/api/v1/sport/football/categories"
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Referer': 'https://www.sofascore.com/',
            'Origin': 'https://www.sofascore.com',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
        }
        
        response = await session.get(url, headers=headers, impersonate="chrome")
        
        if response.status_code != 200:
            logger.error(f"Failed to fetch categories: {response.status_code}")
            return []

        data = response.json()
        _category_cache = data.get("categories", [])
        logger.info(f"Fetched and cached {len(_category_cache)} SofaScore categories")
    
    # Map relevant codes to category IDs
    target_ids = []
    copy_codes = relevant_codes.copy()
    
    for cat in _category_cache:
        alpha2 = cat.get("alpha2")
        cat_id = cat.get("id")
        
        if not alpha2 and "INT" in relevant_codes:
            target_ids.append(cat_id)
            copy_codes = copy_codes - {'INT'}
        # Check if this category's alpha2 code is in our relevant list
        if alpha2 and alpha2 in relevant_codes:
            target_ids.append(cat_id)
            copy_codes = copy_codes - {alpha2}
    
    if copy_codes:
        logger.debug(f"Unmapped codes for this date: {copy_codes}")
    
    return target_ids

async def fetch_events_for_category_date(session: CurlSession, category_id: int, date_str: str, retry_count=0, max_retries=3):
    """Fetches events for a specific category ID and date with retry logic."""
    url = f"https://www.sofascore.com/api/v1/category/{category_id}/scheduled-events/{date_str}"
    
    # Add realistic headers
    headers = {
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.sofascore.com/',
        'Origin': 'https://www.sofascore.com',
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
    }
    
    try:
        # Add random delay between requests (0.5-2 seconds)
        await asyncio.sleep(0.5 + (hash(f"{category_id}{date_str}") % 150) / 100)
        
        resp = await session.get(url, headers=headers, impersonate="chrome")
        
        if resp.status_code == 200:
            return resp.json().get("events", [])
        elif resp.status_code == 404:
            return []
        elif resp.status_code == 403 and retry_count < max_retries:
            # Exponential backoff on 403
            wait_time = (2 ** retry_count) * 2
            logger.warning(f"403 error for cat {category_id} date {date_str}, retrying in {wait_time}s (attempt {retry_count + 1}/{max_retries})")
            await asyncio.sleep(wait_time)
            return await fetch_events_for_category_date(session, category_id, date_str, retry_count + 1, max_retries)
        else:
            logger.warning(f"Error fetching cat {category_id} date {date_str}: {resp.status_code}")
            return []
    except Exception as e:
        logger.error(f"Exception fetching cat {category_id} date {date_str}: {e}")
        return []


# --- Main Route ---

@router.get("/fetch-range")
async def fetch_sofascore_range(start_date: str, end_date: str):
    """
    1. Loop through each date in the range
    2. For each date, get relevant country codes from DB
    3. Get SofaScore category IDs for those countries
    4. Fetch events for that date only
    5. Save to DB
    """
    # 1. Parse Dates for Loop
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

    # Global metrics across all dates
    total_matches_fetched = 0
    total_matches_inserted = 0
    total_categories_fetched = 0
    dates_with_no_matches = 0
    total_duplicate_count = 0
    total_skipped_count = 0
    total_league_not_found = 0
    total_home_team_not_found = 0
    total_away_team_not_found = 0
    total_fully_matched = 0
    
    # Track seen IDs across all dates to avoid duplicates
    global_seen_sofascore_ids = set()

    async with CurlSession() as s:
        # Process each date separately
        for d_str in date_list:
            logger.info(f"Processing date: {d_str}")
            
            # Get country codes specific to this date
            async with async_session() as db_session:
                relevant_country_codes = await get_relevant_country_codes_for_date(db_session, d_str)
            
            if not relevant_country_codes:
                logger.info(f"No ended matches found for {d_str}, skipping SofaScore fetch")
                dates_with_no_matches += 1
                continue
            
            logger.info(f"Found {len(relevant_country_codes)} country codes for {d_str}: {relevant_country_codes}")
            
            # Get SofaScore Category IDs for this date's countries
            target_category_ids = await fetch_sofascore_category_map(s, relevant_country_codes)
            
            if not target_category_ids:
                logger.warning(f"Could not map country codes to SofaScore categories for {d_str}")
                continue
            
            total_categories_fetched += len(target_category_ids)
            logger.info(f"Fetching {len(target_category_ids)} categories for {d_str}")
            
            # Parse the target date
            try:
                target_date = datetime.strptime(d_str, "%Y-%m-%d").date()
            except ValueError:
                logger.error(f"Invalid date format: {d_str}")
                continue
            
            start_of_day = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
            end_of_day = start_of_day.replace(hour=23, minute=59, second=59, microsecond=999999)

            # Instead of concurrent requests, do sequential with rate limiting
            day_events_flat = []
            for cat_id in target_category_ids:
                events = await fetch_events_for_category_date(s, cat_id, d_str)
                day_events_flat.extend(events)
            
            logger.info(f"  -> Found {len(day_events_flat)} events for {d_str}")
            
            # Process events for this specific date
            date_match_objects = []
            date_seen_ids = set()
            date_duplicate_count = 0
            date_skipped_count = 0

            for ev in day_events_flat:
                sofascore_id = ev.get("id")
                
                start_ts = ev.get("startTimestamp")
                if not isinstance(start_ts, (int, float)) or start_ts <= 0:
                    continue
                    
                start_time = datetime.fromtimestamp(start_ts, tz=timezone.utc)
                
                if not (start_of_day <= start_time <= end_of_day):
                    continue

                country = ev.get("tournament", {}).get("category", {}).get("name")
                country_code = ev.get("tournament", {}).get("category", {}).get("alpha2") or "INT"

                # Check against both date-specific and global seen IDs
                if sofascore_id in date_seen_ids or sofascore_id in global_seen_sofascore_ids:
                    date_duplicate_count += 1
                    continue

                try:
                    home_score = ev.get("homeScore", {}).get("normaltime")
                    away_score = ev.get("awayScore", {}).get("normaltime")
                    
                    # if home_score is None or away_score is None:
                    #     date_skipped_count += 1
                    #     continue

                    if 'INT' in country_code:
                        country = "International"
                    
                    country = country.replace('Amateur', '').strip()
                    
                    match_obj = SofascoreFt(
                        sofascore_id=sofascore_id,
                        competition_name=ev.get("tournament", {}).get("name"),
                        category=ev.get("tournament", {}).get("category", {}).get("sport", {}).get("name"),
                        country=country,
                        country_code=country_code,
                        home_team=ev.get("homeTeam", {}).get("name"),
                        home_score=int(home_score) if home_score is not None else None,
                        away_team=ev.get("awayTeam", {}).get("name"),
                        away_score=int(away_score) if away_score is not None else None,
                        start_time=start_time.replace(tzinfo=None),
                        league_id=None,
                        home_team_id=None,
                        away_team_id=None,
                        event_status= ev.get("status", {}).get("type")
                    )
                    
                    date_match_objects.append(match_obj)
                    date_seen_ids.add(sofascore_id)
                except Exception as e:
                    logger.error(f"Error parsing event {sofascore_id}: {e}")
                    continue
            
            logger.info(f"  -> Parsed {len(date_match_objects)} unique matches for {d_str}")
            
            # Update global metrics
            total_duplicate_count += date_duplicate_count
            total_skipped_count += date_skipped_count
            
            # Insert this date's data into the database
            if date_match_objects:
                async with async_session() as db_session:
                    try:
                        # Check DB duplicates for this date's matches
                        existing_ids_result = await db_session.execute(
                            select(SofascoreFt.sofascore_id).where(
                                SofascoreFt.sofascore_id.in_(date_seen_ids)
                            )
                        )
                        existing_ids = {row[0] for row in existing_ids_result.fetchall()}
                        
                        matches_to_insert = []
                        date_db_duplicate_count = 0
                        date_league_not_found = 0
                        date_home_team_not_found = 0
                        date_away_team_not_found = 0
                        date_fully_matched = 0
                        
                        for match in date_match_objects:
                            if match.sofascore_id in existing_ids:
                                date_db_duplicate_count += 1
                                continue
                            
                            # Mapping Logic
                            league_id = await find_league_id(db_session, match.competition_name, match.country_code)
                            
                            if league_id is None:
                                date_league_not_found += 1
                                matches_to_insert.append(match)
                                continue
                            
                            match.league_id = league_id
                            
                            home_team_id = await find_team_id(db_session, match.home_team, league_id)
                            if home_team_id:
                                match.home_team_id = home_team_id
                            else:
                                date_home_team_not_found += 1
                            
                            away_team_id = await find_team_id(db_session, match.away_team, league_id)
                            if away_team_id:
                                match.away_team_id = away_team_id
                            else:
                                date_away_team_not_found += 1
                            
                            if match.league_id and match.home_team_id and match.away_team_id:
                                date_fully_matched += 1
                            
                            matches_to_insert.append(match)
                        
                        if matches_to_insert:
                            db_session.add_all(matches_to_insert)
                            await db_session.commit()
                            logger.info(f"  -> Inserted {len(matches_to_insert)} matches for {d_str} (duplicates: {date_db_duplicate_count})")
                            
                            # Add to global seen IDs after successful insertion
                            global_seen_sofascore_ids.update(date_seen_ids)
                            
                            # Update global metrics
                            total_matches_inserted += len(matches_to_insert)
                            total_duplicate_count += date_db_duplicate_count
                            total_league_not_found += date_league_not_found
                            total_home_team_not_found += date_home_team_not_found
                            total_away_team_not_found += date_away_team_not_found
                            total_fully_matched += date_fully_matched
                        else:
                            logger.info(f"  -> No new matches to insert for {d_str} (all duplicates)")
                            total_duplicate_count += date_db_duplicate_count

                    except Exception as e:
                        await db_session.rollback()
                        logger.error(f"DB Transaction Error for {d_str}: {e}")
                        # Continue to next date even if this one fails
                        continue
            else:
                logger.info(f"  -> No matches to process for {d_str}")
            
            total_matches_fetched += len(date_match_objects)

    logger.info(f"Data collection complete. Total matches fetched: {total_matches_fetched}, inserted: {total_matches_inserted}")
    
    return {
        "status": "success",
        "date_range": f"{start_date} to {end_date}",
        "dates_processed": len(date_list),
        "dates_with_no_matches": dates_with_no_matches,
        "total_categories_fetched": total_categories_fetched,
        "matches_fetched": total_matches_fetched,
        "matches_inserted": total_matches_inserted,
        "stats": {
            "duplicates_skipped": total_duplicate_count,
            "fully_matched": total_fully_matched,
            "league_missing": total_league_not_found,
            "teams_missing": total_home_team_not_found + total_away_team_not_found
        }
    }