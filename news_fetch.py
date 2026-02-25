"""News fetching module using NewsAPI."""

from typing import List
from newsapi import NewsApiClient


class NewsFetcher:
    """Client for fetching news related to prediction markets."""
    
    def __init__(self, api_key: str):
        """
        Initialize the news fetcher.
        
        Args:
            api_key: Your NewsAPI key from https://newsapi.org
        """
        self.client = NewsApiClient(api_key=api_key)
    
    def fetch_news(self, query: str, max_results: int = 5) -> List[str]:
        """
        Fetch news articles related.
        Args:
            query: Search query (usually market title)
            max_results: Maximum number of articles to return
        
        Returns:
            List of article descriptions
        """
        try:
            response = self.client.get_everything(
                q=query,
                language='en',
                sort_by='relevancy',
                page_size=max_results
            )
            
            if response.get('status') == 'ok':
                articles = response.get('articles', [])
                return [
                    article.get('description', '')
                    for article in articles
                    if article.get('description')
                ]
            return []
        except Exception as e:
            print(f"News fetch error: {e}")
            return []


def fetch_news(query: str, api_key: str, max_results: int = 5) -> List[str]:
    """
    Convenience function to fetch news.
    
    Args:
        query: Search query
        api_key: NewsAPI key
        max_results: Max articles
    
    Returns:
        List of descriptions
    """
    if not api_key:
        return []
    fetcher = NewsFetcher(api_key)
    return fetcher.fetch_news(query, max_results)
