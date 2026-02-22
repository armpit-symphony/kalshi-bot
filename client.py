"""Kalshi API Client Wrapper - Using Official SDK"""

import os
import logging
from typing import Optional, List

try:
    from kalshi_python import Configuration, KalshiClient
except ImportError:
    print("ERROR: kalshi-python not installed")
    print("Install with: pip install kalshi-python")
    raise

from config import Config


class KalshiBotClient:
    """Wrapper around Official Kalshi SDK."""
    
    def __init__(self, config: Config):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # Create SDK configuration - use direct attributes
        self._configuration = Configuration(
            host=config.host + "/trade-api/v2",
        )
        self._configuration.api_key_id = config.api_key_id
        self._configuration.private_key_pem = config.private_key_pem
        
        # Create client
        self._client = KalshiClient(self._configuration)
        
        print(f"📡 Client initialized for {config.host}")
    
    def test_connection(self) -> bool:
        """Test API connection."""
        try:
            self._client.get_balance()
            return True
        except Exception as e:
            self.logger.error(f"Connection test failed: {e}")
            return False
    
    def get_balance(self):
        """Get account balance."""
        return self._client.get_balance()
    
    def get_events(self, limit: int = 20) -> List:
        """Get active events."""
        response = self._client.get_events(
            limit=limit,
            status="active"
        )
        return response.events
    
    def get_markets(self, limit: int = 20, event_id: Optional[str] = None):
        """Get markets, optionally filtered by event."""
        response = self._client.get_markets(limit=limit)
        return response.markets
    
    def get_market(self, ticker: str):
        """Get specific market."""
        return self._client.get_market(ticker=ticker)
    
    def get_positions(self):
        """Get current positions."""
        return self._client.get_positions()
    
    def get_orders(self, status: str = "open"):
        """Get orders."""
        return self._client.get_orders(status=status)
    
    def place_order(
        self,
        ticker: str,
        side: str,  # "yes" or "no"
        price: int,  # 0-100
        count: int,  # number of contracts
    ):
        """Place an order."""
        return self._client.create_order(
            ticker=ticker,
            side=side,
            price=price,
            count=count,
        )
    
    def cancel_order(self, order_id: str):
        """Cancel an order."""
        return self._client.cancel_order(order_id=order_id)
