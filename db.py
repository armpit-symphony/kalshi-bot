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
            settlement_price REAL,
            model_prob REAL,
            market_prob REAL,
            edge REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            signal TEXT NOT NULL,
            confidence REAL NOT NULL,
            model_prob REAL NOT NULL,
            market_prob REAL NOT NULL,
            edge REAL NOT NULL,
            best_ask REAL,
            description TEXT,
            timestamp REAL NOT NULL
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

    # Best-effort migrations for older DBs
    for col, col_type in (
        ("model_prob", "REAL"),
        ("market_prob", "REAL"),
        ("edge", "REAL"),
    ):
        try:
            cursor.execute(f"ALTER TABLE trades ADD COLUMN {col} {col_type}")
            conn.commit()
        except sqlite3.OperationalError:
            # Column already exists
            pass

def add_trade(conn, ticker, side, count, price, timestamp, description='', model_prob=None, market_prob=None, edge=None):
    """Add a new trade to the database."""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (
            ticker, side, count, price, description, timestamp, status,
            model_prob, market_prob, edge
        )
        VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
    ''', (ticker, side, count, price, description, timestamp, model_prob, market_prob, edge))
    conn.commit()
    logger.info(f"Added trade for {ticker}")

def add_signal(conn, ticker, side, signal, confidence, model_prob, market_prob, edge, best_ask, timestamp, description=''):
    """Add a new signal to the database."""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO signals (
            ticker, side, signal, confidence, model_prob, market_prob,
            edge, best_ask, description, timestamp
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (ticker, side, signal, confidence, model_prob, market_prob, edge, best_ask, description, timestamp))
    conn.commit()
    logger.info(f"Added signal for {ticker}")

def get_open_trades(conn, ticker=None):
    """Get all open trades."""
    cursor = conn.cursor()
    if ticker:
        cursor.execute("SELECT * FROM trades WHERE status='open' AND ticker=?", (ticker,))
    else:
        cursor.execute("SELECT * FROM trades WHERE status='open'")
    return cursor.fetchall()

def get_open_trades_count(conn):
    """Get count of open trades."""
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM trades WHERE status='open'")
    row = cursor.fetchone()
    return int(row[0]) if row else 0

def has_open_trade(conn, ticker: str) -> bool:
    """Check if there is an open trade for a ticker."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM trades WHERE status='open' AND ticker=? LIMIT 1",
        (ticker,),
    )
    return cursor.fetchone() is not None

def get_last_trade_time(conn, ticker: str):
    """Get the most recent trade timestamp for a ticker."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp FROM trades WHERE ticker=? ORDER BY timestamp DESC LIMIT 1",
        (ticker,),
    )
    row = cursor.fetchone()
    return row[0] if row else None

def count_trades_since(conn, since_ts: float) -> int:
    """Count total trades placed since a timestamp."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*) FROM trades WHERE timestamp >= ?",
        (since_ts,),
    )
    row = cursor.fetchone()
    return int(row[0]) if row else 0

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

def get_edge_report(conn):
    """Bucket win rate and avg P&L by edge."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE status='closed' AND edge IS NOT NULL")
    closed = cursor.fetchall()
    if not closed:
        return []

    buckets = [
        (0.00, 0.02),
        (0.02, 0.05),
        (0.05, 0.10),
        (0.10, 1.00),
    ]
    results = []
    for low, high in buckets:
        bucket_trades = [t for t in closed if t[11] is not None and low <= t[11] < high]
        if not bucket_trades:
            continue
        pnl = 0
        wins = 0
        for trade in bucket_trades:
            if trade[2] == 'yes':
                trade_pnl = trade[3] * (trade[8] - trade[4]) / 100
            else:
                trade_pnl = trade[3] * ((100 - trade[8]) - (100 - trade[4])) / 100
            pnl += trade_pnl
            if trade_pnl > 0:
                wins += 1
        total = len(bucket_trades)
        win_rate = (wins / total * 100) if total > 0 else 0
        results.append({
            "range": f"{low:.2f}-{high:.2f}",
            "trades": total,
            "win_rate": round(win_rate, 2),
            "avg_pnl": round(pnl / total, 4),
        })
    return results

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
