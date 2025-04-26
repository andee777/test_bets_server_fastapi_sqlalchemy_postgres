from sqlalchemy import Column, Text, DateTime, Integer, Boolean, Float
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func # Import func for server_default
from datetime import datetime

# Base is defined in this file according to your provided code.
# Ideally, Base should be defined once (e.g., in app/database.py) and imported.
Base = declarative_base()

class Match(Base):
    __tablename__ = 'match'
    match_id = Column(Text, primary_key=True, index=True)
    competition_name = Column(Text, index=True, nullable=True)
    category = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    home_team = Column(Text, nullable=True)
    away_team = Column(Text, nullable=True)
    event_status = Column(Text, nullable=True)
    live = Column(Boolean, default=False, index=True)
    start_time = Column(DateTime, nullable=True)
    match_time = Column(Text, nullable=True)

class EndedMatch(Base):
    __tablename__ = 'ended_match'
    match_id = Column(Text, primary_key=True, index=True)
    competition_name = Column(Text, index=True, nullable=True)
    category = Column(Text, nullable=True)
    country = Column(Text, nullable=True)
    home_team = Column(Text, nullable=True)
    away_team = Column(Text, nullable=True)
    event_status = Column(Text, nullable=True)
    live = Column(Boolean, default=False, index=True)
    start_time = Column(DateTime, nullable=True)
    match_time = Column(Text, nullable=True)

class Odds(Base):
    __tablename__ = 'odds'
    odds_id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(Text, index=True)
    event_status = Column(Text, nullable=True)
    match_time = Column(Text, nullable=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    home_win = Column(Float, nullable=True)
    draw = Column(Float, nullable=True)
    away_win = Column(Float, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now(), index=True)

class LatestOdd(Base):
    __tablename__ = 'latest_odd'
    match_id = Column(Text, primary_key=True)
    odds_id = Column(Integer, index=True)
    event_status = Column(Text, nullable=True)
    match_time = Column(Text, nullable=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    home_win = Column(Float, nullable=True)
    draw = Column(Float, nullable=True)
    away_win = Column(Float, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now(), index=True)

class InitialOdd(Base):
    __tablename__ = 'initial_odd'
    match_id = Column(Text, primary_key=True)
    odds_id = Column(Integer, index=True)
    event_status = Column(Text, nullable=True)
    match_time = Column(Text, nullable=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    home_win = Column(Float, nullable=True)
    draw = Column(Float, nullable=True)
    away_win = Column(Float, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now(), index=True)

class MaxOddsHome(Base):
    __tablename__ = 'max_odds_home'
    match_id = Column(Text, primary_key=True)
    odds_id = Column(Integer, index=True)
    event_status = Column(Text, nullable=True)
    match_time = Column(Text, nullable=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    home_win = Column(Float, nullable=True)
    draw = Column(Float, nullable=True)
    away_win = Column(Float, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now(), index=True)

class MaxOddsDraw(Base):
    __tablename__ = 'max_odds_draw'
    match_id = Column(Text, primary_key=True)
    odds_id = Column(Integer, index=True)
    event_status = Column(Text, nullable=True)
    match_time = Column(Text, nullable=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    home_win = Column(Float, nullable=True)
    draw = Column(Float, nullable=True)
    away_win = Column(Float, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now(), index=True)

class MaxOddsAway(Base):
    __tablename__ = 'max_odds_away'
    match_id = Column(Text, primary_key=True)
    odds_id = Column(Integer, index=True)
    event_status = Column(Text, nullable=True)
    match_time = Column(Text, nullable=True)
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    home_win = Column(Float, nullable=True)
    draw = Column(Float, nullable=True)
    away_win = Column(Float, nullable=True)
    fetched_at = Column(DateTime, server_default=func.now(), index=True)


# Users table (primary key: user_id)
class User(Base):
    __tablename__ = 'user'
    user_id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(Text, nullable=False, unique=True)
    password = Column(Text, nullable=False)
    name = Column(Text, nullable=True)
    balance = Column(Float, nullable=False, default=0)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

# Bets table (primary key: bet_id)
class Bet(Base):
    __tablename__ = 'bet'
    bet_id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, nullable=False)
    type = Column(Text, nullable=False)  # "single" or "parlay"
    amount = Column(Float, nullable=False)
    expected_win = Column(Float, nullable=True)
    outcome = Column(Text, nullable=True)  # "pending", "won", "lost"
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    bot = Column(Boolean, nullable=True)
    bot_task = Column(Text, nullable=True)

# BetEvents table (primary key: bet_event_id)
class BetEvent(Base):
    __tablename__ = 'bet_event'
    bet_event_id = Column(Integer, primary_key=True, autoincrement=True)
    bet_id = Column(Integer, nullable=False)  # FK to bet.bet_id
    match_id = Column(Text, nullable=False)
    bet_type = Column(Text, nullable=False)  # "home", "draw", "away"
    odd_id = Column(Integer, nullable=False)  # The specific odd placed
    outcome = Column(Text, nullable=True)  # "pending", "won", "lost"