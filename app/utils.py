# app/utils.py
import logging
import httpx
from datetime import datetime

logger = logging.getLogger(__name__)

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