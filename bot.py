"""
Kalshi Trading Bot - Main Entry Point

Usage:
    python bot.py --demo        # Use demo environment
    python bot.py --live       # Use production (real money!)
    python bot.py --balance    # Check balance only
"""

import os
import sys
import argparse
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from client import KalshiBotClient
from config import Config


def main():
    parser = argparse.ArgumentParser(description="Kalshi Trading Bot")
    parser.add_argument("--demo", action="store_true", help="Use demo environment")
    parser.add_argument("--live", action="store_true", help="Use production environment")
    parser.add_argument("--balance", action="store_true", help="Check balance and exit")
    parser.add_argument("--markets", action="store_true", help="List markets and exit")
    parser.add_argument("--events", action="store_true", help="List events and exit")
    args = parser.parse_args()
    
    # Determine environment
    if args.demo:
        env = "demo"
    elif args.live:
        env = "production"
    else:
        env = "demo"  # Default to demo for safety
    
    print(f"🔧 Initializing bot in {env.upper()} mode...")
    
    # Load config
    config = Config(env=env)
    
    # Initialize client
    client = KalshiBotClient(config)
    
    # Test connection
    print("📡 Testing connection...")
    if not client.test_connection():
        print("❌ Failed to connect to Kalshi API")
        sys.exit(1)
    
    print("✅ Connected successfully!")
    
    # Show balance
    balance = client.get_balance()
    print(f"💰 Balance: ${balance.balance / 100:.2f}")
    
    if args.balance:
        sys.exit(0)
    
    # List events
    if args.events:
        events = client.get_events(limit=10)
        print(f"\n📊 Top Events:")
        for event in events:
            print(f"  - {event.event_id}: {event.title}")
        sys.exit(0)
    
    # List markets
    if args.markets:
        markets = client.get_markets(limit=10)
        print(f"\n📊 Top Markets:")
        for market in markets:
            print(f"  - {market.ticker}: {market.title} (${market.yes_bid}/{market.no_bid})")
        sys.exit(0)
    
    # Main trading loop (placeholder for now)
    print("\n🚀 Bot initialized and ready!")
    print("   Use --events, --markets, or --balance to query data")
    print("   Trading logic coming soon...")


if __name__ == "__main__":
    main()
