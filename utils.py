"""
Utility functions for Breeze Options Trader
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pytz

# Optional scipy import for Greeks calculation
try:
    from scipy.stats import norm as _norm
    from math import log, sqrt, exp
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False


class Utils:
    """Utility functions"""
    
    IST = pytz.timezone('Asia/Kolkata')
    
    @staticmethod
    def is_market_open() -> bool:
        now = datetime.now(Utils.IST)
        if now.weekday() >= 5:
            return False
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        return market_open <= now <= market_close
    
    @staticmethod
    def get_market_status() -> str:
        now = datetime.now(Utils.IST)
        if now.weekday() >= 5:
            return "🔴 Market Closed (Weekend)"
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        pre_market = now.replace(hour=9, minute=0, second=0, microsecond=0)
        if now < pre_market:
            return "🟡 Pre-Market"
        elif pre_market <= now < market_open:
            return "🟠 Pre-Open Session"
        elif market_open <= now <= market_close:
            return "🟢 Market Open"
        else:
            return "🔴 Market Closed"
    
    @staticmethod
    def format_currency(value: float) -> str:
        if value >= 10_000_000:
            return f"₹{value / 10_000_000:.2f} Cr"
        elif value >= 100_000:
            return f"₹{value / 100_000:.2f} L"
        elif value >= 1_000:
            return f"₹{value / 1_000:.2f} K"
        else:
            return f"₹{value:.2f}"
    
    @staticmethod
    def calculate_pnl(
        entry_price: float, current_price: float,
        quantity: int, position_type: str
    ) -> Dict[str, float]:
        if position_type.lower() == "long":
            pnl = (current_price - entry_price) * quantity
        else:
            pnl = (entry_price - current_price) * quantity
        
        pnl_percent = ((current_price - entry_price) / entry_price) * 100
        if position_type.lower() == "short":
            pnl_percent = -pnl_percent
        
        return {
            "pnl": pnl,
            "pnl_percent": pnl_percent,
            "entry_value": entry_price * quantity,
            "current_value": current_price * quantity
        }
    
    @staticmethod
    def get_strike_prices(
        spot_price: float, strike_gap: int, num_strikes: int = 20
    ) -> List[int]:
        atm_strike = round(spot_price / strike_gap) * strike_gap
        return [atm_strike + (i * strike_gap)
                for i in range(-num_strikes, num_strikes + 1)]
    
    @staticmethod
    def format_expiry_date(date_str: str, input_format: str = "%Y-%m-%d") -> str:
        try:
            return datetime.strptime(date_str, input_format).strftime("%d-%b-%Y")
        except Exception:
            return date_str
    
    @staticmethod
    def parse_breeze_datetime(date_str: str) -> Optional[datetime]:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M:%S",
                    "%Y-%m-%dT%H:%M:%S", "%d-%b-%Y"):
            try:
                return datetime.strptime(date_str, fmt)
            except Exception:
                continue
        return None
    
    @staticmethod
    def calculate_option_greeks(
        spot_price: float, strike_price: float,
        time_to_expiry: float, volatility: float,
        interest_rate: float, option_type: str
    ) -> Dict[str, float]:
        """Simplified Black-Scholes Greeks (requires scipy)."""
        if not _HAS_SCIPY:
            return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
        
        try:
            S, K, r, sigma = spot_price, strike_price, interest_rate, volatility
            T = max(time_to_expiry / 365, 0.0001)
            
            d1 = (log(S / K) + (r + sigma ** 2 / 2) * T) / (sigma * sqrt(T))
            d2 = d1 - sigma * sqrt(T)
            
            if option_type.upper() in ("CE", "CALL"):
                delta = _norm.cdf(d1)
                theta = (-S * _norm.pdf(d1) * sigma / (2 * sqrt(T))
                         - r * K * exp(-r * T) * _norm.cdf(d2)) / 365
            else:
                delta = _norm.cdf(d1) - 1
                theta = (-S * _norm.pdf(d1) * sigma / (2 * sqrt(T))
                         + r * K * exp(-r * T) * _norm.cdf(-d2)) / 365
            
            gamma = _norm.pdf(d1) / (S * sigma * sqrt(T))
            vega = S * _norm.pdf(d1) * sqrt(T) / 100
            
            return {
                "delta": round(delta, 4),
                "gamma": round(gamma, 6),
                "theta": round(theta, 4),
                "vega": round(vega, 4),
            }
        except Exception:
            return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
    
    @staticmethod
    def positions_to_dataframe(positions: List[Dict]) -> pd.DataFrame:
        if not positions:
            return pd.DataFrame()
        df = pd.DataFrame(positions)
        mapping = {
            "stock_code": "Instrument", "exchange_code": "Exchange",
            "expiry_date": "Expiry", "strike_price": "Strike",
            "right": "Type", "quantity": "Qty",
            "average_price": "Avg Price", "ltp": "LTP", "pnl": "P&L"
        }
        return df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})
    
    @staticmethod
    def orders_to_dataframe(orders: List[Dict]) -> pd.DataFrame:
        if not orders:
            return pd.DataFrame()
        df = pd.DataFrame(orders)
        mapping = {
            "order_id": "Order ID", "stock_code": "Instrument",
            "action": "Action", "quantity": "Qty", "price": "Price",
            "order_type": "Type", "order_status": "Status",
            "order_datetime": "Time"
        }
        return df.rename(columns={k: v for k, v in mapping.items() if k in df.columns})


class OptionChainAnalyzer:
    """Analyze option chain data"""
    
    @staticmethod
    def process_option_chain(data: Dict) -> pd.DataFrame:
        if not data or "Success" not in data:
            return pd.DataFrame()
        records = data["Success"]
        if not records:
            return pd.DataFrame()
        
        df = pd.DataFrame(records)
        numeric_cols = [
            'strike_price', 'ltp', 'best_bid_price', 'best_offer_price',
            'open', 'high', 'low', 'previous_close', 'ltp_percent_change',
            'volume', 'open_interest', 'total_buy_qty', 'total_sell_qty'
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df
    
    @staticmethod
    def get_atm_strike(df: pd.DataFrame, spot_price: float, strike_gap: int) -> int:
        return round(spot_price / strike_gap) * strike_gap
    
    @staticmethod
    def calculate_pcr(df: pd.DataFrame) -> float:
        if df.empty:
            return 0
        call_oi = df[df['right'] == 'Call']['open_interest'].sum()
        put_oi = df[df['right'] == 'Put']['open_interest'].sum()
        return put_oi / call_oi if call_oi else 0
    
    @staticmethod
    def get_max_pain(df: pd.DataFrame, strike_gap: int) -> int:
        if df.empty:
            return 0
        strikes = df['strike_price'].unique()
        pain = {}
        for strike in strikes:
            calls = df[(df['right'] == 'Call') & (df['strike_price'] < strike)]
            call_pain = ((strike - calls['strike_price']) * calls['open_interest']).sum()
            puts = df[(df['right'] == 'Put') & (df['strike_price'] > strike)]
            put_pain = ((puts['strike_price'] - strike) * puts['open_interest']).sum()
            pain[strike] = call_pain + put_pain
        return min(pain, key=pain.get) if pain else 0
