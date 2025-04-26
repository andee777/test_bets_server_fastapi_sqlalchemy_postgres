import asyncio
import logging
from datetime import datetime
from sqlalchemy import select, insert, update, and_, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Match, InitialOdd, LatestOdd, Bet, BetEvent, User

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

async def auto_place_bet_favourite(session: AsyncSession):
    """
    Check live matches for those with match_time > 45 minutes and that have at least one initial odd
    (home_win, draw, or away_win) between 1 and 2, and the corresponding latest odds within the same range.
    For qualifying matches, if there is no prior bot bet for the match, place a bot bet of type 'single'
    for user_id 2 with a fixed stake amount, and update the user's balance accordingly.
    """
    stmt = select(Match).where(Match.live == True)
    result = await session.execute(stmt)
    live_matches = result.scalars().all()
    # logger.info(f"Found {len(live_matches)} live matches.")

    for match in live_matches:
        # Only process matches with match time > 45 minutes (i.e., > 2700 seconds)
        match_seconds = parse_match_time(match.match_time or "00:00")
        if match_seconds > 300:
            continue
        # Check if a bot bet already exists for this match
        subq = select(BetEvent.match_id).join(Bet, BetEvent.bet_id == Bet.bet_id).where(
            and_(
                Bet.bot == True,
                Bet.bot_task.ilike("bet_favourite"),
                BetEvent.match_id == match.match_id
            )
        )
        exists_bet = await session.execute(select(exists(subq)))
        if exists_bet.scalar():
            # logger.info(f"Bot bet already placed for match {match.match_id}, skipping.")
            continue

        # Fetch initial odds and latest odds for the match
        stmt_initial = select(InitialOdd).where(InitialOdd.match_id == match.match_id)
        result_initial = await session.execute(stmt_initial)
        initial_odd = result_initial.scalar_one_or_none()

        stmt_latest = select(LatestOdd).where(LatestOdd.match_id == match.match_id)
        result_latest = await session.execute(stmt_latest)
        latest_odd = result_latest.scalar_one_or_none()

        if not initial_odd or not latest_odd:
            logger.info(f"Missing odds for match {match.match_id}, skipping.")
            continue

        # Condition: check if any initial odd is between 1 and 2 (inclusive of 1, <=2),
        # and also the corresponding latest odd is in that range.
        def is_valid_range(val_init, val_latest):
            return (val_init is not None and val_latest is not None and
                    1 <= val_init <= 1.5 and 1 <= val_latest <= 10)

        selected_type = None
        if is_valid_range(initial_odd.home_win, latest_odd.home_win):
            selected_type = "home"
            odd_value = latest_odd.home_win
        elif is_valid_range(initial_odd.draw, latest_odd.draw):
            selected_type = "draw"
            odd_value = latest_odd.draw
        elif is_valid_range(initial_odd.away_win, latest_odd.away_win):
            selected_type = "away"
            odd_value = latest_odd.away_win
        else:
            # logger.info(f"No qualifying odds for match {match.match_id}. Skipping.")
            continue

        # Place the bet with a fixed stake amount
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
            "bot_task": "bet_favourite"
        }
        stmt_bet = insert(Bet).values(**bet_payload).returning(Bet.bet_id)
        inserted_bet_id = (await session.execute(stmt_bet)).scalar_one()

        # Insert the bet event using the latest odds (for odd_id)
        bet_event_payload = {
            "bet_id": inserted_bet_id,
            "match_id": match.match_id,
            "bet_type": selected_type,
            "odd_id": latest_odd.odds_id,  # Use latest odds id
            "outcome": "pending"
        }
        await session.execute(insert(BetEvent).values(**bet_event_payload))

        # Now update the user's balance: subtract the stake amount
        stmt_update_user = (
            update(User)
            .where(User.user_id == 2)
            .values(balance = User.balance - stake_amount)
        )
        await session.execute(stmt_update_user)

        logger.info(f"\n ----- [FAV] Placed bot bet on {selected_type.upper()} for match {match.match_id} at odd {odd_value} -----")

    await session.commit()

async def periodic_auto_bet_favourite():
    while True:
        # logger.info("Running automated bet placement task.")
        async with async_session() as session:
            try:
                await auto_place_bet_favourite(session)
            except Exception as e:
                logger.error(f"Error in automated bet placement: {e}")
                await session.rollback()
        await asyncio.sleep(60)  # Run every 10 minutes

# Uncomment the following lines to test the script directly.
# if __name__ == '__main__':
#     asyncio.run(periodic_auto_bet())
