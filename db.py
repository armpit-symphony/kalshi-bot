import sqlite3
import time
import logging

logger = logging.getLogger(__name__)

def init_db(conn):
    """Initialize the database with required tables."""
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            count INTEGER NOT NULL,
            price REAL NOT NULL,
            description TEXT,
            timestamp REAL NOT NULL,
            status TEXT DEFAULT 'open',
            settlement_price REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS lessons (
            id INTEGER PRIMARY KEY,
            ticker TEXT,
            description TEXT,
            predicted_side TEXT,
            actual_outcome TEXT,
            lesson TEXT,
            timestamp REAL
        )
    ''')
    conn.commit()
    logger.info("Database initialized.")

def add_trade(conn, ticker, side, count, price, timestamp, description=''):
    """Add a new trade to the database."""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (ticker, side, count, price, description, timestamp, status)
        VALUES (?, ?, ?, ?, ?, ?, 'open')
    ''', (ticker, side, count, price, description, timestamp))
    conn.commit()
    logger.info(f"Added trade for {ticker}")

def get_open_trades(conn, ticker=None):
    """Get all open trades."""
    cursor = conn.cursor()
    if ticker:
        cursor.execute("SELECT * FROM trades WHERE status='open' AND ticker=?", (ticker,))
    else:
        cursor.execute("SELECT * FROM trades WHERE status='open'")
    return cursor.fetchall()

def close_trade(conn, trade_id, settlement_price):
    """Close a trade with settlement price."""
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE trades SET status='closed', settlement_price=? WHERE id=?
    ''', (settlement_price, trade_id))
    conn.commit()
    logger.info(f"Closed trade {trade_id}")

def get_performance(conn):
    """Calculate performance metrics (win rate and P&L)."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE status='closed'")
    closed = cursor.fetchall()
    
    if not closed:
        return {'win_rate': 0, 'pnl': 0, 'total_trades': 0}
    
    pnl = 0
    wins = 0
    
    for trade in closed:
        # trade: id, ticker, side, count, price, description, timestamp, status, settlement_price
        if trade[2] == 'yes':
            trade_pnl = trade[3] * (trade[8] - trade[4]) / 100
        else:
            trade_pnl = trade[3] * ((100 - trade[8]) - (100 - trade[4])) / 100
        pnl += trade_pnl
        if trade_pnl > 0:
            wins += 1
    
    total = len(closed)
    win_rate = (wins / total * 100) if total > 0 else 0
    
    return {'win_rate': round(win_rate, 2), 'pnl': round(pnl, 2), 'total_trades': total}

def add_lesson(conn, ticker, description, predicted_side, actual_outcome, lesson):
    """Add a lesson from a wrong prediction."""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO lessons (ticker, description, predicted_side, actual_outcome, lesson, timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (ticker, description, predicted_side, actual_outcome, lesson, time.time()))
    conn.commit()
    logger.info(f"Added lesson for {ticker}")

def get_lessons(conn):
    """Get recent lessons."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM lessons ORDER BY timestamp DESC LIMIT 5")
    return cursor.fetchall()
