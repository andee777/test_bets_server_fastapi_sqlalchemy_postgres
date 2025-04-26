# app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

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

API_URLS = {
    "live": os.getenv("LIVE_URL"),
    "football": os.getenv("FOOTBALL_URL"),
    "basketball": os.getenv("BASKETBALL_URL"),
}