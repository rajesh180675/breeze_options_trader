"""
Breeze API Client Wrapper.
──────────────────────────
• Smart date parsing (handles DD-Mon-YYYY, YYYY-MM-DD, ISO, etc.)
• All API calls return  {"success": bool, "message": str, "data": ...}
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import pytz
from breeze_connect import BreezeConnect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATE PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def parse_date(date_str: str) -> str:
    """
    Accept any common date format, return DD-Mon-YYYY for Breeze API.

    Handles:
      12-Feb-2026   →  12-Feb-2026   (already correct)
      2026-02-12    →  12-Feb-2026
      12-FEB-2026   →  12-Feb-2026
      2026-02-12T…  →  12-Feb-2026
      12/02/2026    →  12-Feb-2026
    """
    if not date_str or not date_str.strip():
        return ""

    s = date_str.strip()

    formats = [
        ("%d-%b-%Y", False),
        ("%d-%B-%Y", True),
        ("%Y-%m-%d", True),
        ("%Y-%m-%dT%H:%M:%S", True),
        ("%Y-%m-%dT%H:%M:%S.%f", True),
        ("%d/%m/%Y", True),
        ("%d-%m-%Y", True),
    ]

    for fmt, needs_convert in formats:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%d-%b-%Y") if needs_convert else s
        except ValueError:
            continue

    logger.warning(f"Could not parse date '{s}', returning as-is")
    return s


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════

class BreezeClientWrapper:
    """Thin wrapper around BreezeConnect with error handling."""

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.breeze: Optional[BreezeConnect] = None
        self.is_connected = False
        self.ist = pytz.timezone("Asia/Kolkata")

    # ── helpers ────────────────────────────────────────────────────────────

    def _ok(self, data: Any) -> Dict[str, Any]:
        return {"success": True, "data": data, "message": ""}

    def _fail(self, msg: str) -> Dict[str, Any]:
        return {"success": False, "data": {}, "message": msg}

    def _guard(self) -> Optional[Dict]:
        if not self.is_connected:
            return self._fail("Not connected to Breeze API")
        return None

    # ── connection ─────────────────────────────────────────────────────────

    def connect(self, session_token: str) -> Dict[str, Any]:
        try:
            self.breeze = BreezeConnect(api_key=self.api_key)
            self.breeze.generate_session(
                api_secret=self.api_secret,
                session_token=session_token,
            )
            self.is_connected = True
            logger.info("Connected to Breeze API")
            return self._ok({"message": "Connected"})
        except Exception as e:
            logger.error(f"Connect failed: {e}")
            self.is_connected = False
            return self._fail(str(e))

    # ── account ────────────────────────────────────────────────────────────

    def get_customer_details(self) -> Dict[str, Any]:
        err = self._guard()
        if err:
            return err
        try:
            return self._ok(self.breeze.get_customer_details())
        except Exception as e:
            return self._fail(str(e))

    def get_funds(self) -> Dict[str, Any]:
        err = self._guard()
        if err:
            return err
        try:
            return self._ok(self.breeze.get_funds())
        except Exception as e:
            return self._fail(str(e))

    # ── market data ────────────────────────────────────────────────────────

    def get_option_chain(
        self, stock_code: str, exchange: str, expiry_date: str,
        product_type: str = "options", strike_price: str = "",
        option_type: str = "",
    ) -> Dict[str, Any]:
        err = self._guard()
        if err:
            return err
        try:
            exp = parse_date(expiry_date)
            data = self.breeze.get_option_chain_quotes(
                stock_code=stock_code,
                exchange_code=exchange,
                product_type=product_type,
                expiry_date=exp,
                right=option_type or "",
                strike_price=str(strike_price) if strike_price else "",
            )
            return self._ok(data)
        except Exception as e:
            logger.error(f"Option chain: {e}")
            return self._fail(str(e))

    def get_quotes(
        self, stock_code: str, exchange: str, expiry_date: str,
        strike_price: int, option_type: str,
        product_type: str = "options",
    ) -> Dict[str, Any]:
        err = self._guard()
        if err:
            return err
        try:
            exp = parse_date(expiry_date)
            right = "call" if option_type.upper() == "CE" else "put"
            data = self.breeze.get_quotes(
                stock_code=stock_code,
                exchange_code=exchange,
                expiry_date=exp,
                product_type=product_type,
                right=right,
                strike_price=str(strike_price),
            )
            return self._ok(data)
        except Exception as e:
            return self._fail(str(e))

    # ── orders ─────────────────────────────────────────────────────────────

    def place_order(
        self, stock_code: str, exchange: str, expiry_date: str,
        strike_price: int, option_type: str, action: str,
        quantity: int, order_type: str = "market", price: float = 0,
        stoploss: float = 0, validity: str = "day",
    ) -> Dict[str, Any]:
        err = self._guard()
        if err:
            return err
        try:
            exp = parse_date(expiry_date)
            right = "call" if option_type.upper() == "CE" else "put"

            resp = self.breeze.place_order(
                stock_code=stock_code,
                exchange_code=exchange,
                product="options",
                action=action.lower(),
                order_type=order_type.lower(),
                stoploss=str(stoploss) if stoploss > 0 else "",
                quantity=str(quantity),
                price=str(price) if order_type.lower() == "limit" else "",
                validity=validity,
                validity_date="",
                disclosed_quantity="",
                expiry_date=exp,
                right=right,
                strike_price=str(strike_price),
            )
            logger.info(f"Order: {action} {stock_code} {strike_price}{right} x{quantity} → {resp}")
            return self._ok(resp)
        except Exception as e:
            logger.error(f"Place order: {e}")
            return self._fail(str(e))

    def sell_call(self, stock_code, exchange, expiry_date, strike_price,
                  quantity, order_type="market", price=0):
        return self.place_order(stock_code, exchange, expiry_date,
                                strike_price, "CE", "sell", quantity,
                                order_type, price)

    def sell_put(self, stock_code, exchange, expiry_date, strike_price,
                 quantity, order_type="market", price=0):
        return self.place_order(stock_code, exchange, expiry_date,
                                strike_price, "PE", "sell", quantity,
                                order_type, price)

    def square_off_position(
        self, stock_code, exchange, expiry_date, strike_price,
        option_type, quantity, current_position,
        order_type="market", price=0,
    ):
        action = "buy" if current_position.lower() == "short" else "sell"
        logger.info(f"Square off: {action} {stock_code} {strike_price} "
                     f"{option_type} x{quantity} (was {current_position})")
        return self.place_order(stock_code, exchange, expiry_date,
                                strike_price, option_type, action,
                                quantity, order_type, price)

    # ── portfolio ──────────────────────────────────────────────────────────

    def get_portfolio_positions(self) -> Dict[str, Any]:
        err = self._guard()
        if err:
            return err
        try:
            return self._ok(self.breeze.get_portfolio_positions())
        except Exception as e:
            return self._fail(str(e))

    def get_order_list(self, exchange="", from_date="", to_date=""):
        err = self._guard()
        if err:
            return err
        try:
            fd = parse_date(from_date) if from_date else ""
            td = parse_date(to_date) if to_date else ""
            data = self.breeze.get_order_list(
                exchange_code=exchange, from_date=fd, to_date=td,
            )
            return self._ok(data)
        except Exception as e:
            logger.error(f"Order list: {e}")
            return self._fail(str(e))

    def get_trade_list(self, exchange="", from_date="", to_date=""):
        err = self._guard()
        if err:
            return err
        try:
            fd = parse_date(from_date) if from_date else ""
            td = parse_date(to_date) if to_date else ""
            data = self.breeze.get_trade_list(
                exchange_code=exchange, from_date=fd, to_date=td,
            )
            return self._ok(data)
        except Exception as e:
            logger.error(f"Trade list: {e}")
            return self._fail(str(e))

    def cancel_order(self, order_id, exchange):
        err = self._guard()
        if err:
            return err
        try:
            resp = self.breeze.cancel_order(
                exchange_code=exchange, order_id=order_id,
            )
            return self._ok(resp)
        except Exception as e:
            return self._fail(str(e))

    def modify_order(self, order_id, exchange, quantity=0, price=0,
                     order_type="", stoploss=0, validity=""):
        err = self._guard()
        if err:
            return err
        try:
            resp = self.breeze.modify_order(
                order_id=order_id,
                exchange_code=exchange,
                order_type=order_type or None,
                stoploss=str(stoploss) if stoploss > 0 else None,
                quantity=str(quantity) if quantity > 0 else None,
                price=str(price) if price > 0 else None,
                validity=validity or None,
            )
            return self._ok(resp)
        except Exception as e:
            return self._fail(str(e))

    def get_margin_required(self, stock_code, exchange, expiry_date,
                            strike_price, option_type, action, quantity):
        err = self._guard()
        if err:
            return err
        try:
            exp = parse_date(expiry_date)
            right = "call" if option_type.upper() == "CE" else "put"
            data = self.breeze.get_margin(
                exchange_code=exchange, stock_code=stock_code,
                product_type="options", right=right,
                strike_price=str(strike_price), expiry_date=exp,
                quantity=str(quantity), action=action.lower(),
                order_type="market", price="",
            )
            return self._ok(data)
        except Exception as e:
            return self._fail(str(e))

    def square_off_all(self, exchange=""):
        err = self._guard()
        if err:
            return [err]
    
        pos_resp = self.get_portfolio_positions()
        if not pos_resp.get("success"):
            return [pos_resp]
    
        data = pos_resp.get("data", {})
        positions = data.get("Success", []) if isinstance(data, dict) else []
        if isinstance(positions, dict):
            positions = [positions]
    
        # Import from utils (NOT from app — avoids circular import)
        from utils import PositionUtils
    
        results = []
        for p in positions:
            try:
                if exchange and p.get("exchange_code") != exchange:
                    continue
                qty = abs(int(p.get("quantity", 0)))
                if qty == 0:
                    continue
    
                pos_type = PositionUtils.detect_type(p)
    
                r = self.square_off_position(
                    p.get("stock_code", ""),
                    p.get("exchange_code", ""),
                    p.get("expiry_date", ""),
                    int(p.get("strike_price", 0)),
                    str(p.get("right", "")).upper(),
                    qty, pos_type,
                )
                results.append(r)
            except Exception as e:
                results.append(self._fail(str(e)))
    
        return results or [self._ok({"message": "No positions"})]
