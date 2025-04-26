import asyncio
import logging
from datetime import datetime
from sqlalchemy import select, insert, update, and_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Match, LatestOdd, Bet, BetEvent, User

logger = logging.getLogger(__name__)

def parse_match_time(match_time_str: str) -> int:
    """
    Convert a match_time formatted as "mm:ss" into total seconds.
    """
    try:
        minutes, seconds = map(int, match_time_str.split(":"))
        return minutes * 60 + seconds
    except Exception:
        return 0  # Default if parsing fails

async def auto_place_bets_late_game(session: AsyncSession):
    # Query for live matches
    stmt = select(Match).where(Match.live == True)
    result = await session.execute(stmt)
    live_matches = result.scalars().all()
    # logger.info(f"Found {len(live_matches)} live matches for late-game betting.")

    for match in live_matches:
        # Convert match_time (mm:ss) into seconds and ensure >80 minutes (4800 sec)
        match_seconds = parse_match_time(match.match_time or "00:00")
        if match_seconds <= 4800:
            continue

        # Check if a bot bet already exists for this match (for user_id 2)
        subq = select(BetEvent.match_id).join(Bet, BetEvent.bet_id == Bet.bet_id).where(
            and_(
                Bet.bot == True,
                Bet.user_id == 2,
                Bet.bot_task.ilike("bet_favourite_late_matches"),
                BetEvent.match_id == match.match_id
            )
        )
        exists_bet = await session.execute(select(exists(subq)))
        if exists_bet.scalar():
            # logger.info(f"[80+] Bot bet already placed for match {match.match_id}, skipping.")
            continue

        # Get latest odds for the match
        stmt_latest = select(LatestOdd).where(LatestOdd.match_id == match.match_id)
        result_latest = await session.execute(stmt_latest)
        latest_odd = result_latest.scalar_one_or_none()

        if not latest_odd:
            logger.info(f"Missing latest odds for match {match.match_id}, skipping.")
            continue

        # Condition: we check if any latest odd is between 1 and 1.5 (inclusive of 1, ≤1.5)
        def is_valid(val):
            return val is not None and 1 <= val <= 1.5

        if is_valid(latest_odd.home_win):
            bet_type = "home"
            odd_value = latest_odd.home_win
        elif is_valid(latest_odd.draw):
            bet_type = "draw"
            odd_value = latest_odd.draw
        elif is_valid(latest_odd.away_win):
            bet_type = "away"
            odd_value = latest_odd.away_win
        else:
            # logger.info(f"[80+] No qualifying low odds for match {match.match_id}. Skipping.")
            continue

        # Place the bot bet
        stake_amount = 10
        bet_payload = {
            "user_id": 2,
            "type": "single",
            "amount": stake_amount,
            "expected_win": stake_amount * odd_value,
            "outcome": "pending",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "bot": True,
            "bot_task": "bet_favourite_late_matches"
        }
        stmt_bet = insert(Bet).values(**bet_payload).returning(Bet.bet_id)
        inserted_bet_id = (await session.execute(stmt_bet)).scalar_one()

        # Insert corresponding bet event (use the latest odd's odds_id)
        bet_event_payload = {
            "bet_id": inserted_bet_id,
            "match_id": match.match_id,
            "bet_type": bet_type,
            "odd_id": latest_odd.odds_id,
            "outcome": "pending"
        }
        await session.execute(insert(BetEvent).values(**bet_event_payload))

        # Update user's balance (subtract stake_amount)
        stmt_update_user = (
            update(User)
            .where(User.user_id == 2)
            .values(balance = User.balance - stake_amount)
        )
        await session.execute(stmt_update_user)

        logger.info(f"\n ----- [80+] Placed bot bet on {bet_type.upper()} for match {match.match_id} with odd {odd_value} -----")

    await session.commit()

async def periodic_auto_bet_late_game():
    while True:
        # logger.info("Running 80+ minute auto-bet task.")
        async with async_session() as session:
            try:
                await auto_place_bets_late_game(session)
            except Exception as e:
                logger.error(f"Error in 80+ min bet placement: {e}")
                await session.rollback()
        await asyncio.sleep(60)             # Run the task every 60 seconds
