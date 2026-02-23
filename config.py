"""Configuration for Kalshi Bot"""

import os
from pathlib import Path


class Config:
    """Bot configuration."""
    
    # API Endpoints - use demo for now
    DEMO_HOST = "https://demo-api.kalshi.co"
    PRODUCTION_HOST = "https://api.elections.kalshi.com"
    
    def __init__(self, env: str = "demo"):
        """Initialize configuration."""
        self.env = env
        
        # Set host
        if env == "production":
            self.host = self.PRODUCTION_HOST
        else:
            self.host = self.DEMO_HOST
        
        # Load API credentials
        self.api_key_id = os.environ.get("KALSHI_API_KEY_ID")
        self.pem_path = os.environ.get("KALSHI_PEM_PATH", "/home/sparky/.keys/kalshi.pem")
        
        # Validate credentials exist
        if not self.api_key_id:
            raise ValueError("KALSHI_API_KEY_ID not set in environment")
        
        if not Path(self.pem_path).exists():
            raise ValueError(f"PEM file not found at {self.pem_path}")
        
        # Load PEM content
        with open(self.pem_path, "r") as f:
            self.private_key_pem = f.read()
        
        # Trading parameters
        self.max_bet_amount = float(os.environ.get("MAX_BET_AMOUNT", "25.0"))
        self.skip_existing = os.environ.get("SKIP_EXISTING", "true").lower() == "true"
    
    def __repr__(self):
        return f"Config(env={self.env}, host={self.host})"
