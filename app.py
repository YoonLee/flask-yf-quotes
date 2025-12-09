"""
Simple Flask service that proxies live quote data from Yahoo Finance via yfinance.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Tuple

from flask import Flask, jsonify
import requests
import yfinance as yf

app = Flask(__name__)
_YF_SESSION = requests.Session()
_YF_SESSION.headers.update(
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
    }
)


def _fetch_quote(symbol: str) -> Tuple[float, float, datetime, float]:
    """
    Fetch the most recent close plus previous close so we can calculate pct change.
    """
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period='2d')

    if hist.empty:
        raise ValueError(f"No price data available for symbol '{symbol}'.")

    last_close = float(hist["Close"].iloc[-1])
    prev_close = float(hist["Close"].iloc[-2]) if len(hist["Close"]) > 1 else last_close
    timestamp = hist.index[-1].to_pydatetime()
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    volume = float(hist["Volume"].iloc[-1])

    if prev_close == 0.0:
        raise ValueError(f"Previous close is zero for symbol '{symbol}'.")

    return last_close, prev_close, timestamp, volume


def _format_volume(volume: float) -> str:
    """Return a human-readable volume string using K/M/B suffixes."""
    abs_volume = abs(volume)
    if abs_volume >= 1_000_000_000:
        return f"{volume / 1_000_000_000:.2f}B"
    if abs_volume >= 1_000_000:
        return f"{volume / 1_000_000:.2f}M"
    if abs_volume >= 1_000:
        return f"{volume / 1_000:.2f}K"
    return f"{int(volume)}"


def _build_response(symbol: str) -> Dict[str, object]:
    symbol = symbol.upper()
    last_price, prev_close, timestamp, volume = _fetch_quote(symbol)
    change_percent = ((last_price - prev_close) / prev_close) * 100
    server_time_utc = datetime.now(timezone.utc).isoformat()

    app.logger.info(
        "Quote fetched | symbol=%s last_price=%.4f prev_close=%.4f volume=%.0f timestamp=%s server_time_utc=%s",
        symbol,
        last_price,
        prev_close,
        volume,
        timestamp.isoformat(),
        server_time_utc,
    )

    return {
        "symbol": symbol,
        "last_price": round(last_price, 4),
        "previous_close": round(prev_close, 4),
        "change_percent": round(change_percent, 4),
        "volume": int(volume),
        "volume_formatted": _format_volume(volume),
        "timestamp": timestamp.isoformat(),
        "last_updated_utc": server_time_utc,
    }


@app.get("/api/quote/<symbol>")
def get_quote(symbol: str):
    """
    Return the latest price plus daily change percentage for the supplied symbol.
    """
    try:
        data = _build_response(symbol)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 404
    except Exception as exc:  # pragma: no cover - defensive catch for external API issues
        return jsonify({"error": "Failed to reach Yahoo Finance", "details": str(exc)}), 502

    return jsonify(data)


@app.get("/")
def root():
    """
    Provide a tiny landing page that documents the available endpoint.
    """
    return jsonify(
        {
            "message": "Use /api/quote/<symbol> to fetch the latest price and change percent.",
            "example": "/api/quote/AAPL",
        }
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
