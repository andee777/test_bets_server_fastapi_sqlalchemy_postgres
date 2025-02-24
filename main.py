import os
from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Text, DateTime, String, BigInteger, ForeignKey
from sqlalchemy.dialects.postgresql import insert

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
    __tablename__ = 'matches'
    match_id = Column(BigInteger, primary_key=True, index=True)
    competition_name = Column(Text, index=True)
    category = Column(Text)
    home_team = Column(Text)
    away_team = Column(Text)
    start_time = Column(DateTime)

class Odds(Base):
    __tablename__ = 'odds'
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    match_id = Column(BigInteger, ForeignKey('matches.match_id'), index=True)
    event_status = Column(Text)
    match_time = Column(Text)
    current_score = Column(Text)
    # Separate columns for 1X2 odds
    home_win = Column(String)
    draw = Column(String)
    away_win = Column(String)
    fetched_at = Column(DateTime, default=datetime.utcnow, index=True)

async def fetch_and_store_data(url: str, category: str):
    logger.info(f"--------- periodic_fetch___{category} ---------")

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
        # Prepare match data for bulk upsert
        match_data_list = []
        for match in matches:
            match_data = {
                "match_id": int(match.get("match_id")),
                "competition_name": match.get("competition_name"),
                "category": category,
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

        # Prepare odds data for bulk insert
        odds_data_list = []
        for match in matches:
            # Initialize odds values
            home_win = None
            draw = None
            away_win = None

            # For pre game matches (football and basketball) use direct fields
            if category in ("football", "basketball"):
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
                "match_id": int(match.get("match_id")),
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
        await fetch_and_store_data(LIVE_URL, "live")
        await asyncio.sleep(10)

async def periodic_fetch_others():
    while True:
        await fetch_and_store_data(FOOTBALL_URL, "football")
        await fetch_and_store_data(BASKETBALL_URL, "basketball")
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
    await fetch_and_store_data(LIVE_URL, "live")
    return {"message": "Live odds fetched and stored using SQLAlchemy."}

@app.get("/fetch/football")
async def fetch_football_endpoint():
    await fetch_and_store_data(FOOTBALL_URL, "football")
    return {"message": "Football odds fetched and stored using SQLAlchemy."}

@app.get("/fetch/basketball")
async def fetch_basketball_endpoint():
    await fetch_and_store_data(BASKETBALL_URL, "basketball")
    return {"message": "Basketball odds fetched and stored using SQLAlchemy."}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
