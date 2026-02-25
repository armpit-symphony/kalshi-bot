"""Grok analysis module for generating trading signals."""

import requests
from typing import Tuple


def analyze_with_grok(
    market_title: str,
    market_description: str,
    news: list,
    api_key: str,
    market_meta: dict = None
) -> Tuple[str, float]:
    """
    Analyze a market and generate a trading signal using Grok via REST API.

    Returns:
        Tuple of (signal: 'YES'/'NO'/'HOLD', confidence: 0.0-1.0)
    """
    prompt = f"""You are an expert at analyzing prediction markets.

Market: {market_title}
Description: {market_description}
"""

    if market_meta:
        yes_bid = market_meta.get("yes_bid")
        yes_ask = market_meta.get("yes_ask")
        no_bid = market_meta.get("no_bid")
        no_ask = market_meta.get("no_ask")
        volume = market_meta.get("volume")
        open_interest = market_meta.get("open_interest")
        prompt += "\nMarket Data:\n"
        if yes_bid is not None or yes_ask is not None:
            prompt += f"- YES bid/ask: {yes_bid}/{yes_ask}\n"
        if no_bid is not None or no_ask is not None:
            prompt += f"- NO bid/ask: {no_bid}/{no_ask}\n"
        if volume is not None:
            prompt += f"- Volume: {volume}\n"
        if open_interest is not None:
            prompt += f"- Open interest: {open_interest}\n"

    if news:
        prompt += "\nRecent News:\n"
        for i, article in enumerate(news[:5], 1):
            prompt += f"{i}. {article}\n"

    prompt += """
Based on the above information, predict the outcome of this prediction market.

Respond with ONLY one of these formats:
- "YES with 0.85" (if you think YES is likely, with confidence 0-1)
- "NO with 0.75" (if you think NO is likely, with confidence 0-1)
- "HOLD with 0.0" (if you don't have enough information)

Make your prediction based on the evidence available.
"""

    try:
        response = requests.post(
            'https://api.x.ai/v1/chat/completions',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            json={
                'model': 'grok-3-mini',
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': 0.5,
                'max_tokens': 20
            },
            timeout=30
        )
        response.raise_for_status()
        output = response.json()['choices'][0]['message']['content'].strip()
        return _parse_response(output)

    except Exception as e:
        print(f"Grok analysis error: {e}")
        return ('HOLD', 0.0)


def _parse_response(output: str) -> Tuple[str, float]:
    """Parse Grok's response into signal and confidence."""
    output = output.upper()

    if 'YES' in output and 'WITH' in output:
        try:
            confidence = float(output.split('WITH')[-1].strip().replace('%', ''))
            if confidence > 1:
                confidence = confidence / 100.0
            return ('YES', min(max(confidence, 0.0), 1.0))
        except (ValueError, IndexError):
            return ('YES', 0.5)

    elif 'NO' in output and 'WITH' in output:
        try:
            confidence = float(output.split('WITH')[-1].strip().replace('%', ''))
            if confidence > 1:
                confidence = confidence / 100.0
            return ('NO', min(max(confidence, 0.0), 1.0))
        except (ValueError, IndexError):
            return ('NO', 0.5)

    elif 'HOLD' in output:
        return ('HOLD', 0.0)

    return ('HOLD', 0.0)
