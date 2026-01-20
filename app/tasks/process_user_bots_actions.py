from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from app.models import InitialOdd, LatestOdd, Match, Bet, BetEvent, User, Bot
from sqlalchemy import select, insert, update

import logging
logger = logging.getLogger(__name__)

async def process_bot_action(session: AsyncSession, bot: Bot, match: Match, initial_odd: InitialOdd, latest_odd: LatestOdd):
    """
    Processes a bot's action and places a bet accordingly.

    Args:
        session (AsyncSession): SQLAlchemy async session.
        bot: , 
        match: , 
        initial_odd: , 
        latest_odd: 

    Returns:
        dict: Details about the placed bet.
    """

    action = bot.action

    home_team = match.home_team
    away_team = match.away_team

    initial_odds_home = initial_odd.home_win
    initial_odds_away = initial_odd.away_win
    initial_odds_draw = initial_odd.draw

    current_odds_home = latest_odd.home_win
    current_odds_away = latest_odd.away_win
    current_odds_draw = latest_odd.draw

    team_to_bet_on = None
    odds_to_use = None

    # Helper: determine favourite vs outsider
    def get_favourite_and_outsider(current: bool = True):
        """
        Determines the favourite and outsider based on odds, including draw odds.
        Returns a tuple: (favourite_side, outsider_side)
        where each is one of 'home', 'draw', or 'away'.
        """

        odds_map = {
            "home": current_odds_home if current else initial_odds_home,
            "draw": current_odds_draw if current else initial_odds_draw,
            "away": current_odds_away if current else initial_odds_away,
        }

        # Filter out None or invalid odds
        odds_map = {k: v for k, v in odds_map.items() if v is not None}

        if not odds_map:
            return None, None

        # Sort odds: lower = favourite, higher = outsider
        sorted_odds = sorted(odds_map.items(), key=lambda x: x[1])

        favourite_side = sorted_odds[0][0]
        outsider_side = sorted_odds[-1][0]
        # print(favourite)
        return favourite_side, outsider_side


    def get_selected_team(bot_conditions: dict) -> str | None:
        """
        Determines if the selected team from bot.conditions corresponds
        to the home or away team in the given match.
        Returns 'home', 'away', or None if not found.
        Example bot_conditions:
            {"team": {"equals": "Manchester United"}}
        """
        if not bot_conditions or not isinstance(bot_conditions, dict):
            return None

        team_condition = bot_conditions.get("team")
        if not team_condition:
            return None

        # Extract the team name from the condition dict (e.g., {"equals": "Man United"})
        _, team_name = next(iter(team_condition.items()), (None, None))
        if not team_name:
            return None

        home_team = (match.home_team or "").lower()
        away_team = (match.away_team or "").lower()
        team_name = team_name.lower()

        if team_name == home_team:
            return "home"
        elif team_name == away_team:
            return "away"
        return None


    # --- Determine team_to_bet_on and odds_to_use based on action ---
    if action == "place_bet_home":
        team_to_bet_on = 'home'
        odds_to_use = current_odds_home

    elif action == "place_bet_away":
        team_to_bet_on = 'away'
        odds_to_use = current_odds_away

    elif action == "place_bet_draw":
        team_to_bet_on = "draw"
        odds_to_use = current_odds_draw

    elif action in ["place_bet_live_favourite", "place_bet_live_outsider"]:
        favourite, outsider = get_favourite_and_outsider(current=True)
        team_to_bet_on = favourite if action == "place_bet_live_favourite" else outsider

        if team_to_bet_on == "home":
            odds_to_use = current_odds_home
        elif team_to_bet_on == "away":
            odds_to_use = current_odds_away
        elif team_to_bet_on == "draw":
            odds_to_use = current_odds_draw
        else:
            odds_to_use = None
        # print("----- live fav/outsider", team_to_bet_on, odds_to_use)

    elif action in ["place_bet_initial_favourite", "place_bet_initial_outsider"]:
        favourite, outsider = get_favourite_and_outsider(current=False)
        team_to_bet_on = favourite if action == "place_bet_initial_favourite" else outsider

        if team_to_bet_on == "home":
            odds_to_use = initial_odds_home
        elif team_to_bet_on == "away":
            odds_to_use = initial_odds_away
        elif team_to_bet_on == "draw":
            odds_to_use = initial_odds_draw
        else:
            odds_to_use = None

    elif action in ("place_bet_selected_team", "place_bet_not_selected_team") :
        selected_side = get_selected_team(bot.conditions)
        # Flip if it's the "not_selected" action
        team_to_bet_on = (
            "away" if action == "place_bet_not_selected_team" and selected_side == "home"
            else "home" if action == "place_bet_not_selected_team" and selected_side == "away"
            else selected_side
        )

        odds_to_use = current_odds_home if team_to_bet_on == "home" else current_odds_away
    # print("------------ ", team_to_bet_on, odds_to_use, team_to_bet_on and odds_to_use)
    # --- Place the bet if valid ---
    if team_to_bet_on and odds_to_use:
        # Place the bet with a fixed stake amount
        stake_amount = bot.bet_amount
        bet_payload = {
            "user_id": bot.user_id,
            "type": "single",
            "amount": stake_amount,
            "expected_win": stake_amount * odds_to_use,
            "outcome": "pending",
            "created_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "updated_at": datetime.now(timezone.utc).replace(tzinfo=None),
            "bot": True,
            "bot_task": bot.name,
            "bot_id": bot.bot_id,
        }
        stmt_bet = insert(Bet).values(**bet_payload).returning(Bet.bet_id)
        inserted_bet_id = (await session.execute(stmt_bet)).scalar_one()

        # Insert the bet event using the latest odds (for odd_id)
        bet_event_payload = {
            "bet_id": inserted_bet_id,
            "match_id": match.match_id,
            "bet_type": team_to_bet_on,
            "odd_id": latest_odd.odds_id,  # Use latest odds id
            "outcome": "pending"
        }
        await session.execute(insert(BetEvent).values(**bet_event_payload))

        # Now update the user's balance: subtract the stake amount
        stmt_update_user = (
            update(User)
            .where(User.user_id == bot.user_id)
            .values(balance = User.balance - stake_amount)
        )
        await session.execute(stmt_update_user)

        logger.info(f"\n ----- [{bot.name}] Placed bot bet on match {match.match_id} at odd {odds_to_use} -----")
        await session.commit()

        return {
            "status": "success",
            "team": team_to_bet_on,
            "odds": odds_to_use,
            "amount": stake_amount,
            "action": action
        }

    return {"status": "skipped", "reason": "Invalid action or missing odds"}
