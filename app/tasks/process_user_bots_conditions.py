# app/tasks/process_user_bots_conditions.py
from typing import Dict, Any
from app.models import InitialOdd, LatestOdd, Match


def compare_value(operator: str, target_value, condition_value) -> bool:
    """Compare a numeric or comparable value against a condition."""
    if target_value is None:
        return False

    try:
        if operator == "equals":
            return target_value == condition_value

        elif operator == "greater_than":
            return target_value > condition_value

        elif operator == "less_than":
            return target_value < condition_value

        elif operator == "between":
            # condition_value should be a list or tuple with exactly 2 numeric elements
            if (
                isinstance(condition_value, (list, tuple))
                and len(condition_value) == 2
            ):
                lower, upper = condition_value
                # print(lower, upper, condition_value, lower <= target_value <= upper)
                # Handle both numeric and string comparison cases
                return lower <= target_value <= upper
            else:
                # Invalid format for "between"
                return False

        elif operator == "not_equals":
            return target_value != condition_value

    except Exception as e:
        print(f"compare_value error: {e}")
        return False

    return False


def get_favourite_and_outsider(
    current_odds_home: float | None,
    current_odds_draw: float | None,
    current_odds_away: float | None,
    initial_odds_home: float | None,
    initial_odds_draw: float | None,
    initial_odds_away: float | None,
    current: bool = True,
):
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

    odds_map = {k: v for k, v in odds_map.items() if v is not None}
    if not odds_map:
        return None, None

    sorted_odds = sorted(odds_map.items(), key=lambda x: x[1])
    favourite_side = sorted_odds[0][0]
    # print("favourite_side:", sorted_odds[0])
    outsider_side = sorted_odds[-1][0]
    return favourite_side, outsider_side


def get_selected_team(bot_conditions: dict, home_team: str, away_team: str) -> str | None:
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

    _, team_name = next(iter(team_condition.items()), (None, None))
    if not team_name:
        return None

    home_team = (home_team or "").lower()
    away_team = (away_team or "").lower()
    team_name = team_name.lower()

    if team_name == home_team:
        return "home"
    elif team_name == away_team:
        return "away"
    return None


async def process_bot_conditions(
    session,
    bot_conditions: Dict[str, Dict[str, Any]],
    match: Match,
    initial_odd: InitialOdd,
    latest_odd: LatestOdd,
) -> bool:
    """
    Evaluates whether a given match satisfies all of a bot's conditions.
    Returns True if all conditions match, False otherwise.
    """

    for key, condition in bot_conditions.items():
        if not condition:
            continue

        operator, value = list(condition.items())[0]

        # 🏟️ Match-level checks
        if key == "country":
            if match.country != value:
                return False

        elif key == "competition":
            if match.competition_name != value:
                return False

        elif key == "team":
            if value not in [match.home_team, match.away_team]:
                return False

        elif key == "match_time":
            try:
                minutes, seconds = map(int, match.match_time.split(":"))
                match_time_value = minutes + seconds / 60
            except Exception:
                match_time_value = 0
            if not compare_value(operator, match_time_value, value):
                return False

        elif key == "home_goals":
            if not compare_value(operator, latest_odd.home_score, value):
                return False

        elif key == "away_goals":
            if not compare_value(operator, latest_odd.away_score, value):
                return False

        elif key == "home_red_cards":
            if not compare_value(operator, getattr(match, "home_red_cards", None), value):
                return False

        elif key == "away_red_cards":
            if not compare_value(operator, getattr(match, "away_red_cards", None), value):
                return False

        # 🎲 Initial odds conditions
        elif key.startswith("initial_odds_"):
            if not initial_odd:
                return False

            initial_fav, initial_out = get_favourite_and_outsider(
                None,
                None,
                None,
                getattr(initial_odd, "home_win", None),
                getattr(initial_odd, "draw", None),
                getattr(initial_odd, "away_win", None),
                current=False,
            )

            if key == "initial_odds_any":
                odd_value = min(
                    getattr(initial_odd, "home_win", None),
                    getattr(initial_odd, "draw", None),
                    getattr(initial_odd, "away_win", None),
                )
            elif key == "initial_odds_home":
                odd_value = getattr(initial_odd, "home_win", None)
            elif key == "initial_odds_draw":
                odd_value = getattr(initial_odd, "draw", None)
            elif key == "initial_odds_away":
                odd_value = getattr(initial_odd, "away_win", None)
            elif key == "initial_odds_selected_team":
                selected_team = get_selected_team(bot_conditions, match.home_team, match.away_team)
                odd_value = getattr(initial_odd, f"{selected_team}_win", None)
            elif key == "initial_odds_favourite" and initial_fav:
                if initial_fav == 'draw':
                    odd_value = getattr(initial_odd, f"draw", None)
                else:
                    odd_value = getattr(initial_odd, f"{initial_fav}_win", None)
            elif key == "initial_odds_outsider" and initial_out:
                if initial_fav == 'draw':
                    odd_value = getattr(initial_odd, f"draw", None)
                else:
                    odd_value = getattr(initial_odd, f"{initial_out}_win", None)
            else:
                odd_value = None

            if not compare_value(operator, odd_value, value):
                return False

        # 🎲 Live odds conditions
        elif key.startswith("live_odds_"):
            if not latest_odd:
                return False

            live_fav, live_out = get_favourite_and_outsider(
                getattr(latest_odd, "home_win", None),
                getattr(latest_odd, "draw", None),
                getattr(latest_odd, "away_win", None),
                None,
                None,
                None,
                current=True,
            )

            if key == "live_odds_any":
                odd_value = min(
                    getattr(latest_odd, "home_win", None),
                    getattr(latest_odd, "draw", None),
                    getattr(latest_odd, "away_win", None),
                )
            elif key == "live_odds_home":
                odd_value = getattr(latest_odd, "home_win", None)
            elif key == "live_odds_draw":
                odd_value = getattr(latest_odd, "draw", None)
            elif key == "live_odds_away":
                odd_value = getattr(latest_odd, "away_win", None)
            elif key == "live_odds_selected_team":
                selected_team = get_selected_team(bot_conditions, match.home_team, match.away_team)
                odd_value = getattr(latest_odd, f"{selected_team}_win", None)
            elif key == "live_odds_favourite" and live_fav:
                if live_fav == 'draw':
                    odd_value = getattr(latest_odd, f"draw", None)
                else:
                    odd_value = getattr(latest_odd, f"{live_fav}_win", None)
                # print('---live odds', match.home_team, match.away_team, live_fav, match.match_time)
            elif key == "live_odds_outsider" and live_out:
                if live_fav == 'draw':
                    odd_value = getattr(latest_odd, f"draw", None)
                else:
                    odd_value = getattr(latest_odd, f"{live_out}_win", None)
            else:
                odd_value = None

            if not compare_value(operator, odd_value, value):
                return False

        # 🧮 Score difference
        elif key == "score_difference":
            diff = abs(
                getattr(latest_odd, "home_score", 0)
                - getattr(latest_odd, "away_score", 0)
            )
            if not compare_value(operator, diff, value):
                return False

        else:
            continue

    # ✅ All conditions satisfied
    return True
