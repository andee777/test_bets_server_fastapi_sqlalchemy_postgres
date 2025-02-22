import os
from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import Column, Integer, Text, JSON, DateTime
import httpx
import asyncio
from datetime import datetime
from contextlib import asynccontextmanager

# Load environment variables from .env file
load_dotenv()

# Database credentials from environment variables
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
CLOUD_SQL_INSTANCE = os.getenv("CLOUD_SQL_INSTANCE")

# URLs for fetching data from environment variables
LIVE_URL = os.getenv("LIVE_URL")
FOOTBALL_URL = os.getenv("FOOTBALL_URL")
BASKETBALL_URL = os.getenv("BASKETBALL_URL")

# Create the database URL
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Create SQLAlchemy async engine and session maker
engine = create_async_engine(DATABASE_URL, echo=True)
async_session = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
Base = declarative_base()

# --------------------------
# Define the Models
# --------------------------

class LiveMatch(Base):
    __tablename__ = 'live_matches'
    id = Column(Integer, primary_key=True, index=True)
    competition_name = Column(Text)
    category = Column(Text)
    home_team = Column(Text)
    away_team = Column(Text)
    event_status = Column(Text)
    match_time = Column(Text)
    current_score = Column(Text)
    odds = Column(JSON)
    fetched_at = Column(DateTime, default=datetime.utcnow)

class FootballMatch(Base):
    __tablename__ = 'football_matches'
    id = Column(Integer, primary_key=True, index=True)
    start_time = Column(DateTime, nullable=True)
    competition_name = Column(Text)
    category = Column(Text)
    home_team = Column(Text)
    away_team = Column(Text)
    odds = Column(JSON)
    fetched_at = Column(DateTime, default=datetime.utcnow)

class BasketballMatch(Base):
    __tablename__ = 'basketball_matches'
    id = Column(Integer, primary_key=True, index=True)
    start_time = Column(DateTime, nullable=True)
    competition_name = Column(Text)
    category = Column(Text)
    home_team = Column(Text)
    away_team = Column(Text)
    odds = Column(JSON)
    fetched_at = Column(DateTime, default=datetime.utcnow)

# --------------------------
# Fetch and Store Functions
# --------------------------

async def fetch_and_store_live():
    url = LIVE_URL
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            matches = data.get("data", [])
    except Exception as e:
        print(f"Error fetching live data: {e}")
        return

    async with async_session() as session:
        for match in matches:
            live_match = LiveMatch(
                competition_name = match.get("competition_name"),
                category = match.get("category"),
                home_team = match.get("home_team"),
                away_team = match.get("away_team"),
                event_status = match.get("event_status"),
                match_time = match.get("match_time"),
                current_score = match.get("current_score"),
                odds = match.get("odds"),
                fetched_at = datetime.utcnow()
            )
            session.add(live_match)
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"Error saving live data: {e}")

async def fetch_and_store_football():
    url = FOOTBALL_URL
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            matches = data.get("data", [])
    except Exception as e:
        print(f"Error fetching football data: {e}")
        return

    async with async_session() as session:
        for match in matches:
            try:
                start_time = datetime.fromisoformat(match.get("start_time"))
            except Exception:
                start_time = None

            football_match = FootballMatch(
                start_time = start_time,
                competition_name = match.get("competition_name"),
                category = match.get("category"),
                home_team = match.get("home_team"),
                away_team = match.get("away_team"),
                odds = match.get("odds"),
                fetched_at = datetime.utcnow()
            )
            session.add(football_match)
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"Error saving football data: {e}")

async def fetch_and_store_basketball():
    url = BASKETBALL_URL
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            matches = data.get("data", [])
    except Exception as e:
        print(f"Error fetching basketball data: {e}")
        return

    async with async_session() as session:
        for match in matches:
            try:
                start_time = datetime.fromisoformat(match.get("start_time"))
            except Exception:
                start_time = None

            basketball_match = BasketballMatch(
                start_time = start_time,
                competition_name = match.get("competition_name"),
                category = match.get("category"),
                home_team = match.get("home_team"),
                away_team = match.get("away_team"),
                odds = match.get("odds"),
                fetched_at = datetime.utcnow()
            )
            session.add(basketball_match)
        try:
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"Error saving basketball data: {e}")

# --------------------------
# Lifespan Event Handler
# --------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    background_task = asyncio.create_task(periodic_fetch())
    yield
    background_task.cancel()
    try:
        await background_task
    except asyncio.CancelledError:
        pass

async def periodic_fetch():
    while True:
        await fetch_and_store_live()
        await fetch_and_store_football()
        await fetch_and_store_basketball()
        await asyncio.sleep(10)

# Create the FastAPI app with the lifespan handler
app = FastAPI(lifespan=lifespan)

# --------------------------
# API Endpoints
# --------------------------

@app.get("/fetch/live")
async def fetch_live_endpoint():
    await fetch_and_store_live()
    return {"message": "Live odds fetched and stored using SQLAlchemy."}

@app.get("/fetch/football")
async def fetch_football_endpoint():
    await fetch_and_store_football()
    return {"message": "Football odds fetched and stored using SQLAlchemy."}

@app.get("/fetch/basketball")
async def fetch_basketball_endpoint():
    await fetch_and_store_basketball()
    return {"message": "Basketball odds fetched and stored using SQLAlchemy."}
