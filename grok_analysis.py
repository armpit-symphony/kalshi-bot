"""Grok analysis module for generating trading signals."""

from typing import Tuple
from xai_sdk import Client


class GrokAnalyzer:
    """Client for using Grok to analyze prediction markets."""
    
    def __init__(self, api_key: str):
        """
        Initialize the Grok analyzer.
        
        Args:
            api_key: Your xAI API key from https://console.x.ai
        """
        self.client = Client(api_key=api_key)
    
    def analyze(
        self,
        market_title: str,
        market_description: str = "",
        news: list = None
    ) -> Tuple[str, float]:
        """
        Analyze a market and generate a trading signal.
        
        Args:
            market_title: Title of the market
            market_description: Additional description
            news: List of related news headlines/descriptions
        
        Returns:
            Tuple of (signal: 'YES'/'NO'/'HOLD', confidence: 0.0-1.0)
        """
        # Build the prompt
        prompt = f"""You are an expert at analyzing prediction markets.
        
Market: {market_title}
Description: {market_description}
"""
        
        if news:
            prompt += f"\nRecent News:\n"
            for i, article in enumerate(news[:5], 1):
                prompt += f"{i}. {article}\n"
        
        prompt += """
Based on the above information, predict the outcome of this prediction market.

Respond with ONLY one of these formats:
- "YES with 0.85" (if you think YES is likely, with confidence 0-1)
- "NO with 0.75" (if you think NO is likely, with confidence 0-1)
- "HOLD with 0.0" (if you don't have enough information)

Consider:
- Recent news and sentiment
- Market dynamics
- Historical patterns
- Current events

Make your prediction based on the evidence available.
"""
        
        try:
            response = self.client.chat.completions.create(
                model='grok-4',
                messages=[{'role': 'user', 'content': prompt}],
                temperature=0.5,
                max_tokens=100
            )
            
            output = response.choices[0].message.content.strip()
            
            # Parse the response
            return self._parse_response(output)
            
        except Exception as e:
            print(f"Grok analysis error: {e}")
            return ('HOLD', 0.0)
    
    def _parse_response(self, output: str) -> Tuple[str, float]:
        """Parse Grok's response into signal and confidence."""
        output = output.upper()
        
        if 'YES' in output and 'WITH' in output:
            try:
                confidence = float(output.split('WITH')[-1].strip())
                return ('YES', min(max(confidence, 0.0), 1.0))
            except (ValueError, IndexError):
                return ('YES', 0.5)
        
        elif 'NO' in output and 'WITH' in output:
            try:
                confidence = float(output.split('WITH')[-1].strip())
                return ('NO', min(max(confidence, 0.0), 1.0))
            except (ValueError, IndexError):
                return ('NO', 0.5)
        
        elif 'HOLD' in output:
            return ('HOLD', 0.0)
        
        # Default to hold if can't parse
        return ('HOLD', 0.0)


def analyze_with_grok(
    market_title: str,
    market_description: str,
    news: list,
    api_key: str
) -> Tuple[str, float]:
    """
    Convenience function to analyze a market with Grok.
    
    Args:
        market_title: Title of the market
        market_description: Description
        news: List of news articles
        api_key: xAI API key
    
    Returns:
        Tuple of (signal, confidence)
    """
    analyzer = GrokAnalyzer(api_key)
    return analyzer.analyze(market_title, market_description, news)
