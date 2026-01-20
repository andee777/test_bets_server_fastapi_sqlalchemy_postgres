from sqlalchemy import Column, Text, DateTime, Integer, Boolean, Float, ForeignKey, JSON, Index
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func # Import func for server_default
from datetime import datetime

# Base is defined in this file according to your provided code.
# Ideally, Base should be defined once (e.g., in app/database.py) and imported.
Base = declarative_base()

class Bot(Base):
    __tablename__ = "bot"

    bot_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    public = Column(Boolean, nullable=False, server_default="false")
    user_id = Column(Integer, ForeignKey("user.user_id"), nullable=False)
    conditions = Column(JSON, nullable=False)
    action = Column(Text, nullable=False)
    bet_amount = Column(Float, nullable=True)
    active = Column(Boolean, nullable=False, server_default="true")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

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
    bot_id = Column(Integer, nullable=True)
    validated = Column(Boolean)
    validated_at = Column(DateTime)

# BetEvents table (primary key: bet_event_id)
class BetEvent(Base):
    __tablename__ = 'bet_event'
    bet_event_id = Column(Integer, primary_key=True, autoincrement=True)
    bet_id = Column(Integer, nullable=False)  # FK to bet.bet_id
    match_id = Column(Text, nullable=False)
    bet_type = Column(Text, nullable=False)  # "home", "draw", "away"
    odd_id = Column(Integer, nullable=False)  # The specific odd placed
    outcome = Column(Text, nullable=True)  # "pending", "won", "lost"
    validated = Column(Boolean)
    validated_at = Column(DateTime)
    
class LeagueTeam(Base):
    __tablename__ = 'league_team'
    league_id = Column(Integer, ForeignKey("league.league_id"), primary_key=True, nullable=False)
    team_id = Column(Integer, ForeignKey("team.team_id"), primary_key=True, nullable=False)

class Team(Base):
    __tablename__ = 'team'
    team_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False, index=True)

class League(Base):
    __tablename__ = 'league'
    league_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False) 
    country = Column(Text, nullable=False) 
    country_code = Column(Text, nullable=True) 

class TeamAlias(Base):
    __tablename__ = 'team_alias'
    alias_id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, nullable=False)
    alias = Column(Text, nullable=False, index=True)

class LeagueAlias(Base):
    __tablename__ = 'league_alias'
    alias_id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(Integer, nullable=False)
    alias = Column(Text, nullable=False) 

class SofascoreFt(Base):
    __tablename__ = 'sofascore_ft'
    sofascore_id = Column(Integer, nullable=False, primary_key=True)
    competition_name = Column(Text, nullable=False)
    category = Column(Text, nullable=True)
    country = Column(Text, nullable=False)
    country_code = Column(Text, nullable=False)
    home_team = Column(Text, nullable=False)
    home_score = Column(Integer, nullable=False)
    away_team = Column(Text, nullable=False)
    away_score = Column(Integer, nullable=False)
    start_time = Column(DateTime, nullable=False)
    home_team_id = Column(Integer, nullable=True)
    away_team_id = Column(Integer, nullable=True)
    league_id = Column(Integer, nullable=True)
    match_id = Column(Integer, nullable=True)
