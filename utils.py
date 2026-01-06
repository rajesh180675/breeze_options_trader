"""
Utility functions for Breeze Options Trader
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import pytz


class Utils:
    """Utility functions"""
    
    IST = pytz.timezone('Asia/Kolkata')
    
    @staticmethod
    def is_market_open() -> bool:
        """Check if market is currently open"""
        now = datetime.now(Utils.IST)
        market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        # Check if weekday
        if now.weekday() >= 5:  # Saturday or Sunday
            return False
        
        return market_open <= now <= market_close
    
    @staticmethod
    def get_market_status() -> str:
        """Get current market status"""
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
        """Format value as Indian currency"""
        if value >= 10000000:
            return f"₹{value/10000000:.2f} Cr"
        elif value >= 100000:
            return f"₹{value/100000:.2f} L"
        elif value >= 1000:
            return f"₹{value/1000:.2f} K"
        else:
            return f"₹{value:.2f}"
    
    @staticmethod
    def calculate_pnl(
        entry_price: float,
        current_price: float,
        quantity: int,
        position_type: str
    ) -> Dict[str, float]:
        """
        Calculate P&L for a position
        
        Args:
            entry_price: Entry price
            current_price: Current price
            quantity: Position quantity
            position_type: long or short
            
        Returns:
            P&L details
        """
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
        spot_price: float,
        strike_gap: int,
        num_strikes: int = 20
    ) -> List[int]:
        """
        Generate strike prices around spot price
        
        Args:
            spot_price: Current spot price
            strike_gap: Gap between strikes
            num_strikes: Number of strikes on each side
            
        Returns:
            List of strike prices
        """
        atm_strike = round(spot_price / strike_gap) * strike_gap
        strikes = []
        
        for i in range(-num_strikes, num_strikes + 1):
            strikes.append(atm_strike + (i * strike_gap))
        
        return strikes
    
    @staticmethod
    def format_expiry_date(date_str: str, input_format: str = "%Y-%m-%d") -> str:
        """Format expiry date for display"""
        try:
            dt = datetime.strptime(date_str, input_format)
            return dt.strftime("%d-%b-%Y")
        except:
            return date_str
    
    @staticmethod
    def parse_breeze_datetime(date_str: str) -> Optional[datetime]:
        """Parse datetime from Breeze API response"""
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%d-%b-%Y %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%d-%b-%Y"
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except:
                continue
        
        return None
    
    @staticmethod
    def calculate_option_greeks(
        spot_price: float,
        strike_price: float,
        time_to_expiry: float,
        volatility: float,
        interest_rate: float,
        option_type: str
    ) -> Dict[str, float]:
        """
        Calculate option Greeks (simplified Black-Scholes approximation)
        
        Note: For production, use a proper options pricing library
        """
        from math import log, sqrt, exp
        from scipy.stats import norm
        
        try:
            S = spot_price
            K = strike_price
            T = time_to_expiry / 365  # Convert to years
            r = interest_rate
            sigma = volatility
            
            if T <= 0:
                T = 0.0001
            
            d1 = (log(S/K) + (r + sigma**2/2)*T) / (sigma*sqrt(T))
            d2 = d1 - sigma*sqrt(T)
            
            if option_type.upper() in ["CE", "CALL"]:
                delta = norm.cdf(d1)
                theta = (-S*norm.pdf(d1)*sigma/(2*sqrt(T)) - 
                        r*K*exp(-r*T)*norm.cdf(d2)) / 365
            else:
                delta = norm.cdf(d1) - 1
                theta = (-S*norm.pdf(d1)*sigma/(2*sqrt(T)) + 
                        r*K*exp(-r*T)*norm.cdf(-d2)) / 365
            
            gamma = norm.pdf(d1) / (S * sigma * sqrt(T))
            vega = S * norm.pdf(d1) * sqrt(T) / 100
            
            return {
                "delta": round(delta, 4),
                "gamma": round(gamma, 6),
                "theta": round(theta, 4),
                "vega": round(vega, 4)
            }
        except Exception as e:
            return {"delta": 0, "gamma": 0, "theta": 0, "vega": 0}
    
    @staticmethod
    def positions_to_dataframe(positions: List[Dict]) -> pd.DataFrame:
        """Convert positions list to DataFrame"""
        if not positions:
            return pd.DataFrame()
        
        df = pd.DataFrame(positions)
        
        # Rename columns for better display
        column_mapping = {
            "stock_code": "Instrument",
            "exchange_code": "Exchange",
            "expiry_date": "Expiry",
            "strike_price": "Strike",
            "right": "Type",
            "quantity": "Qty",
            "average_price": "Avg Price",
            "ltp": "LTP",
            "pnl": "P&L"
        }
        
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
        
        return df
    
    @staticmethod
    def orders_to_dataframe(orders: List[Dict]) -> pd.DataFrame:
        """Convert orders list to DataFrame"""
        if not orders:
            return pd.DataFrame()
        
        df = pd.DataFrame(orders)
        
        column_mapping = {
            "order_id": "Order ID",
            "stock_code": "Instrument",
            "action": "Action",
            "quantity": "Qty",
            "price": "Price",
            "order_type": "Type",
            "order_status": "Status",
            "order_datetime": "Time"
        }
        
        df = df.rename(columns={k: v for k, v in column_mapping.items() if k in df.columns})
        
        return df


class OptionChainAnalyzer:
    """Analyze option chain data"""
    
    @staticmethod
    def process_option_chain(data: Dict) -> pd.DataFrame:
        """Process raw option chain data into DataFrame"""
        if not data or "Success" not in data:
            return pd.DataFrame()
        
        records = data["Success"]
        if not records:
            return pd.DataFrame()
        
        df = pd.DataFrame(records)
        
        # Convert numeric columns
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
        """Get ATM strike price"""
        return round(spot_price / strike_gap) * strike_gap
    
    @staticmethod
    def calculate_pcr(df: pd.DataFrame) -> float:
        """Calculate Put-Call Ratio"""
        if df.empty:
            return 0
        
        calls = df[df['right'] == 'Call']
        puts = df[df['right'] == 'Put']
        
        call_oi = calls['open_interest'].sum()
        put_oi = puts['open_interest'].sum()
        
        if call_oi == 0:
            return 0
        
        return put_oi / call_oi
    
    @staticmethod
    def get_max_pain(df: pd.DataFrame, strike_gap: int) -> int:
        """Calculate Max Pain strike"""
        if df.empty:
            return 0
        
        strikes = df['strike_price'].unique()
        pain = {}
        
        for strike in strikes:
            call_pain = 0
            put_pain = 0
            
            # For calls: sum of (strike - current_strike) * OI where strike > current
            calls = df[(df['right'] == 'Call') & (df['strike_price'] < strike)]
            call_pain = ((strike - calls['strike_price']) * calls['open_interest']).sum()
            
            # For puts: sum of (current_strike - strike) * OI where strike < current
            puts = df[(df['right'] == 'Put') & (df['strike_price'] > strike)]
            put_pain = ((puts['strike_price'] - strike) * puts['open_interest']).sum()
            
            pain[strike] = call_pain + put_pain
        
        return min(pain, key=pain.get) if pain else 0
