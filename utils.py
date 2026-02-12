"""
Utilities — position detection, option chain processing, formatting.
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Any, Dict, List
import pytz
import logging

log = logging.getLogger(__name__)


# ── Safe Type Conversion ─────────────────────────────────────────────────────

def si(v: Any) -> int:
    """Safe int."""
    try:
        return int(float(str(v).strip())) if v else 0
    except (ValueError, TypeError):
        return 0

def sf(v: Any) -> float:
    """Safe float."""
    try:
        return float(str(v).strip()) if v else 0.0
    except (ValueError, TypeError):
        return 0.0


# ── Position Detection ────────────────────────────────────────────────────────

def detect_type(pos: Dict) -> str:
    """
    Determine LONG or SHORT. Breeze gives positive qty for both.
    Checks: action → sell/buy qty → open qty → qty sign.
    """
    a = str(pos.get("action", "")).lower().strip()
    if a == "sell": return "short"
    if a == "buy":  return "long"

    for f in ("position_type", "segment"):
        v = str(pos.get(f, "")).lower()
        if "short" in v or "sell" in v: return "short"
        if "long" in v or "buy" in v:  return "long"

    sq, bq = si(pos.get("sell_quantity")), si(pos.get("buy_quantity"))
    if sq > 0 and bq == 0: return "short"
    if bq > 0 and sq == 0: return "long"
    if sq != bq: return "short" if sq > bq else "long"

    if si(pos.get("open_sell_qty")) > si(pos.get("open_buy_qty")): return "short"
    if si(pos.get("open_buy_qty")) > si(pos.get("open_sell_qty")): return "long"

    if si(pos.get("quantity")) < 0: return "short"
    return "long"


def close_action(pt: str) -> str:
    """BUY to close short, SELL to close long."""
    return "buy" if pt == "short" else "sell"


def calc_pnl(pt: str, avg: float, ltp: float, qty: int) -> float:
    """Long: (LTP−Avg)×Qty, Short: (Avg−LTP)×Qty."""
    q = abs(qty)
    return (avg - ltp) * q if pt == "short" else (ltp - avg) * q


# ── Market ────────────────────────────────────────────────────────────────────

_IST = pytz.timezone("Asia/Kolkata")

def market_status() -> str:
    now = datetime.now(_IST)
    if now.weekday() >= 5: return "🔴 Closed (Weekend)"
    o = now.replace(hour=9, minute=15, second=0, microsecond=0)
    c = now.replace(hour=15, minute=30, second=0, microsecond=0)
    p = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now < p: return "🟡 Pre-Market"
    if now < o: return "🟠 Pre-Open"
    if now <= c: return "🟢 Open"
    return "🔴 Closed"


def fmt_inr(v: float) -> str:
    if abs(v) >= 1e7: return f"₹{v/1e7:.2f}Cr"
    if abs(v) >= 1e5: return f"₹{v/1e5:.2f}L"
    if abs(v) >= 1e3: return f"₹{v/1e3:.1f}K"
    return f"₹{v:.2f}"


def fmt_expiry(d: str) -> str:
    for f in ("%Y-%m-%d", "%d-%b-%Y"):
        try:
            return datetime.strptime(d, f).strftime("%d-%b-%Y (%a)")
        except ValueError:
            continue
    return d


# ── Option Chain Processing ───────────────────────────────────────────────────

def process_oc(data: Dict) -> pd.DataFrame:
    """Raw API data → clean DataFrame with numeric columns."""
    if not data or "Success" not in data:
        return pd.DataFrame()
    rows = data["Success"]
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    # Normalise right field
    if "right" in df.columns:
        df["right"] = df["right"].str.strip().str.capitalize()
    # Convert numerics
    for c in ["strike_price", "ltp", "best_bid_price", "best_offer_price",
              "open_interest", "volume", "ltp_percent_change"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


def oc_pivot(df: pd.DataFrame) -> pd.DataFrame:
    """
    Create traditional option chain view:
    Call OI | Call Vol | Call LTP | Call Bid | Call Ask | STRIKE | Put Bid | Put Ask | Put LTP | Put Vol | Put OI
    """
    if df.empty or "strike_price" not in df.columns or "right" not in df.columns:
        return pd.DataFrame()

    fields = {
        "open_interest": "OI",
        "volume": "Vol",
        "ltp": "LTP",
        "best_bid_price": "Bid",
        "best_offer_price": "Ask",
    }

    calls = df[df["right"] == "Call"].set_index("strike_price")
    puts = df[df["right"] == "Put"].set_index("strike_price")
    strikes = sorted(df["strike_price"].dropna().unique())

    chain = pd.DataFrame({"Strike": strikes})

    for src_col, label in fields.items():
        if src_col in calls.columns:
            chain[f"C {label}"] = chain["Strike"].map(
                calls[src_col].to_dict()).fillna(0)
    
    for src_col, label in fields.items():
        if src_col in puts.columns:
            chain[f"P {label}"] = chain["Strike"].map(
                puts[src_col].to_dict()).fillna(0)

    # Order columns: calls | strike | puts
    call_cols = [c for c in chain.columns if c.startswith("C ")]
    put_cols = [c for c in chain.columns if c.startswith("P ")]
    chain = chain[call_cols + ["Strike"] + put_cols]

    return chain


def oc_pcr(df: pd.DataFrame) -> float:
    if df.empty or "right" not in df.columns:
        return 0.0
    c = df[df["right"] == "Call"]["open_interest"].sum()
    p = df[df["right"] == "Put"]["open_interest"].sum()
    return p / c if c > 0 else 0.0


def oc_max_pain(df: pd.DataFrame) -> int:
    if df.empty or "strike_price" not in df.columns:
        return 0
    strikes = df["strike_price"].unique()
    pain = {}
    for s in strikes:
        cp = ((s - df[(df["right"] == "Call") & (df["strike_price"] < s)]["strike_price"])
              * df[(df["right"] == "Call") & (df["strike_price"] < s)]["open_interest"]).sum()
        pp = ((df[(df["right"] == "Put") & (df["strike_price"] > s)]["strike_price"] - s)
              * df[(df["right"] == "Put") & (df["strike_price"] > s)]["open_interest"]).sum()
        pain[s] = cp + pp
    return int(min(pain, key=pain.get)) if pain else 0


def oc_atm(df: pd.DataFrame) -> float:
    """Estimate ATM strike: where Call LTP ≈ Put LTP, or mid of max OI."""
    if df.empty:
        return 0
    if "right" in df.columns and "ltp" in df.columns:
        calls = df[df["right"] == "Call"][["strike_price", "ltp"]].set_index("strike_price")
        puts = df[df["right"] == "Put"][["strike_price", "ltp"]].set_index("strike_price")
        common = calls.join(puts, lsuffix="_c", rsuffix="_p").dropna()
        if not common.empty:
            common["diff"] = abs(common["ltp_c"] - common["ltp_p"])
            return common["diff"].idxmin()
    # Fallback: middle strike
    strikes = sorted(df["strike_price"].unique())
    return strikes[len(strikes) // 2] if strikes else 0


# ── API Response Helper ───────────────────────────────────────────────────────

class R:
    """Normalise Breeze responses (Success = dict or list)."""
    def __init__(self, raw: Dict):
        self.raw = raw
        self.ok = raw.get("success", False)
        self.msg = raw.get("message", "?")
        d = raw.get("data", {})
        s = d.get("Success") if isinstance(d, dict) else None
        self._s = s
        if isinstance(s, dict):
            self._one = s
        elif isinstance(s, list) and s and isinstance(s[0], dict):
            self._one = s[0]
        else:
            self._one = {}

    @property
    def data(self): return self._one

    @property
    def items(self) -> List[Dict]:
        if isinstance(self._s, list): return self._s
        if isinstance(self._s, dict): return [self._s]
        return []

    def get(self, k, d=None): return self._one.get(k, d)
