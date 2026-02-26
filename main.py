import time
import threading
import sqlite3
import logging
import asyncio
import numpy as np
import uuid
import math
import re
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from dotenv import load_dotenv
import os
from kalshi_api import KalshiAPI
from news_fetch import fetch_news
from grok_analysis import analyze_with_grok
from db import (
    init_db,
    add_trade,
    add_signal,
    get_open_trades,
    get_open_trades_count,
    has_open_trade,
    get_last_trade_time,
    count_trades_since,
    get_performance,
    get_edge_report,
    close_trade,
    add_lesson,
    get_lessons,
)


class _RedactSecretsFilter(logging.Filter):
    _patterns = [
        re.compile(r"(bot)\d+:[A-Za-z0-9_\-]+", re.IGNORECASE),
        re.compile(r"(Bearer)\s+[A-Za-z0-9_\-\.]+", re.IGNORECASE),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            redacted = msg
            for pat in self._patterns:
                redacted = pat.sub(r"\1<redacted>", redacted)
            if redacted != msg:
                record.msg = redacted
                record.args = ()
        except Exception:
            pass
        return True


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
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_RedactSecretsFilter())
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)

load_dotenv(dotenv_path='/home/sparky/.keys/kalshi.env')
load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
AUTO_TRADE = os.getenv('AUTO_TRADE', 'false').lower() == 'true'
USE_DEMO = os.getenv('USE_DEMO', 'true').lower() == 'true'
CONFIDENCE_THRESHOLD = float(os.getenv('CONFIDENCE_THRESHOLD', '0.7'))
EDGE_THRESHOLD = float(os.getenv('EDGE_THRESHOLD', os.getenv('MIN_EDGE', '0.05')))
TRADE_SIZE = int(os.getenv('TRADE_SIZE', '1'))
MONITOR_INTERVAL = int(os.getenv('MONITOR_INTERVAL', '300'))
VOLATILITY_THRESHOLD = float(os.getenv('VOLATILITY_THRESHOLD', '10'))
MIN_VOLUME = int(os.getenv('MIN_VOLUME', '100'))
MAX_SPREAD = float(os.getenv('MAX_SPREAD', '15'))
MAX_TRADES_PER_CYCLE = int(os.getenv('MAX_TRADES_PER_CYCLE', '3'))
MAX_OPEN_POSITIONS = int(os.getenv('MAX_OPEN_POSITIONS', '5'))
MAX_TRADES_PER_DAY = int(os.getenv('MAX_TRADES_PER_DAY', '10'))
TICKER_COOLDOWN_HOURS = int(os.getenv('TICKER_COOLDOWN_HOURS', '6'))
ALLOW_MULTIPLE_PER_EVENT = os.getenv('ALLOW_MULTIPLE_PER_EVENT', 'false').lower() == 'true'
LIMIT_ORDER_TIMEOUT = int(os.getenv('LIMIT_ORDER_TIMEOUT', '60'))

NEWSAPI_KEY = os.getenv('NEWSAPI_KEY')
XAI_API_KEY = os.getenv('XAI_API_KEY')
KALSHI_API_KEY_ID = os.getenv('KALSHI_API_KEY_ID')
KALSHI_PEM_PATH = os.getenv('KALSHI_PEM_PATH', '/home/sparky/.keys/kalshi.pem')

MAX_COMBO_POSITIONS = int(os.getenv('MAX_COMBO_POSITIONS', '6'))
HIGH_CONFIDENCE_THRESHOLD = float(os.getenv('HIGH_CONFIDENCE_THRESHOLD', '0.9'))
MAX_TOTAL_POSITIONS = int(os.getenv('MAX_TOTAL_POSITIONS', '10'))
CATEGORIES_TO_INCLUDE = os.getenv('CATEGORIES_TO_INCLUDE', 'all')
DIVERSIFY_SELECTION = os.getenv('DIVERSIFY_SELECTION', 'true').lower() == 'true'

try:
    with open(KALSHI_PEM_PATH, 'r') as f:
        private_key_pem = f.read()
    kalshi = KalshiAPI(api_key_id=KALSHI_API_KEY_ID, private_key_pem=private_key_pem, use_demo=USE_DEMO)
    logger.info("Kalshi API initialized successfully.")
except Exception:
    # Avoid logging exception details that may contain key material
    logger.critical("Failed to initialize Kalshi API. Check credentials and PEM file.")
    raise

db_conn = sqlite3.connect('database.db', check_same_thread=False)
init_db(db_conn)

# Globals
auto_trade_enabled = AUTO_TRADE
pending_trades = {}
_app = None  # telegram Application instance


async def send_message(text, reply_markup=None):
    """Send a Telegram message if token is configured."""
    if _app and TELEGRAM_CHAT_ID:
        try:
            await _app.bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=text, reply_markup=reply_markup)
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")


def _start_of_day_ts() -> float:
    now = time.localtime()
    start = time.struct_time((
        now.tm_year, now.tm_mon, now.tm_mday,
        0, 0, 0,
        now.tm_wday, now.tm_yday, now.tm_isdst
    ))
    return time.mktime(start)


def _score_signal(sig: dict) -> float:
    edge = sig.get('edge', 0.0)
    volume = sig.get('volume', 0) or 0
    return edge * math.log1p(volume)


def _best_level_price(levels, side: str):
    if not levels:
        return None
    if isinstance(levels, dict):
        levels = levels.get(side) or levels.get('levels') or []
    for lvl in levels:
        if isinstance(lvl, dict):
            price = lvl.get('price')
        elif isinstance(lvl, (list, tuple)) and lvl:
            price = lvl[0]
        else:
            price = None
        if price is not None:
            return price
    return None


def _get_market_pricing(market: dict, ticker: str) -> dict:
    pricing = {
        'yes_bid': market.get('yes_bid'),
        'yes_ask': market.get('yes_ask'),
        'no_bid': market.get('no_bid'),
        'no_ask': market.get('no_ask'),
        'volume': market.get('volume'),
        'open_interest': market.get('open_interest'),
    }

    if pricing['yes_ask'] is None or pricing['no_ask'] is None:
        try:
            orderbook = kalshi.get_market_orderbook(ticker)
            yes_book = orderbook.get('yes') or orderbook.get('yes_orders') or orderbook.get('yes_book') or {}
            no_book = orderbook.get('no') or orderbook.get('no_orders') or orderbook.get('no_book') or {}
            pricing['yes_bid'] = pricing['yes_bid'] or _best_level_price(yes_book, 'bids')
            pricing['yes_ask'] = pricing['yes_ask'] or _best_level_price(yes_book, 'asks')
            pricing['no_bid'] = pricing['no_bid'] or _best_level_price(no_book, 'bids')
            pricing['no_ask'] = pricing['no_ask'] or _best_level_price(no_book, 'asks')
        except Exception as e:
            logger.debug(f"Orderbook fetch failed for {ticker}: {e}")
    return pricing


def _compute_edge(signal: str, confidence: float, pricing: dict):
    yes_ask = pricing.get('yes_ask')
    no_ask = pricing.get('no_ask')
    if yes_ask is None or no_ask is None:
        return None
    try:
        yes_ask = float(yes_ask)
        no_ask = float(no_ask)
    except Exception:
        return None
    model_yes = confidence if signal == 'YES' else (1.0 - confidence)
    if signal == 'YES':
        implied = yes_ask / 100.0
        edge = model_yes - implied
    else:
        implied = 1.0 - (no_ask / 100.0)
        edge = (1.0 - model_yes) - no_ask / 100.0
    return implied, edge


def _spread_ok(signal: str, pricing: dict) -> bool:
    if signal == 'YES':
        bid = pricing.get('yes_bid')
        ask = pricing.get('yes_ask')
    else:
        bid = pricing.get('no_bid')
        ask = pricing.get('no_ask')
    if bid is None or ask is None:
        return False
    try:
        bid = float(bid)
        ask = float(ask)
    except Exception:
        return False
    return (ask - bid) <= MAX_SPREAD


def _get_open_positions_count() -> int:
    try:
        positions = kalshi.get_positions()
        active = []
        for p in positions:
            qty = (
                p.get('position') or
                p.get('net_position') or
                p.get('count') or
                p.get('quantity') or
                0
            )
            try:
                if abs(float(qty)) > 0:
                    active.append(p)
            except Exception:
                continue
        return len(active)
    except Exception:
        return get_open_trades_count(db_conn)


def cancel_order_if_open(order_id: str, timeout_seconds: int):
    """Cancel order if it is still open after timeout."""
    try:
        time.sleep(timeout_seconds)
        try:
            open_orders = kalshi.get_orders(status='open')
        except Exception as e:
            logger.error(f"Failed to fetch open orders for cancel check: {e}")
            return
        if any(o.get('order_id') == order_id for o in open_orders):
            if kalshi.cancel_order(order_id):
                logger.info(f"Canceled stale order {order_id} after {timeout_seconds}s")
            else:
                logger.warning(f"Failed to cancel stale order {order_id}")
    except Exception as e:
        logger.error(f"Error in cancel_order_if_open: {e}")


def monitor_markets():
    from collections import defaultdict
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    while True:
        try:
            markets = kalshi.get_open_markets()
            logger.info(f"Fetched {len(markets)} open markets.")

            # --- Market Selection ---
            include_categories = None
            if CATEGORIES_TO_INCLUDE and CATEGORIES_TO_INCLUDE.lower() != 'all':
                include_categories = {c.strip().lower() for c in CATEGORIES_TO_INCLUDE.split(',') if c.strip()}
                markets = [m for m in markets if str(m.get('category', '')).lower() in include_categories]

            if DIVERSIFY_SELECTION:
                categories = defaultdict(list)
                for m in markets:
                    cat = m.get('category', 'unknown')
                    categories[cat].append(m)
                selected = []
                for cat, cat_markets in categories.items():
                    top2 = sorted(cat_markets, key=lambda m: m.get('volume', 0), reverse=True)[:2]
                    selected.extend(top2)
                trending = sorted(selected, key=lambda m: m.get('volume', 0), reverse=True)[:MAX_TOTAL_POSITIONS]
                logger.info(f"Diversified selection: {len(trending)} markets from {len(categories)} categories")
            else:
                trending = sorted(markets, key=lambda m: m.get('volume', 0), reverse=True)[:5]

            # --- Collect all signals before processing trades ---
            raw_signals = []
            seen_events = set()
            for market in trending:
                ticker = market['ticker']
                rules = market.get('rules_primary', '')
                description = rules or f"{market['title']} - {market.get('subtitle', '')}"
                search_query = market['title']
                event_key = market.get('event_ticker') or market.get('event_id') or market.get('event') or market.get('title')

                if not ALLOW_MULTIPLE_PER_EVENT and event_key in seen_events:
                    continue

                volume = market.get('volume', 0)
                if volume is not None and volume < MIN_VOLUME:
                    continue

                if has_open_trade(db_conn, ticker):
                    continue

                last_ts = get_last_trade_time(db_conn, ticker)
                if last_ts:
                    cooldown_seconds = TICKER_COOLDOWN_HOURS * 3600
                    if time.time() - last_ts < cooldown_seconds:
                        continue

                try:
                    news = fetch_news(search_query, api_key=NEWSAPI_KEY) if NEWSAPI_KEY else []
                    logger.debug(f"Fetched news for {ticker}: {len(news)} articles.")
                except Exception as e:
                    logger.error(f"Error fetching news for {ticker}: {e}")
                    news = []

                pricing = _get_market_pricing(market, ticker)
                if not pricing or pricing.get("yes_ask") is None or pricing.get("no_ask") is None:
                    continue

                if not XAI_API_KEY:
                    continue
                try:
                    signal, confidence = analyze_with_grok(
                        market.get('title', ''),
                        description,
                        news,
                        XAI_API_KEY,
                        market_meta=pricing,
                    )
                    logger.info(f"Generated signal for {ticker}: {signal} ({confidence})")
                except Exception as e:
                    logger.error(f"Error analyzing with Grok for {ticker}: {e}")
                    continue

                if signal not in ("YES", "NO"):
                    continue

                if confidence >= CONFIDENCE_THRESHOLD:
                    edge_info = _compute_edge(signal, confidence, pricing)
                    if not edge_info:
                        continue
                    implied_prob, edge = edge_info
                    if edge < EDGE_THRESHOLD:
                        continue
                    spread_ok = _spread_ok(signal, pricing)
                    if not spread_ok:
                        continue

                    side = 'yes' if signal == 'YES' else 'no'
                    best_ask = pricing.get('yes_ask') if side == 'yes' else pricing.get('no_ask')
                    market_prob = (best_ask / 100.0) if best_ask is not None else None
                    try:
                        add_signal(
                            db_conn,
                            ticker,
                            side,
                            signal,
                            confidence,
                            confidence,
                            market_prob if market_prob is not None else 0.0,
                            edge,
                            best_ask,
                            time.time(),
                            description,
                        )
                    except Exception as e:
                        logger.error(f"Failed to log signal for {ticker}: {e}")

                    raw_signals.append({
                        'market': market,
                        'ticker': ticker,
                        'description': description,
                        'signal': signal,
                        'confidence': confidence,
                        'edge': edge,
                        'implied_prob': implied_prob,
                        'volume': volume,
                        'pricing': pricing,
                    })
                    if not ALLOW_MULTIPLE_PER_EVENT:
                        seen_events.add(event_key)

            # --- Apply combo limits ---
            if len(raw_signals) > MAX_COMBO_POSITIONS:
                avg_conf = sum(s['confidence'] for s in raw_signals) / len(raw_signals)
                if avg_conf > HIGH_CONFIDENCE_THRESHOLD:
                    final_signals = sorted(raw_signals, key=lambda s: _score_signal(s), reverse=True)[:MAX_TOTAL_POSITIONS]
                    combo_msg = (
                        f"Large combo approved: {len(final_signals)} signals "
                        f"(avg confidence {avg_conf:.2f} > {HIGH_CONFIDENCE_THRESHOLD})"
                    )
                    logger.info(combo_msg)
                    loop.run_until_complete(send_message(combo_msg))
                else:
                    final_signals = sorted(raw_signals, key=lambda s: _score_signal(s), reverse=True)[:MAX_COMBO_POSITIONS]
                    combo_msg = (
                        f"Combo limited: {len(raw_signals)} signals trimmed to {MAX_COMBO_POSITIONS} "
                        f"(avg confidence {avg_conf:.2f} <= {HIGH_CONFIDENCE_THRESHOLD})"
                    )
                    logger.info(combo_msg)
                    loop.run_until_complete(send_message(combo_msg))
            else:
                final_signals = sorted(raw_signals, key=lambda s: _score_signal(s), reverse=True)

            # --- Enforce global risk limits ---
            open_positions = _get_open_positions_count()
            if open_positions >= MAX_OPEN_POSITIONS:
                logger.info(f"Open positions {open_positions} >= max {MAX_OPEN_POSITIONS}. Skipping trades.")
                time.sleep(MONITOR_INTERVAL)
                continue

            start_of_day = _start_of_day_ts()
            trades_today = count_trades_since(db_conn, start_of_day)
            if trades_today >= MAX_TRADES_PER_DAY:
                logger.info(f"Daily trade cap reached ({trades_today}/{MAX_TRADES_PER_DAY}).")
                time.sleep(MONITOR_INTERVAL)
                continue

            available_slots = min(
                MAX_TRADES_PER_CYCLE,
                MAX_OPEN_POSITIONS - open_positions,
                MAX_TRADES_PER_DAY - trades_today,
            )
            if available_slots <= 0:
                time.sleep(MONITOR_INTERVAL)
                continue
            final_signals = final_signals[:available_slots]

            # --- Process final signals ---
            for sig in final_signals:
                market = sig['market']
                ticker = sig['ticker']
                description = sig['description']
                signal = sig['signal']
                confidence = sig['confidence']
                edge = sig['edge']
                implied_prob = sig['implied_prob']
                side = 'yes' if signal == 'YES' else 'no'
                message = (
                    f"Signal for {ticker}: {signal} "
                    f"(Conf: {confidence:.2f}, Edge: {edge:.2f}, Implied: {implied_prob:.2f})"
                )

                loop.run_until_complete(send_message(message))

                if auto_trade_enabled:
                    try:
                        pricing = sig.get('pricing', {})
                        price = pricing.get('yes_ask') if side == 'yes' else pricing.get('no_ask')
                        if price is None:
                            continue

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
                                'description': description,
                                'model_prob': confidence,
                                'market_prob': price / 100.0,
                                'edge': edge,
                            }
                            keyboard = [[
                                InlineKeyboardButton("Go", callback_data=f"go:{pending_id}"),
                                InlineKeyboardButton("No Go", callback_data=f"no:{pending_id}")
                            ]]
                            reply_markup = InlineKeyboardMarkup(keyboard)
                            loop.run_until_complete(send_message(
                                f"Anomaly detected for {ticker}. Approve trade? {message}",
                                reply_markup=reply_markup
                            ))
                        else:
                            # Auto trade
                            order_id = kalshi.place_order(
                                ticker,
                                side,
                                TRADE_SIZE,
                                order_type='limit',
                                price=max(1, min(99, int(price))),
                            )
                            if order_id:
                                add_trade(
                                    db_conn,
                                    ticker,
                                    side,
                                    TRADE_SIZE,
                                    price,
                                    time.time(),
                                    description,
                                    model_prob=confidence,
                                    market_prob=price / 100.0,
                                    edge=edge,
                                )
                                loop.run_until_complete(send_message(f"Trade placed: {message}"))
                                logger.info(f"Trade placed: {message}")
                                threading.Thread(
                                    target=cancel_order_if_open,
                                    args=(order_id, LIMIT_ORDER_TIMEOUT),
                                    daemon=True
                                ).start()
                            else:
                                logger.warning(f"Failed to place order for {ticker}")
                    except Exception as e:
                        logger.error(f"Error placing trade for {ticker}: {e}")

            # Check for settled markets
            try:
                settlements = kalshi.get_settlements()
                logger.info(f"Fetched {len(settlements)} settlements.")
                for sett in settlements:
                    ticker = sett.get('ticker')
                    if not ticker:
                        continue
                    outcome = (
                        sett.get('outcome')
                        or sett.get('result')
                        or sett.get('side')
                        or sett.get('market_result')
                    )
                    if not outcome and 'value' in sett:
                        try:
                            outcome = 'yes' if float(sett['value']) >= 50 else 'no'
                        except Exception:
                            outcome = None
                    if not outcome and 'settlement_price' in sett:
                        try:
                            outcome = 'yes' if float(sett['settlement_price']) >= 50 else 'no'
                        except Exception:
                            outcome = None
                    if not outcome:
                        logger.warning(f"Settlement missing outcome for {ticker}")
                        continue
                    outcome = outcome.lower()
                    open_trades = get_open_trades(db_conn, ticker)
                    for trade in open_trades:
                        # trade tuple: id(0), ticker(1), side(2), count(3), price(4),
                        #              description(5), timestamp(6), status(7), settlement_price(8)
                        settlement_price = 100 if outcome == trade[2] else 0
                        close_trade(db_conn, trade[0], settlement_price)
                        logger.info(f"Closed trade {trade[0]} for {ticker}")

                        # Generate lesson if wrong
                        predicted_side = trade[2]
                        actual_outcome = 'yes' if settlement_price == 100 else 'no'
                        if predicted_side != actual_outcome:
                            lesson_prompt = (
                                f"The prediction for market '{trade[5] or ticker}' was "
                                f"{predicted_side.upper()}, but actual outcome was {actual_outcome.upper()}. "
                                "What lesson can be learned?"
                            )
                            try:
                                if not XAI_API_KEY:
                                    continue
                                import requests as _requests
                                _resp = _requests.post(
                                    'https://api.x.ai/v1/chat/completions',
                                    headers={'Authorization': f'Bearer {XAI_API_KEY}', 'Content-Type': 'application/json'},
                                    json={'model': 'grok-3-mini', 'messages': [{'role': 'user', 'content': lesson_prompt}], 'temperature': 0.5, 'max_tokens': 200},
                                    timeout=30
                                )
                                _resp.raise_for_status()
                                lesson = _resp.json()['choices'][0]['message']['content'].strip()
                                add_lesson(db_conn, ticker, trade[5] or '', predicted_side, actual_outcome, lesson)
                                logger.info(f"Added lesson for {ticker}")
                            except Exception as e:
                                logger.error(f"Failed to generate lesson for {ticker}: {e}")
            except Exception as e:
                logger.error(f"Error processing settlements: {e}")

        except Exception as e:
            logger.error(f"Error in monitor_markets loop: {e}")

        time.sleep(MONITOR_INTERVAL)


async def cmd_start(update, context):
    await update.message.reply_text("Welcome! Monitoring Kalshi markets.")
    logger.info("Telegram /start command received.")


async def cmd_status(update, context):
    open_trades = get_open_trades(db_conn)
    await update.message.reply_text(
        f"Auto Trade: {'Enabled' if auto_trade_enabled else 'Disabled'}\nOpen Trades: {len(open_trades)}"
    )


async def cmd_signals(update, context):
    await update.message.reply_text("No recent signals.")


async def cmd_toggle_auto(update, context):
    global auto_trade_enabled
    auto_trade_enabled = not auto_trade_enabled
    await update.message.reply_text(f"Auto Trade: {'Enabled' if auto_trade_enabled else 'Disabled'}")
    logger.info(f"Auto trade toggled: {auto_trade_enabled}")


async def cmd_performance(update, context):
    try:
        perf = get_performance(db_conn)
        await update.message.reply_text(f"Win Rate: {perf['win_rate']}%\nTotal P&L: ${perf['pnl']}")
    except Exception as e:
        logger.error(f"Error getting performance: {e}")
        await update.message.reply_text("Error retrieving performance.")


async def cmd_edge_report(update, context):
    try:
        report = get_edge_report(db_conn)
        if not report:
            message = "No edge data yet."
        else:
            lines = ["Edge report (closed trades):"]
            for r in report:
                lines.append(f"{r['range']}: trades={r['trades']} win={r['win_rate']}% avg_pnl={r['avg_pnl']}")
            message = "\n".join(lines)
        await update.message.reply_text(message)
        logger.info("Telegram /edge_report command received.")
    except Exception as e:
        logger.error(f"Error getting edge report: {e}")
        await update.message.reply_text("Error retrieving edge report.")


async def callback_query(update, context):
    query = update.callback_query
    data = query.data
    try:
        if data.startswith('go:'):
            pending_id = data.split(':')[1]
            if pending_id in pending_trades:
                trade_info = pending_trades.pop(pending_id)
                order_id = kalshi.place_order(
                    trade_info['ticker'],
                    trade_info['side'],
                    trade_info['count'],
                    order_type='limit',
                    price=max(1, min(99, int(trade_info['price'] or 50))),
                )
                if order_id:
                    add_trade(
                        db_conn,
                        trade_info['ticker'],
                        trade_info['side'],
                        trade_info['count'],
                        trade_info['price'],
                        time.time(),
                        trade_info['description'],
                        model_prob=trade_info.get('model_prob'),
                        market_prob=trade_info.get('market_prob'),
                        edge=trade_info.get('edge'),
                    )
                    await query.message.reply_text(f"Approved and placed: {trade_info['message']}")
                    threading.Thread(
                        target=cancel_order_if_open,
                        args=(order_id, LIMIT_ORDER_TIMEOUT),
                        daemon=True
                    ).start()
                else:
                    await query.message.reply_text("Trade approved but placement failed.")
            else:
                await query.message.reply_text("Pending trade not found.")
        elif data.startswith('no:'):
            pending_id = data.split(':')[1]
            if pending_id in pending_trades:
                del pending_trades[pending_id]
                await query.message.reply_text("Trade declined.")
        await query.answer()
    except Exception as e:
        logger.error(f"Error in callback: {e}")
        await query.answer("Error processing.")


async def post_init(application):
    global _app
    _app = application
    threading.Thread(target=monitor_markets, daemon=True).start()
    logger.info("Market monitoring thread started.")


if __name__ == '__main__':
    app = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    app.add_handler(CommandHandler('start', cmd_start))
    app.add_handler(CommandHandler('status', cmd_status))
    app.add_handler(CommandHandler('signals', cmd_signals))
    app.add_handler(CommandHandler('toggle_auto', cmd_toggle_auto))
    app.add_handler(CommandHandler('performance', cmd_performance))
    app.add_handler(CommandHandler('edge_report', cmd_edge_report))
    app.add_handler(CallbackQueryHandler(callback_query))

    logger.info("Starting bot...")
    app.run_polling()
