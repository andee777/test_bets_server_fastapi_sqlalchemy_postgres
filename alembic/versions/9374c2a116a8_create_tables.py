"""create tables

Revision ID: 9374c2a116a8
Revises: 
Create Date: 2025-04-06 02:19:21.546012

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9374c2a116a8'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create the 'match' table
    op.create_table(
        'match',
        sa.Column('match_id', sa.Text(), primary_key=True, index=True),
        sa.Column('competition_name', sa.Text(), nullable=True, index=True),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('country', sa.Text(), nullable=True),
        sa.Column('home_team', sa.Text(), nullable=True),
        sa.Column('away_team', sa.Text(), nullable=True),
        sa.Column('event_status', sa.Text(), nullable=True),
        sa.Column('live', sa.Boolean(), nullable=False, default=False, index=True),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('match_time', sa.Text(), nullable=True),
    )

    # Create the 'ended_match' table
    op.create_table(
        'ended_match',
        sa.Column('match_id', sa.Text(), primary_key=True, index=True),
        sa.Column('competition_name', sa.Text(), nullable=True, index=True),
        sa.Column('category', sa.Text(), nullable=True),
        sa.Column('country', sa.Text(), nullable=True),
        sa.Column('home_team', sa.Text(), nullable=True),
        sa.Column('away_team', sa.Text(), nullable=True),
        sa.Column('event_status', sa.Text(), nullable=True),
        sa.Column('live', sa.Boolean(), nullable=False, default=False, index=True),
        sa.Column('start_time', sa.DateTime(), nullable=True),
        sa.Column('match_time', sa.Text(), nullable=True),
    )

    # Create the 'odds' table
    op.create_table(
        'odds',
        sa.Column('odds_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('match_id', sa.Text(), index=True),
        sa.Column('event_status', sa.Text(), nullable=True),
        sa.Column('match_time', sa.Text(), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('home_win', sa.Float(), nullable=True),
        sa.Column('draw', sa.Float(), nullable=True),
        sa.Column('away_win', sa.Float(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), server_default=sa.func.now(), index=True),
    )

    # Create the 'latest_odd' table
    op.create_table(
        'latest_odd',
        sa.Column('match_id', sa.Text(), primary_key=True),
        sa.Column('odds_id', sa.Integer(), index=True),
        sa.Column('event_status', sa.Text(), nullable=True),
        sa.Column('match_time', sa.Text(), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('home_win', sa.Float(), nullable=True),
        sa.Column('draw', sa.Float(), nullable=True),
        sa.Column('away_win', sa.Float(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), server_default=sa.func.now(), index=True),
    )
    op.create_foreign_key('latest_odd_odds_id_fkey', 'latest_odd', 'odds', ['odds_id'], ['odds_id'])

    # Create the 'initial_odd' table
    op.create_table(
        'initial_odd',
        sa.Column('match_id', sa.Text(), primary_key=True),
        sa.Column('odds_id', sa.Integer(), index=True),
        sa.Column('event_status', sa.Text(), nullable=True),
        sa.Column('match_time', sa.Text(), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('home_win', sa.Float(), nullable=True),
        sa.Column('draw', sa.Float(), nullable=True),
        sa.Column('away_win', sa.Float(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), server_default=sa.func.now(), index=True),
    )
    op.create_foreign_key('initial_odd_odds_id_fkey', 'initial_odd', 'odds', ['odds_id'], ['odds_id'])

    # Create the 'max_odds_home' table
    op.create_table(
        'max_odds_home',
        sa.Column('match_id', sa.Text(), primary_key=True),
        sa.Column('odds_id', sa.Integer(), index=True),
        sa.Column('event_status', sa.Text(), nullable=True),
        sa.Column('match_time', sa.Text(), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('home_win', sa.Float(), nullable=True),
        sa.Column('draw', sa.Float(), nullable=True),
        sa.Column('away_win', sa.Float(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), server_default=sa.func.now(), index=True),
    )
    op.create_foreign_key('max_odds_home_odds_id_fkey', 'max_odds_home', 'odds', ['odds_id'], ['odds_id'])

    # Create the 'max_odds_draw' table
    op.create_table(
        'max_odds_draw',
        sa.Column('match_id', sa.Text(), primary_key=True),
        sa.Column('odds_id', sa.Integer(), index=True),
        sa.Column('event_status', sa.Text(), nullable=True),
        sa.Column('match_time', sa.Text(), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('home_win', sa.Float(), nullable=True),
        sa.Column('draw', sa.Float(), nullable=True),
        sa.Column('away_win', sa.Float(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), server_default=sa.func.now(), index=True),
    )
    op.create_foreign_key('max_odds_draw_odds_id_fkey', 'max_odds_draw', 'odds', ['odds_id'], ['odds_id'])

    # Create the 'max_odds_away' table
    op.create_table(
        'max_odds_away',
        sa.Column('match_id', sa.Text(), primary_key=True),
        sa.Column('odds_id', sa.Integer(), index=True),
        sa.Column('event_status', sa.Text(), nullable=True),
        sa.Column('match_time', sa.Text(), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('home_win', sa.Float(), nullable=True),
        sa.Column('draw', sa.Float(), nullable=True),
        sa.Column('away_win', sa.Float(), nullable=True),
        sa.Column('fetched_at', sa.DateTime(), server_default=sa.func.now(), index=True),
    )
    op.create_foreign_key('max_odds_away_odds_id_fkey', 'max_odds_away', 'odds', ['odds_id'], ['odds_id'])

    # Create the 'user' table
    # op.create_table(
    #     'user',
    #     sa.Column('user_id', sa.Integer(), primary_key=True, autoincrement=True),
    #     sa.Column('email', sa.Text(), nullable=False, unique=True),
    #     sa.Column('password', sa.Text(), nullable=False),
    #     sa.Column('name', sa.Text(), nullable=True),
    #     sa.Column('balance', sa.Float(), nullable=False, default=0),
    #     sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    #     sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    # )

    # Create the 'bet' table
    op.create_table(
        'bet',
        sa.Column('bet_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),  # "single" or "parlay"
        sa.Column('amount', sa.Float(), nullable=False),
        sa.Column('expected_win', sa.Float(), nullable=True),
        sa.Column('outcome', sa.Text(), nullable=True),  # "pending", "won", "lost"
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('bot', sa.Boolean(), nullable=False, server_default=sa.text('false')),  # new column
        sa.Column('bot_task', sa.Text(), nullable=True),  # new column
    )
    op.create_foreign_key('bet_user_id_fkey', 'bet', 'user', ['user_id'], ['user_id'])

    # Create the 'bet_event' table
    op.create_table(
        'bet_event',
        sa.Column('bet_event_id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('bet_id', sa.Integer(), nullable=False),  # FK to bet.bet_id
        sa.Column('match_id', sa.Text(), nullable=False),
        sa.Column('bet_type', sa.Text(), nullable=False),  # "home", "draw", "away"
        sa.Column('odd_id', sa.Integer(), nullable=False),  # The specific odd placed
        sa.Column('outcome', sa.Text(), nullable=True),  # "pending", "won", "lost"
    )
    op.create_foreign_key('bet_event_bet_id_fkey', 'bet_event', 'bet', ['bet_id'], ['bet_id'])


def downgrade() -> None:
    """Downgrade schema."""
    # Drop all tables in reverse order
    # op.drop_table('bet_event')
    # op.drop_table('bet')
    # # op.drop_table('user')
    # op.drop_table('max_odds_away')
    # op.drop_table('max_odds_draw')
    # op.drop_table('max_odds_home')
    # op.drop_table('initial_odd')
    # op.drop_table('latest_odd')
    # op.drop_table('odds')
    # op.drop_table('ended_match')
    # op.drop_table('match')
