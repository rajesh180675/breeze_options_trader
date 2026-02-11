"""
Utility functions and option chain analysis.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Any, Optional
import pytz

try:
    from scipy.stats import norm as _norm
    from math import log, sqrt, exp
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

IST = pytz.timezone("Asia/Kolkata")


class Utils:

    IST = IST

    @staticmethod
    def is_market_open() -> bool:
        now = datetime.now(IST)
        if now.weekday() >= 5:
            return False
        o = now.replace(hour=9, minute=15, second=0, microsecond=0)
        c = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return o <= now <= c

    @staticmethod
    def get_market_status() -> str:
        now = datetime.now(IST)
        if now.weekday() >= 5:
            return "🔴 Market Closed (Weekend)"
        o = now.replace(hour=9, minute=15, second=0, microsecond=0)
        c = now.replace(hour=15, minute=30, second=0, microsecond=0)
        p = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now < p:
            return "🟡 Pre-Market"
        if now < o:
            return "🟠 Pre-Open Session"
        if now <= c:
            return "🟢 Market Open"
        return "🔴 Market Closed"

    @staticmethod
    def format_currency(value: float) -> str:
        if abs(value) >= 1e7:
            return f"₹{value / 1e7:.2f} Cr"
        if abs(value) >= 1e5:
            return f"₹{value / 1e5:.2f} L"
        if abs(value) >= 1e3:
            return f"₹{value / 1e3:.2f} K"
        return f"₹{value:.2f}"

    @staticmethod
    def format_expiry_date(date_str: str) -> str:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%Y")
        except Exception:
            return date_str

    @staticmethod
    def calculate_option_greeks(
        spot, strike, tte_days, vol, rate, opt_type,
    ) -> Dict[str, float]:
        if not _HAS_SCIPY:
            return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
        try:
            T = max(tte_days / 365, 0.0001)
            d1 = (log(spot / strike) + (rate + vol**2 / 2) * T) / (vol * sqrt(T))
            d2 = d1 - vol * sqrt(T)
            if opt_type.upper() in ("CE", "CALL"):
                delta = _norm.cdf(d1)
                theta = (-spot * _norm.pdf(d1) * vol / (2 * sqrt(T))
                         - rate * strike * exp(-rate * T) * _norm.cdf(d2)) / 365
            else:
                delta = _norm.cdf(d1) - 1
                theta = (-spot * _norm.pdf(d1) * vol / (2 * sqrt(T))
                         + rate * strike * exp(-rate * T) * _norm.cdf(-d2)) / 365
            gamma = _norm.pdf(d1) / (spot * vol * sqrt(T))
            vega = spot * _norm.pdf(d1) * sqrt(T) / 100
            return {
                "delta": round(delta, 4),
                "gamma": round(gamma, 6),
                "theta": round(theta, 4),
                "vega": round(vega, 4),
            }
        except Exception:
            return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}


class OptionChainAnalyzer:

    @staticmethod
    def process_option_chain(data: Dict) -> pd.DataFrame:
        if not data or "Success" not in data:
            return pd.DataFrame()
        records = data["Success"]
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        num_cols = [
            "strike_price", "ltp", "best_bid_price", "best_offer_price",
            "open", "high", "low", "previous_close", "ltp_percent_change",
            "volume", "open_interest", "total_buy_qty", "total_sell_qty",
        ]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    @staticmethod
    def calculate_pcr(df: pd.DataFrame) -> float:
        if df.empty or "right" not in df.columns:
            return 0
        call_oi = df[df["right"] == "Call"]["open_interest"].sum()
        put_oi = df[df["right"] == "Put"]["open_interest"].sum()
        return put_oi / call_oi if call_oi else 0

    @staticmethod
    def get_max_pain(df: pd.DataFrame, strike_gap: int) -> int:
        if df.empty or "strike_price" not in df.columns:
            return 0
        strikes = df["strike_price"].unique()
        pain = {}
        for s in strikes:
            calls = df[(df["right"] == "Call") & (df["strike_price"] < s)]
            cp = ((s - calls["strike_price"]) * calls["open_interest"]).sum()
            puts = df[(df["right"] == "Put") & (df["strike_price"] > s)]
            pp = ((puts["strike_price"] - s) * puts["open_interest"]).sum()
            pain[s] = cp + pp
        return min(pain, key=pain.get) if pain else 0
