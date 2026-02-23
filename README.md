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
KALSHI_KEY_ID=your_kalshi_key_id
KALSHI_PRIVATE_KEY=-----BEGIN RSA PRIVATE KEY-----
YourPrivateKeyHere
-----END RSA PRIVATE KEY-----

# Required for AI analysis
XAI_API_KEY=your_xai_api_key

# Optional
NEWSAPI_KEY=your_newsapi_key
TELEGRAM_TOKEN=your_telegram_bot_token

# Settings
USE_DEMO=true
AUTO_TRADE=false
CONFIDENCE_THRESHOLD=0.7
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
| `TRADE_SIZE` | `1` | Contracts per trade |
| `MONITOR_INTERVAL` | `300` | Seconds between scans |

## How It Works

1. **Fetch Markets**: Gets top 5 trending markets by volume
2. **Fetch News**: Retrieves relevant news for each market
3. **Analyze**: Uses Grok to predict YES/NO with confidence
4. **Signal**: If confidence > threshold, generates signal
5. **Trade**: Optionally executes trade automatically
6. **Alert**: Sends notification via Telegram

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
