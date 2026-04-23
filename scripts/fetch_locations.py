#!/usr/bin/env python3
"""Batch-fetch HQ locations for a list of tickers using yfinance.

Usage:
    python fetch_locations.py AEHR ASML NVDA PLTR
    # Outputs JSON: {"AEHR": {"city": "Fremont", "state": "CA", "country": "United States"}, ...}
"""
import sys
import json
import yfinance as yf


def fetch_locations(tickers: list[str]) -> dict:
    locations = {}
    for ticker in tickers[:30]:  # cap at 30
        try:
            info = yf.Ticker(ticker).info
            city = info.get("city", "")
            state = info.get("state", "")
            country = info.get("country", "")
            if city or state or country:
                locations[ticker] = {
                    "city": city or "",
                    "state": state or "",
                    "country": country or "",
                }
        except Exception:
            pass
    return locations


if __name__ == "__main__":
    tickers = sys.argv[1:]
    if not tickers:
        print("{}")
        sys.exit(0)
    result = fetch_locations(tickers)
    print(json.dumps(result))
