import os
from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Text, DateTime, String, Integer, ForeignKey, update
from sqlalchemy.dialects.postgresql import insert, select, update

import httpx
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Load environment variables from .env file
load_dotenv()

# Database credentials from environment variables
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")

# URLs for fetching data from environment variables
LIVE_URL = os.getenv("LIVE_URL")
FOOTBALL_URL = os.getenv("FOOTBALL_URL")
BASKETBALL_URL = os.getenv("BASKETBALL_URL")

# Create the database URL
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create SQLAlchemy async engine and session maker
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

# Define the Models
class Match(Base):
    __tablename__ = 'Match'
    match_id = Column(Text, primary_key=True, index=True)
    competition_name = Column(Text, index=True)
    category = Column(Text)
    home_team = Column(Text)
    away_team = Column(Text)
    event_status = Column(Text)
    start_time = Column(DateTime)

class Odds(Base):
    __tablename__ = 'Odds'
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Text, ForeignKey('Match.match_id'), index=True)
    event_status = Column(Text)
    match_time = Column(Text)
    current_score = Column(Text)
    # Separate columns for 1X2 odds
    home_win = Column(String)
    draw = Column(String)
    away_win = Column(String)
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)

async def fetch_and_store_data(url: str, category: str, event_status: str):
    logger.info(f"--------- periodic_fetch___{category}___{event_status} ---------")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            matches = data.get("data", [])
    except Exception as e:
        logger.info(f"Error fetching {category} data: {e}")
        return

    async with async_session() as session:
        if len(matches) > 0:
            # Prepare match data for bulk upsert
            match_data_list = []
            for match in matches:
                match_id = match.get("match_id")
                if match_id:
                    match_status = event_status
                    if event_status == 'live':
                        logger.info(f"- live game: {match_id}")
                        # Build a detailed live status string
                        match_status = f'{match.get("event_status")} - {match.get("match_status")} - {match.get("ft_score")}'
                    match_data = {
                        "match_id": f"{match_id}",
                        "competition_name": match.get("competition_name"),
                        "category": category,
                        "event_status": match_status,
                        "home_team": match.get("home_team"),
                        "away_team": match.get("away_team"),
                        "start_time": datetime.fromisoformat(match.get("start_time"))
                            if match.get("start_time") else None,
                    }
                    match_data_list.append(match_data)

            # Upsert matches into the Match table
            stmt = insert(Match)
            set_dict = {
                col.name: getattr(stmt.excluded, col.name)
                for col in Match.__table__.columns if col.name != 'match_id'
            }
            stmt = stmt.values(match_data_list).on_conflict_do_update(
                index_elements=['match_id'],
                set_=set_dict
            )
            await session.execute(stmt)

            # Only for live fetches, perform the comparison/update logic.
            if event_status == 'live':
                # Get the list of match_ids from the API response
                api_match_ids = [match.get("match_id") for match in matches if match.get("match_id")]

                # First, retrieve match_ids from the DB that do NOT have "not started" as event_status.
                result = await session.execute(
                    select(Match.match_id).where(
                        Match.category == category,
                        Match.event_status != "not started"
                    )
                )
                db_match_ids = [row[0] for row in result.fetchall()]

                # Determine which match_ids in the DB are not present in the API response.
                to_update_ids = [mid for mid in db_match_ids if mid not in api_match_ids]

                if to_update_ids:
                    logger.info(f"Updating matches not in API response: {to_update_ids}")
                    update_stmt = update(Match).where(
                        Match.match_id.in_(to_update_ids)
                    ).values(event_status="ended")
                    await session.execute(update_stmt)

            # Prepare odds data for bulk insert
            odds_data_list = []
            for match in matches:
                match_id = match.get("match_id")
                if not match_id:
                    continue  # Skip odds insertion if match_id is missing
                # Initialize odds values
                home_win = None
                draw = None
                away_win = None

                # For pre game matches (football and basketball) use direct fields
                if category in ("football", "basketball") and event_status != 'live':
                    home_win = match.get("home_odd")
                    draw = match.get("neutral_odd")
                    away_win = match.get("away_odd")
                else:
                    # For live matches, process the odds array to find 1X2 odds if available
                    odds_array = match.get("odds", [])
                    for group in odds_array:
                        if group.get("name") == "1X2":
                            for odd in group.get("odds", []):
                                display = odd.get("display")
                                if display == "1":
                                    home_win = odd.get("odd_value")
                                elif display.upper() == "X":
                                    draw = odd.get("odd_value")
                                elif display == "2":
                                    away_win = odd.get("odd_value")

                odds_data = {
                    "match_id": f"{match_id}",
                    "event_status": match.get("event_status"),
                    "match_time": match.get("match_time"),
                    "current_score": match.get("current_score"),
                    "home_win": home_win,
                    "draw": draw,
                    "away_win": away_win,
                    "fetched_at": datetime.utcnow(),
                }
                odds_data_list.append(odds_data)

            # Insert odds data into the Odds table
            await session.execute(insert(Odds).values(odds_data_list))

            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.info(f"Error saving {category} data: {e}")

async def periodic_fetch_live():
    while True:
        await fetch_and_store_data(LIVE_URL, "football", "live")
        await asyncio.sleep(10)

async def periodic_fetch_others():
    while True:
        await fetch_and_store_data(FOOTBALL_URL, "football", "not started")
        await fetch_and_store_data(BASKETBALL_URL, "basketball", "not started")
        await asyncio.sleep(300)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    background_task_live = asyncio.create_task(periodic_fetch_live())
    background_task_others = asyncio.create_task(periodic_fetch_others())
    yield
    background_task_live.cancel()
    background_task_others.cancel()
    try:
        await background_task_live
    except asyncio.CancelledError:
        pass
    try:
        await background_task_others
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan)

@app.get("/fetch/live")
async def fetch_live_endpoint():
    await fetch_and_store_data(LIVE_URL, "football", "live")
    return {"message": "Live odds fetched and stored using SQLAlchemy."}

@app.get("/fetch/football")
async def fetch_football_endpoint():
    await fetch_and_store_data(FOOTBALL_URL, "football", "not started")
    return {"message": "Football odds fetched and stored using SQLAlchemy."}

@app.get("/fetch/basketball")
async def fetch_basketball_endpoint():
    await fetch_and_store_data(BASKETBALL_URL, "basketball", "not started")
    return {"message": "Basketball odds fetched and stored using SQLAlchemy."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
