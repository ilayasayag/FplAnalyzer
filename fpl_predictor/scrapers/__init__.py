"""
Web scrapers for predicted lineups from multiple sources.
"""

from .lineup_scraper import LineupScraper
from .aggregator import LineupAggregator

__all__ = ['LineupScraper', 'LineupAggregator']
