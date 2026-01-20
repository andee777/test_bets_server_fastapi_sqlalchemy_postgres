# app/alias_utils.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import TeamAlias, LeagueAlias
from rapidfuzz import fuzz


class AliasManager:
    """Manager for team and league aliases."""
    
    def __init__(self):
        self.team_aliases_cache = {}  # {canonical_name: [alias1, alias2, ...]}
        self.team_reverse_cache = {}  # {alias: canonical_name}
        self.league_aliases_cache = {}
        self.league_reverse_cache = {}
        self.cache_loaded = False
    
    async def load_cache(self, session: AsyncSession):
        """Load all aliases into memory cache."""
        # Load team aliases
        result = await session.execute(select(TeamAlias))
        team_aliases = result.fetchall()
        
        self.team_aliases_cache.clear()
        self.team_reverse_cache.clear()
        
        for row in team_aliases:
            alias_obj = row[0]
            canonical = alias_obj.canonical_name.strip().lower()
            alias = alias_obj.alias.strip().lower()
            
            if canonical not in self.team_aliases_cache:
                self.team_aliases_cache[canonical] = []
            self.team_aliases_cache[canonical].append(alias)
            self.team_reverse_cache[alias] = canonical
        
        # Load league aliases
        result = await session.execute(select(LeagueAlias))
        league_aliases = result.fetchall()
        
        self.league_aliases_cache.clear()
        self.league_reverse_cache.clear()
        
        for row in league_aliases:
            alias_obj = row[0]
            canonical = alias_obj.canonical_name.strip().lower()
            alias = alias_obj.alias.strip().lower()
            
            if canonical not in self.league_aliases_cache:
                self.league_aliases_cache[canonical] = []
            self.league_aliases_cache[canonical].append(alias)
            self.league_reverse_cache[alias] = canonical
        
        self.cache_loaded = True
    
    def normalize(self, text: str) -> str:
        """Normalize text for comparison."""
        return text.strip().lower() if text else ""
    
    def get_canonical_team(self, team_name: str) -> str:
        """Get canonical team name from any alias."""
        normalized = self.normalize(team_name)
        return self.team_reverse_cache.get(normalized, team_name)
    
    def get_canonical_league(self, league_name: str) -> str:
        """Get canonical league name from any alias."""
        normalized = self.normalize(league_name)
        return self.league_reverse_cache.get(normalized, league_name)
    
    def get_team_aliases(self, canonical_name: str) -> list:
        """Get all aliases for a canonical team name."""
        normalized = self.normalize(canonical_name)
        return self.team_aliases_cache.get(normalized, [])
    
    def get_league_aliases(self, canonical_name: str) -> list:
        """Get all aliases for a canonical league name."""
        normalized = self.normalize(canonical_name)
        return self.league_aliases_cache.get(normalized, [])
    
    def teams_match(self, team1: str, team2: str) -> bool:
        """Check if two team names refer to the same team."""
        canonical1 = self.get_canonical_team(team1)
        canonical2 = self.get_canonical_team(team2)
        return self.normalize(canonical1) == self.normalize(canonical2)
    
    def leagues_match(self, league1: str, league2: str) -> bool:
        """Check if two league names refer to the same league."""
        canonical1 = self.get_canonical_league(league1)
        canonical2 = self.get_canonical_league(league2)
        return self.normalize(canonical1) == self.normalize(canonical2)
    
    def match_exists(self, db_home: str, db_away: str, db_league: str,
                    fotmob_home: str, fotmob_away: str, fotmob_league: str) -> bool:
        """Check if a database match matches a FotMob match using aliases."""
        home_match = self.teams_match(db_home, fotmob_home)
        away_match = self.teams_match(db_away, fotmob_away)
        league_match = self.leagues_match(db_league, fotmob_league)
        
        return home_match and away_match and league_match


# Global instance
alias_manager = AliasManager()