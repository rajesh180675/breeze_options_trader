"""
Utilities, option chain analyser, and position detection.
"""

import pandas as pd
from datetime import datetime
from typing import Any, Dict, List
import pytz
import logging

logger = logging.getLogger(__name__)

try:
    from scipy.stats import norm as _norm
    from math import log, sqrt, exp
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


def _safe_int(v):
    try: return int(float(str(v).strip())) if v else 0
    except: return 0


class PositionUtils:
    """Position type detection, P&L, and close action logic."""

    @staticmethod
    def detect_type(pos: Dict[str, Any]) -> str:
        """
        Determine LONG or SHORT from Breeze position data.
        Breeze returns positive qty for BOTH — must check action field.
        """
        a = str(pos.get("action", "")).lower().strip()
        if a == "sell": return "short"
        if a == "buy": return "long"

        for fld in ("position_type", "segment"):
            v = str(pos.get(fld, "")).lower()
            if "short" in v or "sell" in v: return "short"
            if "long" in v or "buy" in v: return "long"

        sq = _safe_int(pos.get("sell_quantity", 0))
        bq = _safe_int(pos.get("buy_quantity", 0))
        if sq > 0 and bq == 0: return "short"
        if bq > 0 and sq == 0: return "long"
        if sq > bq: return "short"
        if bq > sq: return "long"

        osq = _safe_int(pos.get("open_sell_qty", 0))
        obq = _safe_int(pos.get("open_buy_qty", 0))
        if osq > obq: return "short"
        if obq > osq: return "long"

        if _safe_int(pos.get("quantity", 0)) < 0: return "short"

        logger.warning(f"Position type unknown: {pos}")
        return "long"

    @staticmethod
    def close_action(pos_type: str) -> str:
        """BUY to close short, SELL to close long."""
        return "buy" if pos_type == "short" else "sell"

    @staticmethod
    def calc_pnl(pos_type: str, avg: float, ltp: float, qty: int) -> float:
        """
        Long  = (LTP − Avg) × Qty
        Short = (Avg − LTP) × Qty
        """
        q = abs(qty)
        return (avg - ltp) * q if pos_type == "short" else (ltp - avg) * q


class Utils:
    IST = pytz.timezone("Asia/Kolkata")

    @staticmethod
    def is_market_open() -> bool:
        now = datetime.now(Utils.IST)
        if now.weekday() >= 5: return False
        o = now.replace(hour=9, minute=15, second=0, microsecond=0)
        c = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return o <= now <= c

    @staticmethod
    def get_market_status() -> str:
        now = datetime.now(Utils.IST)
        if now.weekday() >= 5: return "🔴 Closed (Weekend)"
        o = now.replace(hour=9, minute=15, second=0, microsecond=0)
        c = now.replace(hour=15, minute=30, second=0, microsecond=0)
        p = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now < p: return "🟡 Pre-Market"
        if p <= now < o: return "🟠 Pre-Open"
        if o <= now <= c: return "🟢 Market Open"
        return "🔴 Closed"

    @staticmethod
    def format_currency(value: float) -> str:
        if abs(value) >= 1e7: return f"₹{value/1e7:.2f} Cr"
        if abs(value) >= 1e5: return f"₹{value/1e5:.2f} L"
        if abs(value) >= 1e3: return f"₹{value/1e3:.2f} K"
        return f"₹{value:.2f}"

    @staticmethod
    def format_expiry_date(d: str) -> str:
        for fmt in ("%Y-%m-%d", "%d-%b-%Y"):
            try: return datetime.strptime(d, fmt).strftime("%d-%b-%Y (%A)")
            except: continue
        return d


class OptionChainAnalyzer:
    @staticmethod
    def process_option_chain(data: Dict) -> pd.DataFrame:
        if not data or "Success" not in data: return pd.DataFrame()
        records = data["Success"]
        if not records: return pd.DataFrame()
        df = pd.DataFrame(records)
        for c in ["strike_price","ltp","best_bid_price","best_offer_price",
                   "open","high","low","volume","open_interest",
                   "ltp_percent_change"]:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    @staticmethod
    def calculate_pcr(df: pd.DataFrame) -> float:
        if df.empty or "right" not in df.columns: return 0.0
        c_oi = df[df["right"]=="Call"]["open_interest"].sum()
        p_oi = df[df["right"]=="Put"]["open_interest"].sum()
        return p_oi / c_oi if c_oi else 0.0

    @staticmethod
    def get_max_pain(df: pd.DataFrame, gap: int) -> int:
        if df.empty or "strike_price" not in df.columns: return 0
        strikes = df["strike_price"].unique()
        pain = {}
        for s in strikes:
            cp = ((s - df[(df["right"]=="Call")&(df["strike_price"]<s)]["strike_price"])
                  * df[(df["right"]=="Call")&(df["strike_price"]<s)]["open_interest"]).sum()
            pp = ((df[(df["right"]=="Put")&(df["strike_price"]>s)]["strike_price"] - s)
                  * df[(df["right"]=="Put")&(df["strike_price"]>s)]["open_interest"]).sum()
            pain[s] = cp + pp
        return int(min(pain, key=pain.get)) if pain else 0
