# app/tasks/run_bots.py
import asyncio
from sqlalchemy import select, and_, exists
from app.database import async_session
from app.models import Match, InitialOdd, LatestOdd, Bet, BetEvent, User, Bot
from app.tasks.process_user_bots_conditions import process_bot_conditions
from app.tasks.process_user_bots_actions import process_bot_action
from sqlalchemy.ext.asyncio import AsyncSession

import logging
logger = logging.getLogger(__name__)

async def run_all_bots_once(session: AsyncSession):
    bots = (await session.execute(select(Bot).where(Bot.active == True))).scalars().all()
    # logger.info(f'\n\n************************ {len(bots)} user bots currently active ************************\n')
    for bot in bots:
        stmt = select(Match).where(Match.live == True)
        result = await session.execute(stmt)
        live_matches = result.scalars().all()
        # logger.info(f"Found {len(live_matches)} live matches for late-game betting.")

        for match in live_matches:
            # print(f'bot{bot.bot_id}, match{match.match_id}', bot.conditions)

            # Check if a bot bet already exists for this match
            subq = select(BetEvent.match_id).join(Bet, BetEvent.bet_id == Bet.bet_id).where(
                and_(
                    Bet.bot == True,
                    Bet.bot_task.ilike(bot.name),
                    BetEvent.match_id == match.match_id
                )
            )
            exists_bet = await session.execute(select(exists(subq)))
            if exists_bet.scalar():
                # logger.info(f"Bot bet already placed for match {match.match_id}, skipping.")
                continue

            result = await session.execute(select(InitialOdd).where(InitialOdd.match_id == match.match_id))
            initial_odd = result.scalar_one_or_none()

            result = await session.execute(select(LatestOdd).where(LatestOdd.match_id == match.match_id))
            latest_odd = result.scalar_one_or_none()
            
            result = await process_bot_conditions(session, bot.conditions or [], match, initial_odd, latest_odd)
            
            if result:
                # ✅ Conditions met → perform bot action (place bet, etc.)
                # logger.info(f"\n---------- Bot {bot.name} triggered for match {match.match_id}\n\t--- bot_conditions: {bot.conditions}")
                await process_bot_action(session, bot, match, initial_odd, latest_odd)
            # else:
            #     print('-----------not meet reqs\n\n')
    # logger.info(f'\n************* {len(bots)} user bots finished checking {len(live_matches)} live matches **********\n\n')
    

async def periodic_run_all_bots():
    while True:
        # logger.info("Running automated bet placement task.")
        async with async_session() as session:
            try:
                await run_all_bots_once(session)
            except Exception as e:
                logger.error(f"Error in automated bet placement: {e}")
                await session.rollback()
        await asyncio.sleep(60)  # Run every 10 minutes