# AI-Powered Prediction Market Trading Tool

An AI agent for monitoring, analyzing, and trading on Kalshi prediction markets using Grok for analysis.

## Features

- **Market Monitoring**: Continuously fetches open markets from Kalshi API
- **AI Analysis**: Uses Grok (xAI) to analyze markets and generate trading signals
- **News Integration**: Fetches relevant news via NewsAPI
- **Signal Generation**: Creates BUY YES/NO signals with confidence scores
- **Auto-Trading**: Optional automatic trade execution
- **Telegram Alerts**: Sends signals and performance via Telegram bot
- **Performance Tracking**: SQLite database tracks P&L, win rate
- **Combo Trade Management**: Limits simultaneous positions to 6 per cycle unless avg confidence >90%, in which case up to 10 are allowed
- **Category Diversification**: Selects markets across all Kalshi categories (top 2 per category by volume), configurable via `.env`
- **Risk Controls**: Edge-based filtering, liquidity/spread checks, per-ticker cooldowns, and daily/cycle trade caps

## Prerequisites

- Python 3.10+
- [Kalshi account](https://kalshi.com) with API access
- [xAI API key](https://console.x.ai) for Grok
- [NewsAPI key](https://newsapi.org) (optional)
- [Telegram Bot Token](https://t.me/BotFather) (optional)

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/armpit-symphony/kalshi-bot.git
cd kalshi-bot
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Create a `.env` file:

```env
# Required
KALSHI_API_KEY_ID=your_kalshi_key_id
KALSHI_PEM_PATH=/path/to/kalshi.pem

# Required for AI analysis
XAI_API_KEY=your_xai_api_key

# Optional
NEWSAPI_KEY=your_newsapi_key
TELEGRAM_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Settings
USE_DEMO=true
AUTO_TRADE=false
CONFIDENCE_THRESHOLD=0.7
EDGE_THRESHOLD=0.05
MIN_VOLUME=100
MAX_SPREAD=15
MAX_TRADES_PER_CYCLE=3
MAX_OPEN_POSITIONS=5
MAX_TRADES_PER_DAY=10
TICKER_COOLDOWN_HOURS=6
ALLOW_MULTIPLE_PER_EVENT=false
MAX_COMBO_POSITIONS=6
HIGH_CONFIDENCE_THRESHOLD=0.9
MAX_TOTAL_POSITIONS=10
DIVERSIFY_SELECTION=true
CATEGORIES_TO_INCLUDE=all
TRADE_SIZE=1
MONITOR_INTERVAL=300
```

### 4. Run the bot

```bash
python main.py
```

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Show welcome message |
| `/status` | Show bot status |
| `/markets` | Show trending markets |
| `/signals` | Show recent signals |
| `/toggle_auto` | Toggle auto-trading |
| `/performance` | Show performance stats |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_DEMO` | `true` | Use demo API |
| `AUTO_TRADE` | `false` | Enable auto-trading |
| `CONFIDENCE_THRESHOLD` | `0.7` | Min confidence to trade |
| `EDGE_THRESHOLD` | `0.05` | Minimum edge vs implied price |
| `MIN_VOLUME` | `100` | Minimum market volume |
| `MAX_SPREAD` | `15` | Max bid/ask spread allowed |
| `MAX_TRADES_PER_CYCLE` | `3` | Cap trades per scan cycle |
| `MAX_OPEN_POSITIONS` | `5` | Cap open positions |
| `MAX_TRADES_PER_DAY` | `10` | Cap trades per day |
| `TICKER_COOLDOWN_HOURS` | `6` | Cooldown before trading same ticker again |
| `ALLOW_MULTIPLE_PER_EVENT` | `false` | Allow multiple trades per event |
| `TRADE_SIZE` | `1` | Contracts per trade |
| `MONITOR_INTERVAL` | `300` | Seconds between scans |
| `MAX_COMBO_POSITIONS` | `6` | Max signals per cycle (normal) |
| `HIGH_CONFIDENCE_THRESHOLD` | `0.9` | Avg confidence to allow larger combo |
| `MAX_TOTAL_POSITIONS` | `10` | Max signals per cycle (high confidence) |
| `DIVERSIFY_SELECTION` | `true` | Diversify by category |
| `CATEGORIES_TO_INCLUDE` | `all` | Filter categories (comma-separated) |

## How It Works

1. **Fetch Markets**: Gets active markets (optionally diversified by category)
2. **Fetch News**: Retrieves relevant news for each market
3. **Analyze**: Uses Grok to predict YES/NO with confidence and market context
4. **Filter**: Applies edge, liquidity, spread, cooldown, and risk caps
5. **Rank**: Prioritizes by edge and volume
6. **Trade**: Optionally executes trade automatically
7. **Alert**: Sends notification via Telegram

## Database Schema

The `trades` table stores:
- `id`: Trade ID
- `ticker`: Market ticker
- `side`: YES or NO
- `count`: Number of contracts
- `price`: Entry price
- `timestamp`: Entry time
- `status`: open/closed
- `settlement_price`: Price at settlement

## Disclaimer

⚠️ This is for educational purposes. Trading involves risk. 
- Always use demo mode first
- Never trade more than you can afford to lose
- Ensure compliance with local regulations

## License

MIT
