import os
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import (
    Column,
    Text,
    DateTime,
    Integer,
    Boolean,
    Float,
    ForeignKey,
    select,
    update,
    text
)
from sqlalchemy.dialects.postgresql import insert

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app")
logging.getLogger("httpx").setLevel(logging.WARNING)

# Database credentials and connection URL
DB_CREDENTIALS = {
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "host": os.getenv("DB_HOST"),
    "port": os.getenv("DB_PORT"),
    "dbname": os.getenv("DB_NAME"),
}
DATABASE_URL = (
    f"postgresql+asyncpg://{DB_CREDENTIALS['user']}:"
    f"{DB_CREDENTIALS['password']}@{DB_CREDENTIALS['host']}:"
    f"{DB_CREDENTIALS['port']}/{DB_CREDENTIALS['dbname']}"
)

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=10,
    max_overflow=20,
    pool_timeout=30,
)

# API Endpoints from environment variables
API_URLS = {
    "live": os.getenv("LIVE_URL"),
    "football": os.getenv("FOOTBALL_URL"),
    "basketball": os.getenv("BASKETBALL_URL"),
}

# Create session maker and Base
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

# Helper: Determine match_time based on event_status
def get_match_time(event_status: str, fetched_match_time: str) -> str:
    if event_status == "Extra time halftime":
        return "105:00"
    elif event_status == "Awaiting extra time":
        return "90:00"
    elif event_status == "Penalties":
        return "120:00"
    elif event_status == "Halftime":
        return "45:00"
    elif event_status == "Not started":
        return "00:00"
    else:
        return fetched_match_time

# Database Models

class Match(Base):
    __tablename__ = 'match'
    match_id = Column(Text, primary_key=True, index=True)
    competition_name = Column(Text, index=True)
    category = Column(Text)
    country = Column(Text)
    home_team = Column(Text)
    away_team = Column(Text)
    event_status = Column(Text)
    live = Column(Boolean, default=False, index=True)
    start_time = Column(DateTime)
    match_time = Column(Text)

class Odds(Base):
    __tablename__ = 'odds'
    odds_id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Text, ForeignKey('match.match_id'), index=True)
    event_status = Column(Text)
    match_time = Column(Text)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    home_win = Column(Float)
    draw = Column(Float)
    away_win = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)

class LatestOdd(Base):
    __tablename__ = 'latest_odd'
    # match_id is the primary key for ON CONFLICT to work
    match_id = Column(Text, primary_key=True)
    # odds_id links to the Odds table
    odds_id = Column(Integer, ForeignKey('odds.odds_id'), nullable=True, index=True)
    event_status = Column(Text)
    match_time = Column(Text)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    home_win = Column(Float)
    draw = Column(Float)
    away_win = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)

class InitialOdd(Base):
    __tablename__ = 'initial_odd'
    # match_id is the primary key for ON CONFLICT to work
    match_id = Column(Text, primary_key=True)
    # odds_id links to the Odds table
    odds_id = Column(Integer, ForeignKey('odds.odds_id'), nullable=True, index=True)
    event_status = Column(Text)
    match_time = Column(Text)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    home_win = Column(Float)
    draw = Column(Float)
    away_win = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)

# --- TRIGGER SETUP FUNCTIONS ---
async def create_trigger_functions(conn):
    trigger_function_sql = """
    CREATE OR REPLACE FUNCTION update_odd_summary() RETURNS trigger AS $$
    BEGIN
      INSERT INTO latest_odd (match_id, odds_id, event_status, match_time, home_score, away_score, home_win, draw, away_win, fetched_at)
      VALUES (NEW.match_id, NEW.odds_id, NEW.event_status, NEW.match_time, NEW.home_score, NEW.away_score, NEW.home_win, NEW.draw, NEW.away_win, NEW.fetched_at)
      ON CONFLICT (match_id) DO UPDATE SET
          odds_id = EXCLUDED.odds_id,
          event_status = EXCLUDED.event_status,
          match_time = EXCLUDED.match_time,
          home_score = EXCLUDED.home_score,
          away_score = EXCLUDED.away_score,
          home_win = EXCLUDED.home_win,
          draw = EXCLUDED.draw,
          away_win = EXCLUDED.away_win,
          fetched_at = EXCLUDED.fetched_at;
    
      INSERT INTO initial_odd (match_id, odds_id, event_status, match_time, home_score, away_score, home_win, draw, away_win, fetched_at)
      VALUES (NEW.match_id, NEW.odds_id, NEW.event_status, NEW.match_time, NEW.home_score, NEW.away_score, NEW.home_win, NEW.draw, NEW.away_win, NEW.fetched_at)
      ON CONFLICT (match_id) DO NOTHING;
    
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """
    await conn.execute(text(trigger_function_sql))
    
    drop_trigger_sql = 'DROP TRIGGER IF EXISTS odd_summary_trigger ON odds;'
    await conn.execute(text(drop_trigger_sql))
    
    create_trigger_sql = """
    CREATE TRIGGER odd_summary_trigger
    AFTER INSERT OR UPDATE ON odds
    FOR EACH ROW
    EXECUTE PROCEDURE update_odd_summary();
    """
    await conn.execute(text(create_trigger_sql))
    logger.info("Trigger function and trigger created successfully.")
# --- END OF TRIGGER SETUP FUNCTIONS ---

# Helper Functions

def parse_score(score_str: str):
    if score_str == "-:-":
        return 0, 0
    if score_str and ":" in score_str:
        try:
            parts = score_str.split(":")
            return int(parts[0]), int(parts[1])
        except Exception as e:
            logger.error(f"Error parsing score '{score_str}': {e}")
    return 0, 0

async def fetch_data(url: str) -> list:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json().get("data", [])
    except Exception as e:
        logger.error(f"Error fetching data from {url}: {e}")
        return []

def event_status_not_live(match: dict, status: str) -> bool:
    return match.get("event_status", "").lower() != status.lower()

def to_double(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0

async def prepare_odds_data(matches: list, fetch_event_status: str) -> list:
    odds_data_list = []
    for match in matches:
        match_id = match.get("match_id")
        if not match_id:
            continue

        fetched_match_time = match.get("match_time")
        event_status = match.get("event_status")
        if fetch_event_status == "pregame":
            match_time = "00:00"
            event_status = "pregame"
        else:
            match_time = get_match_time(event_status, fetched_match_time)

        score_str = match.get("current_score", "")
        home_score, away_score = parse_score(score_str)

        home_win, draw, away_win = None, None, None
        if match.get("home_odd") and event_status_not_live(match, "live"):
            home_win = to_double(match.get("home_odd"))
            draw = to_double(match.get("neutral_odd"))
            away_win = to_double(match.get("away_odd"))
        else:
            odds_array = match.get("odds", [])
            for group in odds_array:
                if group.get("name") == "1X2":
                    for odd in group.get("odds", []):
                        display = odd.get("display")
                        if display == "1":
                            home_win = to_double(odd.get("odd_value"))
                        elif display.upper() == "X":
                            draw = to_double(odd.get("odd_value"))
                        elif display == "2":
                            away_win = to_double(odd.get("odd_value"))
        odds_data = {
            "match_id": str(match_id),
            "event_status": event_status,
            "match_time": match_time,
            "home_score": home_score,
            "away_score": away_score,
            "home_win": home_win,
            "draw": draw,
            "away_win": away_win,
            "fetched_at": datetime.utcnow(),
        }
        odds_data_list.append(odds_data)
    return odds_data_list

# Upsert and Update Functions

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
    result = await session.execute(
        select(Match.match_id, Match.live, Match.event_status).where(Match.category == category)
    )
    db_records = result.fetchall()
    to_update_ids = []
    for match_id, live_flag, db_status in db_records:
        if str(match_id) not in api_match_ids and (db_status or "").lower() != "pregame":
            to_update_ids.append(match_id)
    if to_update_ids:
        logger.info(f"Updating {len(to_update_ids)} matches to not live (live=False).")
        try:
            await session.execute(
                update(Match).where(Match.match_id.in_(to_update_ids)).values(live=False)
            )
        except Exception as e:
            logger.error(f"Error updating missing live matches: {e}")

async def handle_missing_live_matches(session: AsyncSession, category: str):
    result = await session.execute(
        select(Match.match_id, Match.live, Match.event_status).where(Match.category == category)
    )
    to_update_ids = [match_id for match_id, live_flag, db_status in result.fetchall() if live_flag and (db_status or "").lower() != "pregame"]
    if to_update_ids:
        logger.info(f"Updating {len(to_update_ids)} missing live matches to not live (live=False).")
        try:
            await session.execute(
                update(Match).where(Match.match_id.in_(to_update_ids)).values(live=False)
            )
        except Exception as e:
            logger.error(f"Error handling missing live matches: {e}")

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

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_trigger_functions(conn)
    tasks = [
        asyncio.create_task(periodic_fetch_live()),
        asyncio.create_task(periodic_fetch_others())
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

@app.get("/fetch/live")
async def fetch_live_endpoint():
    try:
        await fetch_and_store_data(API_URLS["live"], "football", "live")
        return {"message": "Live odds fetched and stored."}
    except Exception as e:
        logger.error(f"Error in /fetch/live endpoint: {e}")
        raise HTTPException(status_code=500, detail="Error fetching live odds")

@app.get("/fetch/football")
async def fetch_football_endpoint():
    try:
        await fetch_and_store_data(API_URLS["football"], "football", "not started")
        return {"message": "Football odds fetched and stored."}
    except Exception as e:
        logger.error(f"Error in /fetch/football endpoint: {e}")
        raise HTTPException(status_code=500, detail="Error fetching football odds")

@app.get("/fetch/basketball")
async def fetch_basketball_endpoint():
    try:
        await fetch_and_store_data(API_URLS["basketball"], "basketball", "not started")
        return {"message": "Basketball odds fetched and stored."}
    except Exception as e:
        logger.error(f"Error in /fetch/basketball endpoint: {e}")
        raise HTTPException(status_code=500, detail="Error fetching basketball odds")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
