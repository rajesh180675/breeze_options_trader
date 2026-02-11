"""
Utility functions & option chain analyser.
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


class Utils:
    IST = pytz.timezone("Asia/Kolkata")

    @staticmethod
    def is_market_open() -> bool:
        now = datetime.now(Utils.IST)
        if now.weekday() >= 5:
            return False
        o = now.replace(hour=9, minute=15, second=0, microsecond=0)
        c = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return o <= now <= c

    @staticmethod
    def get_market_status() -> str:
        now = datetime.now(Utils.IST)
        if now.weekday() >= 5:
            return "🔴 Market Closed (Weekend)"
        o = now.replace(hour=9, minute=15, second=0, microsecond=0)
        c = now.replace(hour=15, minute=30, second=0, microsecond=0)
        p = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now < p:
            return "🟡 Pre-Market"
        if p <= now < o:
            return "🟠 Pre-Open Session"
        if o <= now <= c:
            return "🟢 Market Open"
        return "🔴 Market Closed"

    @staticmethod
    def format_currency(value: float) -> str:
        if abs(value) >= 1e7:
            return f"₹{value/1e7:.2f} Cr"
        if abs(value) >= 1e5:
            return f"₹{value/1e5:.2f} L"
        if abs(value) >= 1e3:
            return f"₹{value/1e3:.2f} K"
        return f"₹{value:.2f}"

    @staticmethod
    def format_expiry_date(date_str: str) -> str:
        for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%B-%Y"):
            try:
                return datetime.strptime(date_str, fmt).strftime("%d-%b-%Y (%A)")
            except ValueError:
                continue
        return date_str

    @staticmethod
    def calculate_option_greeks(
        spot, strike, tte_days, vol, rate, opt_type,
    ) -> Dict[str, float]:
        if not _HAS_SCIPY:
            return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
        try:
            S, K, r, s = spot, strike, rate, vol
            T = max(tte_days / 365, 0.0001)
            d1 = (log(S/K) + (r + s**2/2)*T) / (s*sqrt(T))
            d2 = d1 - s*sqrt(T)
            if opt_type.upper() in ("CE", "CALL"):
                delta = _norm.cdf(d1)
                theta = (-S*_norm.pdf(d1)*s/(2*sqrt(T))
                         - r*K*exp(-r*T)*_norm.cdf(d2)) / 365
            else:
                delta = _norm.cdf(d1) - 1
                theta = (-S*_norm.pdf(d1)*s/(2*sqrt(T))
                         + r*K*exp(-r*T)*_norm.cdf(-d2)) / 365
            gamma = _norm.pdf(d1) / (S*s*sqrt(T))
            vega = S * _norm.pdf(d1) * sqrt(T) / 100
            return {
                "delta": round(delta, 4), "gamma": round(gamma, 6),
                "theta": round(theta, 4), "vega": round(vega, 4),
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
        nums = [
            "strike_price", "ltp", "best_bid_price", "best_offer_price",
            "open", "high", "low", "previous_close", "ltp_percent_change",
            "volume", "open_interest", "total_buy_qty", "total_sell_qty",
        ]
        for c in nums:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    @staticmethod
    def calculate_pcr(df: pd.DataFrame) -> float:
        if df.empty or "right" not in df.columns:
            return 0.0
        call_oi = df[df["right"] == "Call"]["open_interest"].sum()
        put_oi = df[df["right"] == "Put"]["open_interest"].sum()
        return put_oi / call_oi if call_oi else 0.0

    @staticmethod
    def get_max_pain(df: pd.DataFrame, strike_gap: int) -> int:
        if df.empty or "strike_price" not in df.columns:
            return 0
        strikes = df["strike_price"].unique()
        pain = {}
        for s in strikes:
            cp = ((s - df[(df["right"]=="Call") & (df["strike_price"]<s)]["strike_price"])
                  * df[(df["right"]=="Call") & (df["strike_price"]<s)]["open_interest"]).sum()
            pp = ((df[(df["right"]=="Put") & (df["strike_price"]>s)]["strike_price"] - s)
                  * df[(df["right"]=="Put") & (df["strike_price"]>s)]["open_interest"]).sum()
            pain[s] = cp + pp
        return int(min(pain, key=pain.get)) if pain else 0
