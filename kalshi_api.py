"""Kalshi API client for market data and trading."""

import os
import time
import base64
import logging
import requests
from typing import List, Dict, Any, Optional
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)


class KalshiAPI:
    """Client for interacting with the Kalshi trading API."""
    
    def __init__(
        self,
        api_key_id: str,
        private_key_pem: str,
        use_demo: bool = True
    ):
        """
        Initialize the Kalshi API client.
        
        Args:
            api_key_id: Your Kalshi API key ID
            private_key_pem: Your private key in PEM format
            use_demo: Use demo environment (default True)
        """
        self.api_key_id = api_key_id
        self.private_key_pem = private_key_pem
        
        # Set the correct base URL
        if use_demo:
            self.base_url = 'https://demo-api.kalshi.co/trade-api/v2'
        else:
            self.base_url = 'https://api.elections.kalshi.com/trade-api/v2'
        
        # Load private key
        self._private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )
    
    def _sign_request(self, method: str, path: str) -> Dict[str, str]:
        """Create signed headers for API request."""
        timestamp = str(int(time.time() * 1000))
        
        # Create the message to sign — full path including API version prefix
        message = f"{timestamp}{method.upper()}/trade-api/v2{path}".encode('utf-8')
        
        # Sign with RSA-PSS
        signature = self._private_key.sign(
            message,
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.DIGEST_LENGTH
            ),
            hashes.SHA256()
        )
        
        signature_b64 = base64.b64encode(signature).decode('utf-8')
        
        headers = {
            'KALSHI-ACCESS-KEY': self.api_key_id,
            'KALSHI-ACCESS-TIMESTAMP': timestamp,
            'KALSHI-ACCESS-SIGNATURE': signature_b64,
            'Content-Type': 'application/json'
        }
        return headers
    
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """Make an authenticated API request."""
        headers = self._sign_request(method, path)
        
        url = self.base_url + path
        
        if method == 'GET':
            response = requests.get(url, headers=headers, params=params)
        elif method == 'POST':
            response = requests.post(url, headers=headers, json=data)
        elif method == 'DELETE':
            response = requests.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")
        
        if response.status_code not in (200, 201):
            raise Exception(f"API Error {response.status_code}: {response.text}")
        
        return response.json()
    
    def get_open_markets(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get open markets."""
        return self._request(
            'GET',
            '/markets',
            params={'status': 'open', 'limit': limit}
        ).get('markets', [])
    
    def get_market(self, ticker: str) -> Dict[str, Any]:
        """Get details for a specific market."""
        return self._request('GET', f'/markets/{ticker}')
    
    def get_market_orderbook(self, ticker: str) -> Dict[str, Any]:
        """Get order book for a market."""
        return self._request('GET', f'/markets/{ticker}/orderbook')

    def get_best_ask(self, ticker: str, side: str) -> Optional[int]:
        """
        Get best ask price for a side ("yes" or "no").
        Returns price in 0-100, or None if unavailable.
        """
        try:
            book = self.get_market_orderbook(ticker)
        except Exception:
            return None

        side = side.lower()

        def _extract_asks(container) -> Optional[int]:
            if not container:
                return None
            asks = container.get('asks') or container.get('ask') or []
            if not asks:
                return None
            prices = []
            for a in asks:
                if isinstance(a, dict) and 'price' in a:
                    prices.append(a['price'])
                elif isinstance(a, (list, tuple)) and len(a) > 0:
                    prices.append(a[0])
            return min(prices) if prices else None

        # Common shapes: {"yes": {"asks": [...]}, "no": {"asks": [...]}}
        if isinstance(book, dict):
            if side in book and isinstance(book[side], dict):
                best = _extract_asks(book[side])
                if best is not None:
                    return best

            # Alternate shapes
            key = f"{side}_asks"
            if key in book and isinstance(book[key], list):
                prices = []
                for a in book[key]:
                    if isinstance(a, dict) and 'price' in a:
                        prices.append(a['price'])
                    elif isinstance(a, (list, tuple)) and len(a) > 0:
                        prices.append(a[0])
                return min(prices) if prices else None

        return None
    
    def place_order(
        self,
        ticker: str,
        side: str,
        count: int,
        order_type: str = 'market',
        price: Optional[int] = None
    ) -> Optional[str]:
        """
        Place an order.
        
        Args:
            ticker: Market ticker (e.g., 'KXCAL')
            side: 'yes' or 'no'
            count: Number of contracts
            order_type: 'market' or 'limit'
            price: Price for limit orders (0-100)
        
        Returns:
            Order ID if successful, None otherwise
        """
        data = {
            'ticker': ticker,
            'side': side,
            'count': count,
            'type': order_type,
            'action': 'buy'
        }

        if price is not None:
            if side == 'yes':
                data['yes_price'] = int(price)
            else:
                data['no_price'] = int(price)
        
        try:
            result = self._request('POST', '/portfolio/orders', data=data)
            return result.get('order', {}).get('order_id')
        except Exception as e:
            logger.error(f"Order failed for {ticker}: {e}")
            return None
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions."""
        return self._request('GET', '/portfolio/positions').get('positions', [])
    
    def get_orders(self, status: str = 'open') -> List[Dict[str, Any]]:
        """Get orders, optionally filtered by status."""
        return self._request(
            'GET',
            '/portfolio/orders',
            params={'status': status}
        ).get('orders', [])
    
    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order."""
        try:
            self._request('DELETE', f'/orders/{order_id}')
            return True
        except Exception:
            return False
    
    def get_balance(self) -> Dict[str, Any]:
        """Get account balance."""
        return self._request('GET', '/portfolio/balance')
    
    def get_settlements(self) -> List[Dict[str, Any]]:
        """Get settlement history."""
        return self._request('GET', '/portfolio/settlements').get('settlements', [])

    def get_recent_trades(self, ticker: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get recent trades for a market."""
        try:
            return self._request('GET', f'/markets/{ticker}/trades', params={'limit': limit}).get('trades', [])
        except Exception:
            return []
