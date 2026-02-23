import time
import threading
import sqlite3
import logging
import numpy as np
import uuid
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
import os
from kalshi_api import KalshiAPI
from news_fetch import fetch_news
from grok_analysis import analyze_with_grok
from db import init_db, add_trade, get_open_trades, get_performance, close_trade, add_lesson, get_lessons

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
AUTO_TRADE = os.getenv('AUTO_TRADE', 'false').lower() == 'true'
USE_DEMO = os.getenv('USE_DEMO', 'true').lower() == 'true'
CONFIDENCE_THRESHOLD = 0.7
TRADE_SIZE = 1
MONITOR_INTERVAL = 300
VOLATILITY_THRESHOLD = 10

try:
    kalshi = KalshiAPI(use_demo=USE_DEMO)
    logger.info("Kalshi API initialized successfully.")
except Exception as e:
    logger.critical(f"Failed to initialize Kalshi API: {e}")
    raise

db_conn = sqlite3.connect('database.db')
init_db(db_conn)

# Globals
auto_trade_enabled = AUTO_TRADE
pending_trades = {}

def monitor_markets(updater):
    while True:
        try:
            markets = kalshi.get_open_markets()
            logger.info(f"Fetched {len(markets)} open markets.")
            trending = sorted(markets, key=lambda m: m.get('volume', 0), reverse=True)[:5]
            
            for market in trending:
                ticker = market['ticker']
                description = f"{market['title']} - {market['subtitle']}"
                
                try:
                    news = fetch_news(market['title'])
                    logger.debug(f"Fetched news for {ticker}: {len(news)} articles.")
                except Exception as e:
                    logger.error(f"Error fetching news for {ticker}: {e}")
                    continue
                
                try:
                    signal, confidence = analyze_with_grok(description, news, db_conn)
                    logger.info(f"Generated signal for {ticker}: {signal} ({confidence})")
                except Exception as e:
                    logger.error(f"Error analyzing with Grok for {ticker}: {e}")
                    continue
                
                if confidence > CONFIDENCE_THRESHOLD:
                    side = 'yes' if signal == 'YES' else 'no'
                    message = f"Signal for {ticker}: {signal} (Confidence: {confidence})"
                    
                    try:
                        updater.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
                        logger.info(f"Sent Telegram message: {message}")
                    except Exception as e:
                        logger.error(f"Error sending Telegram message: {e}")
                    
                    if auto_trade_enabled:
                        try:
                            price = market['yes_bid'] if side == 'yes' else (100 - market['no_bid'])
                            
                            # Check for anomaly
                            recent_trades = kalshi.get_recent_trades(ticker)
                            anomaly = False
                            if recent_trades:
                                prices = [t['price'] for t in recent_trades if 'price' in t]
                                if len(prices) > 5:
                                    vol = np.std(prices)
                                    if vol > VOLATILITY_THRESHOLD:
                                        anomaly = True
                                        logger.info(f"Anomaly detected for {ticker}: volatility {vol}")
                            
                            if anomaly:
                                # Require manual approval
                                pending_id = str(uuid.uuid4())
                                pending_trades[pending_id] = {
                                    'ticker': ticker,
                                    'side': side,
                                    'count': TRADE_SIZE,
                                    'price': price,
                                    'message': message,
                                    'description': description
                                }
                                keyboard = [
                                    [
                                        InlineKeyboardButton("Go", callback_data=f"go:{pending_id}"),
                                        InlineKeyboardButton("No Go", callback_data=f"no:{pending_id}")
                                    ]
                                ]
                                reply_markup = InlineKeyboardMarkup(keyboard)
                                updater.bot.send_message(
                                    chat_id=TELEGRAM_CHAT_ID,
                                    text=f"Anomaly detected for {ticker}. Approve trade? {message}",
                                    reply_markup=reply_markup
                                )
                            else:
                                # Auto trade
                                order_id = kalshi.place_order(ticker, side, TRADE_SIZE)
                                if order_id:
                                    add_trade(db_conn, ticker, side, TRADE_SIZE, price, time.time(), description)
                                    trade_message = f"Trade placed: {message}"
                                    updater.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=trade_message)
                                    logger.info(trade_message)
                                else:
                                    logger.warning(f"Failed to place order for {ticker}")
                        except Exception as e:
                            logger.error(f"Error placing trade for {ticker}: {e}")
            
            # Check for settled markets
            try:
                settlements = kalshi.get_settlements()
                logger.info(f"Fetched {len(settlements)} settlements.")
                for sett in settlements:
                    ticker = sett['ticker']
                    outcome = sett['outcome']
                    open_trades = get_open_trades(db_conn, ticker)
                    for trade in open_trades:
                        settlement_price = 100 if outcome == trade['side'] else 0
                        close_trade(db_conn, trade['id'], settlement_price)
                        logger.info(f"Closed trade {trade['id']} for {ticker}")
                        
                        # Generate lesson if wrong
                        predicted_side = trade['side']
                        actual_outcome = 'yes' if settlement_price == 100 else 'no'
                        if predicted_side != actual_outcome:
                            lesson_prompt = f"The prediction for market '{trade.get('description', ticker)}' was {predicted_side.upper()}, but actual outcome was {actual_outcome.upper()}. What lesson can be learned?"
                            try:
                                from grok_analysis import client
                                lesson_response = client.chat.completions.create(
                                    model='grok-4',
                                    messages=[{'role': 'user', 'content': lesson_prompt}],
                                    temperature=0.5,
                                    max_tokens=200
                                )
                                lesson = lesson_response.choices[0].message.content.strip()
                                add_lesson(db_conn, ticker, trade.get('description', ''), predicted_side, actual_outcome, lesson)
                                logger.info(f"Added lesson for {ticker}")
                            except Exception as e:
                                logger.error(f"Failed to generate lesson for {ticker}: {e}")
            except Exception as e:
                logger.error(f"Error processing settlements: {e}")
                
        except Exception as e:
            logger.error(f"Error in monitor_markets loop: {e}")
        
        time.sleep(MONITOR_INTERVAL)

def callback_query(update, context):
    query = update.callback_query
    data = query.data
    try:
        if data.startswith('go:'):
            pending_id = data.split(':')[1]
            if pending_id in pending_trades:
                trade_info = pending_trades.pop(pending_id)
                order_id = kalshi.place_order(trade_info['ticker'], trade_info['side'], trade_info['count'])
                if order_id:
                    add_trade(db_conn, trade_info['ticker'], trade_info['side'], trade_info['count'], trade_info['price'], time.time(), trade_info['description'])
                    context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"Approved and placed: {trade_info['message']}")
                else:
                    context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Trade approved but placement failed.")
            else:
                context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Pending trade not found.")
        elif data.startswith('no:'):
            pending_id = data.split(':')[1]
            if pending_id in pending_trades:
                del pending_trades[pending_id]
                context.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="Trade declined.")
        query.answer()
    except Exception as e:
        logger.error(f"Error in callback: {e}")
        query.answer("Error processing.")

def start(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="Welcome! Monitoring Kalshi markets.")
    logger.info("Telegram /start command received.")

def status(update, context):
    open_trades = get_open_trades(db_conn)
    message = f"Auto Trade: {'Enabled' if auto_trade_enabled else 'Disabled'}\nOpen Trades: {len(open_trades)}"
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)
    logger.info("Telegram /status command received.")

def signals(update, context):
    context.bot.send_message(chat_id=update.effective_chat.id, text="No recent signals.")
    logger.info("Telegram /signals command received.")

def toggle_auto(update, context):
    global auto_trade_enabled
    auto_trade_enabled = not auto_trade_enabled
    message = f"Auto Trade: {'Enabled' if auto_trade_enabled else 'Disabled'}"
    context.bot.send_message(chat_id=update.effective_chat.id, text=message)
    logger.info(f"Telegram /toggle_auto: {message}")

def performance(update, context):
    try:
        perf = get_performance(db_conn)
        message = f"Win Rate: {perf['win_rate']}%\nTotal P&L: ${perf['pnl']}"
        context.bot.send_message(chat_id=update.effective_chat.id, text=message)
        logger.info("Telegram /performance command received.")
    except Exception as e:
        logger.error(f"Error getting performance: {e}")
        context.bot.send_message(chat_id=update.effective_chat.id, text="Error retrieving performance.")

if __name__ == '__main__':
    try:
        updater = Updater(token=TELEGRAM_TOKEN, use_context=True)
        dispatcher = updater.dispatcher
        dispatcher.add_handler(CommandHandler('start', start))
        dispatcher.add_handler(CommandHandler('status', status))
        dispatcher.add_handler(CommandHandler('signals', signals))
        dispatcher.add_handler(CommandHandler('toggle_auto', toggle_auto))
        dispatcher.add_handler(CommandHandler('performance', performance))
        dispatcher.add_handler(CallbackQueryHandler(callback_query))
        
        updater.start_polling()
        logger.info("Telegram bot started polling.")
        
        threading.Thread(target=monitor_markets, args=(updater,)).start()
        logger.info("Market monitoring thread started.")
    except Exception as e:
        logger.critical(f"Failed to start application: {e}")
