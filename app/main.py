# app/main.py
import os
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.database import engine, Base
from app.triggers import create_trigger_functions
from app.tasks.fetch_pregame_odds import periodic_fetch_pregame
from app.tasks.fetch_live_odds import periodic_fetch_live
from app.tasks.cleanup import periodic_cleanup
from app.tasks.archive_ended_matches import periodic_archive_ended_matches
from app.tasks.run_user_bots import periodic_run_all_bots

# Import the new router
from app.routers import sofascore

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
        # asyncio.create_task(periodic_fetch_pregame()),
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

# Register the router
app.include_router(sofascore.router)

@app.get("/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)