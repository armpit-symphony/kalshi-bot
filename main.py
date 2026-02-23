"""AI-Powered Prediction Market Trading Tool

Main entry point for the trading bot.
"""

import os
import sys
import time
import threading
import sqlite3
from telegram.ext import Updater, CommandHandler, MessageHandler, filters as FiltersModule
from dotenv import load_dotenv

from kalshi_api import KalshiAPI
from news_fetch import NewsFetcher
from grok_analysis import GrokAnalyzer
from db import init_db, add_trade, get_open_trades, get_performance, close_trade

# Load environment variables
load_dotenv()

# Configuration
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
KALSHI_KEY_ID = os.getenv('KALSHI_KEY_ID', '')
KALSHI_PRIVATE_KEY = os.getenv('KALSHI_PRIVATE_KEY', '')
XAI_API_KEY = os.getenv('XAI_API_KEY', '')
NEWSAPI_KEY = os.getenv('NEWSAPI_KEY', '')

# Trading settings
USE_DEMO = os.getenv('USE_DEMO', 'true').lower() == 'true'
AUTO_TRADE = os.getenv('AUTO_TRADE', 'false').lower() == 'true'
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.7'))
TRADE_SIZE = int(os.getenv('TRADE_SIZE', '1'))
MONITOR_INTERVAL = int(os.getenv('MONITOR_INTERVAL', '300'))  # 5 minutes

# Global state
auto_trade_enabled = AUTO_TRADE
db_conn = None
kalshi = None
news_fetcher = None
grok_analyzer = None


def initialize():
    """Initialize all clients and database."""
    global kalshi, news_fetcher, grok_analyzer, db_conn
    
    print("Initializing...")
    
    # Initialize database
    db_conn = sqlite3.connect('database.db')
    init_db(db_conn)
    print("✓ Database initialized")
    
    # Initialize Kalshi client
    kalshi = KalshiAPI(
        api_key_id=KALSHI_KEY_ID,
        private_key_pem=KALSHI_PRIVATE_KEY,
        use_demo=USE_DEMO
    )
    print("✓ Kalshi API connected")
    
    # Initialize news fetcher
    if NEWSAPI_KEY:
        news_fetcher = NewsFetcher(NEWSAPI_KEY)
        print("✓ News fetcher initialized")
    
    # Initialize Grok analyzer
    if XAI_API_KEY:
        grok_analyzer = GrokAnalyzer(XAI_API_KEY)
        print("✓ Grok analyzer initialized")
    
    print(f"Demo mode: {USE_DEMO}")
    print(f"Auto trade: {AUTO_TRADE}")


def get_trending_markets(max_markets: int = 5):
    """Get top trending markets by volume."""
    try:
        markets = kalshi.get_open_markets(limit=100)
        # Sort by volume (if available) and take top N
        sorted_markets = sorted(
            markets,
            key=lambda m: m.get('volume24hr', 0),
            reverse=True
        )
        return sorted_markets[:max_markets]
    except Exception as e:
        print(f"Error fetching markets: {e}")
        return []


def analyze_market(market: dict) -> tuple:
    """Analyze a market and return signal."""
    ticker = market.get('ticker', '')
    title = market.get('title', '')
    subtitle = market.get('subtitle', '')
    
    # Fetch news if available
    news = []
    if news_fetcher and title:
        try:
            news = news_fetcher.fetch_news(title, max_results=3)
        except Exception as e:
            print(f"News fetch error for {title}: {e}")
    
    # Analyze with Grok if available
    if grok_analyzer:
        try:
            signal, confidence = grok_analyzer.analyze(
                market_title=title,
                market_description=subtitle,
                news=news
            )
            return signal, confidence
        except Exception as e:
            print(f"Grok analysis error: {e}")
    
    return 'HOLD', 0.0


def execute_trade(ticker: str, side: str, price: float) -> bool:
    """Execute a trade and record it."""
    try:
        order_id = kalshi.place_order(
            ticker=ticker,
            side=side,
            count=TRADE_SIZE,
            order_type='market'
        )
        
        if order_id:
            # Record the trade
            trade_id = add_trade(
                conn=db_conn,
                ticker=ticker,
                side=side,
                count=TRADE_SIZE,
                price=price,
                timestamp=time.time()
            )
            print(f"✓ Trade executed: {ticker} {side} x{TRADE_SIZE} (ID: {trade_id})")
            return True
        
        return False
    except Exception as e:
        print(f"Trade execution error: {e}")
        return False


def monitor_markets(updater):
    """Main monitoring loop."""
    global auto_trade_enabled
    
    while True:
        try:
            print("\n" + "="*50)
            print("Scanning markets...")
            
            # Get trending markets
            trending = get_trending_markets(5)
            
            if not trending:
                print("No markets found")
                time.sleep(MONITOR_INTERVAL)
                continue
            
            signals_generated = 0
            
            for market in trending:
                ticker = market.get('ticker', '')
                title = market.get('title', '')
                yes_bid = market.get('yes_bid', 0)
                no_bid = market.get('no_bid', 0)
                
                print(f"\nAnalyzing: {ticker} - {title}")
                
                # Analyze
                signal, confidence = analyze_market(market)
                
                print(f"  Signal: {signal} (Confidence: {confidence:.2f})")
                
                # Check if signal meets threshold
                if confidence >= CONFIDENCE_THRESHOLD and signal in ('YES', 'NO'):
                    signals_generated += 1
                    
                    # Determine price
                    price = yes_bid if signal == 'YES' else no_bid
                    
                    # Format message
                    message = (
                        f"📊 Signal for {ticker}\n"
                        f"Market: {title}\n"
                        f"Signal: {signal.upper()}\n"
                        f"Confidence: {confidence:.0%}\n"
                        f"Price: ${price/100:.2f}"
                    )
                    
                    # Send to Telegram
                    if TELEGRAM_TOKEN:
                        try:
                            updater.bot.send_message(
                                chat_id=TELEGRAM_TOKEN.split(':')[0] if ':' in TELEGRAM_TOKEN else TELEGRAM_TOKEN,
                                text=message
                            )
                        except Exception as e:
                            print(f"Telegram send error: {e}")
                    
                    # Auto-trade if enabled
                    if auto_trade_enabled:
                        success = execute_trade(ticker, signal.lower(), price)
                        if success:
                            trade_msg = f"✅ Trade placed: {signal} {ticker}"
                            if TELEGRAM_TOKEN:
                                try:
                                    updater.bot.send_message(
                                        chat_id=TELEGRAM_TOKEN.split(':')[0] if ':' in TELEGRAM_TOKEN else TELEGRAM_TOKEN,
                                        text=trade_msg
                                    )
                                except:
                                    pass
            
            print(f"\nSignals generated: {signals_generated}")
            
        except Exception as e:
            print(f"Monitor error: {e}")
        
        time.sleep(MONITOR_INTERVAL)


# Telegram Command Handlers
def start(update, context):
    """Handle /start command."""
    update.message.reply_text(
        "🤖 AI Prediction Market Trader\n\n"
        "Commands:\n"
        "/start - Show this message\n"
        "/status - Show bot status\n"
        "/markets - Show trending markets\n"
        "/signals - Show recent signals\n"
        "/toggle_auto - Toggle auto-trading\n"
        "/performance - Show performance stats"
    )


def status_command(update, context):
    """Handle /status command."""
    msg = f"🤖 Status\n\n"
    msg += f"Demo Mode: {'Yes' if USE_DEMO else 'No'}\n"
    msg += f"Auto Trade: {'Enabled' if auto_trade_enabled else 'Disabled'}\n"
    msg += f"Confidence Threshold: {CONFIDENCE_THRESHOLD:.0%}\n"
    msg += f"Trade Size: {TRADE_SIZE} contracts"
    update.message.reply_text(msg)


def markets_command(update, context):
    """Handle /markets command."""
    update.message.reply_text("Fetching markets...")
    
    markets = get_trending_markets(5)
    
    if not markets:
        update.message.reply_text("No markets available")
        return
    
    msg = "📊 Top 5 Trending Markets\n\n"
    for i, m in enumerate(markets, 1):
        ticker = m.get('ticker', 'N/A')
        title = m.get('title', 'N/A')[:40]
        yes_bid = m.get('yes_bid', 0)
        no_bid = m.get('no_bid', 0)
        volume = m.get('volume24hr', 0)
        
        msg += f"{i}. {ticker}\n"
        msg += f"   {title}\n"
        msg += f"   YES: ${yes_bid/100:.2f} | NO: ${no_bid/100:.2f}\n"
        msg += f"   Volume: ${volume/100:.0f}\n\n"
    
    update.message.reply_text(msg)


def signals_command(update, context):
    """Handle /signals command."""
    update.message.reply_text("Use /markets to get current analysis")


def toggle_auto_command(update, context):
    """Handle /toggle_auto command."""
    global auto_trade_enabled
    auto_trade_enabled = not auto_trade_enabled
    update.message.reply_text(
        f"Auto Trading: {'Enabled' if auto_trade_enabled else 'Disabled'}"
    )


def performance_command(update, context):
    """Handle /performance command."""
    perf = get_performance(db_conn)
    
    msg = (
        f"📈 Performance\n\n"
        f"Total Trades: {perf['total_trades']}\n"
        f"Wins: {perf['wins']} | Losses: {perf['losses']}\n"
        f"Win Rate: {perf['win_rate']}%\n"
        f"P&L: ${perf['pnl']:.2f}"
    )
    update.message.reply_text(msg)


def main():
    """Main entry point."""
    global db_conn
    
    # Initialize
    initialize()
    
    # Set up Telegram bot
    if not TELEGRAM_TOKEN:
        print("⚠️ No Telegram token - running without bot")
        # Run monitor without Telegram
        monitor_markets(None)
        return
    
    # Create updater
    updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
    dispatcher = updater.dispatcher
    
    # Add command handlers
    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(CommandHandler('status', status_command))
    dispatcher.add_handler(CommandHandler('markets', markets_command))
    dispatcher.add_handler(CommandHandler('signals', signals_command))
    dispatcher.add_handler(CommandHandler('toggle_auto', toggle_auto_command))
    dispatcher.add_handler(CommandHandler('performance', performance_command))
    
    # Start polling
    updater.start_polling()
    print("✓ Telegram bot started")
    
    # Start monitoring in background
    monitor_thread = threading.Thread(target=monitor_markets, args=(updater,))
    monitor_thread.daemon = True
    monitor_thread.start()
    
    print("\n🤖 Bot is running. Press Ctrl+C to stop.")
    
    # Keep running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        if db_conn:
            db_conn.close()
        updater.stop()


if __name__ == '__main__':
    main()
