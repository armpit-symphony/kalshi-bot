"""Database module for tracking trades and performance."""

import sqlite3
import time
from typing import List, Dict, Any, Optional


def init_db(conn: sqlite3.Connection) -> None:
    """Initialize the database with required tables."""
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            side TEXT NOT NULL,
            count INTEGER NOT NULL,
            price REAL NOT NULL,
            timestamp REAL NOT NULL,
            status TEXT DEFAULT 'open',
            settlement_price REAL
        )
    ''')
    conn.commit()


def add_trade(
    conn: sqlite3.Connection,
    ticker: str,
    side: str,
    count: int,
    price: float,
    timestamp: float
) -> int:
    """Add a new trade to the database. Returns trade ID."""
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (ticker, side, count, price, timestamp, status)
        VALUES (?, ?, ?, ?, ?, 'open')
    ''', (ticker, side, count, price, timestamp))
    conn.commit()
    return cursor.lastrowid


def get_open_trades(conn: sqlite3.Connection, ticker: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get all open trades, optionally filtered by ticker."""
    cursor = conn.cursor()
    if ticker:
        cursor.execute(
            "SELECT * FROM trades WHERE status='open' AND ticker=?",
            (ticker,)
        )
    else:
        cursor.execute("SELECT * FROM trades WHERE status='open'")
    
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def close_trade(conn: sqlite3.Connection, trade_id: int, settlement_price: float) -> None:
    """Close a trade with the settlement price."""
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE trades 
        SET status='closed', settlement_price=? 
        WHERE id=?
    ''', (settlement_price, trade_id))
    conn.commit()


def get_all_trades(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    """Get all trades (open and closed)."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC")
    columns = [desc[0] for desc in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_performance(conn: sqlite3.Connection) -> Dict[str, Any]:
    """Calculate performance metrics (win rate and P&L)."""
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE status='closed'")
    columns = [desc[0] for desc in cursor.description]
    closed = [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    if not closed:
        return {'win_rate': 0, 'pnl': 0, 'total_trades': 0, 'wins': 0, 'losses': 0}
    
    pnl = 0
    wins = 0
    losses = 0
    
    for trade in closed:
        # Calculate P&L per contract
        if trade['side'] == 'yes':
            trade_pnl = trade['count'] * (trade['settlement_price'] - trade['price'])
        else:
            # For NO: profit when settlement_price is 0 (you paid NO price, get $1 if NO wins)
            trade_pnl = trade['count'] * (trade['settlement_price'] - trade['price'])
        
        pnl += trade_pnl
        if trade_pnl > 0:
            wins += 1
        else:
            losses += 1
    
    total = wins + losses
    win_rate = (wins / total * 100) if total > 0 else 0
    
    return {
        'win_rate': round(win_rate, 2),
        'pnl': round(pnl, 2),
        'total_trades': total,
        'wins': wins,
        'losses': losses
    }
