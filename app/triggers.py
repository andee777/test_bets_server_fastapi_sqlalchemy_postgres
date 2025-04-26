import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection  # For type hinting

logger = logging.getLogger(__name__)

async def create_trigger_functions(conn: AsyncConnection):
    # --- Existing trigger function for odds summary ---
    trigger_function_sql = """
    CREATE OR REPLACE FUNCTION update_odd_summary() RETURNS trigger AS $$
    BEGIN
      -- Update Latest Odd
      INSERT INTO latest_odd (match_id, odds_id, event_status, match_time, home_score, away_score, home_win, draw, away_win, fetched_at)
      VALUES (NEW.match_id, NEW.odds_id, NEW.event_status, NEW.match_time, NEW.home_score, NEW.away_score, NEW.home_win, NEW.draw, NEW.away_win, NEW.fetched_at)
      ON CONFLICT (match_id) DO UPDATE SET
        odds_id = EXCLUDED.odds_id,
        event_status = EXCLUDED.event_status,
        match_time = EXCLUDED.match_time,
        home_score = EXCLUDED.home_score,
        away_score = EXCLUDED.away_score,
        home_win = EXCLUDED.home_win,
        draw = EXCLUDED.draw,
        away_win = EXCLUDED.away_win,
        fetched_at = EXCLUDED.fetched_at;

      -- Update Initial Odd
      INSERT INTO initial_odd (match_id, odds_id, event_status, match_time, home_score, away_score, home_win, draw, away_win, fetched_at)
      VALUES (NEW.match_id, NEW.odds_id, NEW.event_status, NEW.match_time, NEW.home_score, NEW.away_score, NEW.home_win, NEW.draw, NEW.away_win, NEW.fetched_at)
      ON CONFLICT (match_id) DO NOTHING;

      -- Max Home Odds
      IF NEW.home_win IS NOT NULL THEN
        INSERT INTO max_odds_home (match_id, odds_id, event_status, match_time, home_score, away_score, home_win, draw, away_win, fetched_at)
        VALUES (NEW.match_id, NEW.odds_id, NEW.event_status, NEW.match_time, NEW.home_score, NEW.away_score, NEW.home_win, NEW.draw, NEW.away_win, NEW.fetched_at)
        ON CONFLICT (match_id) DO UPDATE SET
            odds_id = EXCLUDED.odds_id,
            event_status = EXCLUDED.event_status,
            match_time = EXCLUDED.match_time,
            home_score = EXCLUDED.home_score,
            away_score = EXCLUDED.away_score,
            home_win = EXCLUDED.home_win,
            draw = EXCLUDED.draw,
            away_win = EXCLUDED.away_win,
            fetched_at = EXCLUDED.fetched_at
        WHERE EXCLUDED.home_win > max_odds_home.home_win;
      END IF;

      -- Max Draw Odds
      IF NEW.draw IS NOT NULL THEN
        INSERT INTO max_odds_draw (match_id, odds_id, event_status, match_time, home_score, away_score, home_win, draw, away_win, fetched_at)
        VALUES (NEW.match_id, NEW.odds_id, NEW.event_status, NEW.match_time, NEW.home_score, NEW.away_score, NEW.home_win, NEW.draw, NEW.away_win, NEW.fetched_at)
        ON CONFLICT (match_id) DO UPDATE SET
            odds_id = EXCLUDED.odds_id,
            event_status = EXCLUDED.event_status,
            match_time = EXCLUDED.match_time,
            home_score = EXCLUDED.home_score,
            away_score = EXCLUDED.away_score,
            home_win = EXCLUDED.home_win,
            draw = EXCLUDED.draw,
            away_win = EXCLUDED.away_win,
            fetched_at = EXCLUDED.fetched_at
        WHERE EXCLUDED.draw > max_odds_draw.draw;
      END IF;

      -- Max Away Odds
      IF NEW.away_win IS NOT NULL THEN
        INSERT INTO max_odds_away (match_id, odds_id, event_status, match_time, home_score, away_score, home_win, draw, away_win, fetched_at)
        VALUES (NEW.match_id, NEW.odds_id, NEW.event_status, NEW.match_time, NEW.home_score, NEW.away_score, NEW.home_win, NEW.draw, NEW.away_win, NEW.fetched_at)
        ON CONFLICT (match_id) DO UPDATE SET
            odds_id = EXCLUDED.odds_id,
            event_status = EXCLUDED.event_status,
            match_time = EXCLUDED.match_time,
            home_score = EXCLUDED.home_score,
            away_score = EXCLUDED.away_score,
            home_win = EXCLUDED.home_win,
            draw = EXCLUDED.draw,
            away_win = EXCLUDED.away_win,
            fetched_at = EXCLUDED.fetched_at
        WHERE EXCLUDED.away_win > max_odds_away.away_win;
      END IF;

      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """

    # logger.info("Creating/Replacing 'update_odd_summary' trigger function...")
    await conn.execute(text(trigger_function_sql))

    await conn.execute(text('DROP TRIGGER IF EXISTS odd_summary_trigger ON odds;'))

    const_create_trigger_sql = """
    CREATE TRIGGER odd_summary_trigger
    AFTER INSERT OR UPDATE ON odds
    FOR EACH ROW
    EXECUTE FUNCTION update_odd_summary();
    """
    await conn.execute(text(const_create_trigger_sql))
    # logger.info("Trigger for odds summary created.")

    # --- Trigger for updating bet outcome when match ends ---
    trigger_function_match_sql = """
    CREATE OR REPLACE FUNCTION update_bet_on_match_end() RETURNS trigger AS $$
    DECLARE
      final_home_score INTEGER;
      final_away_score INTEGER;
      winning_bet_type TEXT;
    BEGIN
      IF NEW.event_status = 'ended' AND (OLD.event_status IS DISTINCT FROM NEW.event_status) THEN
        SELECT home_score, away_score INTO final_home_score, final_away_score
        FROM latest_odd
        WHERE match_id = NEW.match_id
        LIMIT 1;

        IF final_home_score IS NULL OR final_away_score IS NULL THEN
          RAISE NOTICE 'Final score not available for match %', NEW.match_id;
          RETURN NEW;
        END IF;

        IF final_home_score > final_away_score THEN
          winning_bet_type := 'home';
        ELSIF final_home_score < final_away_score THEN
          winning_bet_type := 'away';
        ELSE
          winning_bet_type := 'draw';
        END IF;

        UPDATE bet_event
        SET outcome = CASE
                        WHEN bet_type = winning_bet_type THEN 'won'
                        ELSE 'lost'
                      END
        WHERE match_id = NEW.match_id AND (outcome IS NULL OR outcome = 'pending');

        UPDATE bet
        SET outcome = (
          SELECT CASE
                   WHEN EXISTS (
                     SELECT 1 FROM bet_event
                     WHERE bet_id = bet.bet_id AND outcome = 'lost'
                   ) THEN 'lost'
                   WHEN NOT EXISTS (
                     SELECT 1 FROM bet_event
                     WHERE bet_id = bet.bet_id AND (outcome IS NULL OR outcome = 'pending')
                   ) THEN 'won'
                   ELSE outcome
                 END
          FROM bet_event
          WHERE bet_event.bet_id = bet.bet_id
          LIMIT 1
        )
        WHERE bet_id IN (
          SELECT DISTINCT bet_id FROM bet_event WHERE match_id = NEW.match_id
        );
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """

    # logger.info("Creating/Replacing 'update_bet_on_match_end' trigger function...")
    await conn.execute(text(trigger_function_match_sql))

    await conn.execute(text('DROP TRIGGER IF EXISTS match_end_trigger ON "match";'))

    const_create_match_trigger_sql = """
    CREATE TRIGGER match_end_trigger
    AFTER UPDATE ON "match"
    FOR EACH ROW
    WHEN (NEW.event_status = 'ended')
    EXECUTE FUNCTION update_bet_on_match_end();
    """
    await conn.execute(text(const_create_match_trigger_sql))
    # logger.info("Trigger for match end events created.")

    # --- New Trigger: update user balance when a bet is won ---
    trigger_function_bet_win_sql = """
    CREATE OR REPLACE FUNCTION update_user_balance_on_bet_win() RETURNS trigger AS $$
    BEGIN
      IF NEW.outcome = 'won' AND (OLD.outcome IS DISTINCT FROM 'won') THEN
        UPDATE "user"
        SET balance = balance + NEW.expected_win
        WHERE user_id = NEW.user_id;
      END IF;
      RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """

    # logger.info("Creating/Replacing 'update_user_balance_on_bet_win' trigger function...")
    await conn.execute(text(trigger_function_bet_win_sql))

    await conn.execute(text('DROP TRIGGER IF EXISTS bet_win_trigger ON "bet";'))

    const_create_bet_win_trigger_sql = """
    CREATE TRIGGER bet_win_trigger
    AFTER UPDATE ON "bet"
    FOR EACH ROW
    WHEN (NEW.outcome = 'won')
    EXECUTE FUNCTION update_user_balance_on_bet_win();
    """
    await conn.execute(text(const_create_bet_win_trigger_sql))
    # logger.info("Trigger for bet win user balance update created.")
