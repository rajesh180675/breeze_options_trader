"""
Breeze API Client Wrapper.
Key design:
  • format_expiry()  → DD-Mon-YYYY  (option chain, quotes, place_order, margin)
  • format_api_datetime() → ISO 8601   (get_order_list, get_trade_list)
  • Never passes empty exchange_code (fetches both NFO+BFO and merges)
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import pytz

from breeze_connect import BreezeConnect

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATE UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def format_expiry(date_str: str) -> str:
    """
    Convert any date string → DD-Mon-YYYY (what Breeze expects for
    option chain, quotes, place_order, get_margin).

    Accepts: YYYY-MM-DD, DD-Mon-YYYY, DD-MMM-YYYY, ISO, DD/MM/YYYY
    """
    if not date_str:
        return ""

    date_str = date_str.strip()

    formats = [
        ("%d-%b-%Y", False),         # 12-Feb-2026 — already OK
        ("%d-%B-%Y", True),          # 12-February-2026
        ("%Y-%m-%d", True),          # 2026-02-12
        ("%Y-%m-%dT%H:%M:%S", True), # ISO
        ("%Y-%m-%dT%H:%M:%S.%fZ", True),
        ("%d/%m/%Y", True),          # 12/02/2026
    ]

    for fmt, needs_convert in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%d-%b-%Y") if needs_convert else date_str
        except ValueError:
            continue

    logger.warning(f"Could not parse expiry date: {date_str}")
    return date_str


def format_api_datetime(date_str: str) -> str:
    """
    Convert date → ISO 8601 for Breeze order/trade list endpoints.
    Input: YYYY-MM-DD (from Streamlit date_input) or other formats.
    Output: YYYY-MM-DDTHH:MM:SS.000Z
    """
    if not date_str:
        return ""

    date_str = str(date_str).strip()

    # Already ISO?
    if "T" in date_str and "Z" in date_str:
        return date_str

    formats = [
        "%Y-%m-%d",
        "%d-%b-%Y",
        "%d-%B-%Y",
        "%d/%m/%Y",
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime("%Y-%m-%dT06:00:00.000Z")
        except ValueError:
            continue

    logger.warning(f"Could not parse API date: {date_str}")
    return date_str


def _safe_int(v: Any) -> int:
    try:
        return int(float(str(v).strip())) if v else 0
    except (ValueError, TypeError):
        return 0


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT WRAPPER
# ═══════════════════════════════════════════════════════════════════════════════

class BreezeClientWrapper:

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.breeze: Optional[BreezeConnect] = None
        self.is_connected = False
        self.ist = pytz.timezone("Asia/Kolkata")

    # ── Connection ────────────────────────────────────────────────────────

    def connect(self, session_token: str) -> Dict[str, Any]:
        try:
            self.breeze = BreezeConnect(api_key=self.api_key)
            self.breeze.generate_session(
                api_secret=self.api_secret,
                session_token=session_token,
            )
            self.is_connected = True
            logger.info("Connected to Breeze API")
            return {"success": True, "message": "Connected"}
        except Exception as e:
            self.is_connected = False
            logger.error(f"Connect failed: {e}")
            return {"success": False, "message": str(e)}

    def _check(self) -> Optional[Dict]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        return None

    # ── Account ───────────────────────────────────────────────────────────

    def get_customer_details(self) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            return {"success": True, "data": self.breeze.get_customer_details()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def get_funds(self) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            return {"success": True, "data": self.breeze.get_funds()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Market Data ───────────────────────────────────────────────────────

    def get_option_chain(
        self, stock_code: str, exchange: str, expiry_date: str,
        product_type: str = "options", strike_price: str = "",
        option_type: str = "",
    ) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            exp = format_expiry(expiry_date)
            data = self.breeze.get_option_chain_quotes(
                stock_code=stock_code,
                exchange_code=exchange,
                product_type=product_type,
                expiry_date=exp,
                right=option_type or "",
                strike_price=str(strike_price) if strike_price else "",
            )
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"Option chain error: {e}")
            return {"success": False, "message": str(e)}

    def get_quotes(
        self, stock_code: str, exchange: str, expiry_date: str,
        strike_price: int, option_type: str,
        product_type: str = "options",
    ) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            exp = format_expiry(expiry_date)
            right = "call" if option_type.upper() == "CE" else "put"
            data = self.breeze.get_quotes(
                stock_code=stock_code,
                exchange_code=exchange,
                expiry_date=exp,
                product_type=product_type,
                right=right,
                strike_price=str(strike_price),
            )
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Orders ────────────────────────────────────────────────────────────

    def place_order(
        self, stock_code: str, exchange: str, expiry_date: str,
        strike_price: int, option_type: str, action: str,
        quantity: int, order_type: str = "market", price: float = 0,
        stoploss: float = 0, validity: str = "day",
    ) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            exp = format_expiry(expiry_date)
            right = "call" if option_type.upper() in ("CE", "CALL") else "put"

            logger.info(
                f"ORDER: {action} {stock_code} {strike_price}{right} "
                f"qty={quantity} type={order_type} exp={exp}"
            )

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
            return {"success": True, "data": resp}
        except Exception as e:
            logger.error(f"Place order failed: {e}")
            return {"success": False, "message": str(e)}

    def sell_call(self, stock_code, exchange, expiry_date, strike_price,
                  quantity, order_type="market", price=0) -> Dict:
        return self.place_order(
            stock_code, exchange, expiry_date, strike_price,
            "CE", "sell", quantity, order_type, price)

    def sell_put(self, stock_code, exchange, expiry_date, strike_price,
                 quantity, order_type="market", price=0) -> Dict:
        return self.place_order(
            stock_code, exchange, expiry_date, strike_price,
            "PE", "sell", quantity, order_type, price)

    def square_off_position(
        self, stock_code, exchange, expiry_date, strike_price,
        option_type, quantity, current_position,
        order_type="market", price=0,
    ) -> Dict:
        """BUY to close short, SELL to close long."""
        action = "buy" if current_position.lower() == "short" else "sell"
        logger.info(
            f"SQUARE OFF: {action} {stock_code} {strike_price} "
            f"(was {current_position})"
        )
        return self.place_order(
            stock_code, exchange, expiry_date, strike_price,
            option_type, action, quantity, order_type, price)

    # ── Order & Trade Lists ───────────────────────────────────────────────
    #
    #  CRITICAL: These endpoints need ISO dates, NOT DD-Mon-YYYY.
    #  Also: exchange_code CANNOT be empty — Breeze throws TypeError.
    #  Solution: when user picks "All", we call both NFO and BFO and merge.

    def get_order_list(
        self, exchange: str = "", from_date: str = "", to_date: str = "",
    ) -> Dict:
        err = self._check()
        if err:
            return err

        iso_from = format_api_datetime(from_date)
        iso_to = format_api_datetime(to_date)

        exchanges = [exchange] if exchange else ["NFO", "BFO"]

        all_orders: list = []
        last_error = ""

        for exch in exchanges:
            try:
                data = self.breeze.get_order_list(
                    exchange_code=exch,
                    from_date=iso_from,
                    to_date=iso_to,
                )
                success = data.get("Success") if isinstance(data, dict) else None
                if isinstance(success, list):
                    all_orders.extend(success)
                elif isinstance(success, dict):
                    all_orders.append(success)
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Order list {exch}: {e}")

        if all_orders:
            return {"success": True, "data": {"Success": all_orders}}
        elif last_error:
            return {"success": False, "message": last_error}
        else:
            return {"success": True, "data": {"Success": []}}

    def get_trade_list(
        self, exchange: str = "", from_date: str = "", to_date: str = "",
    ) -> Dict:
        err = self._check()
        if err:
            return err

        iso_from = format_api_datetime(from_date)
        iso_to = format_api_datetime(to_date)

        exchanges = [exchange] if exchange else ["NFO", "BFO"]

        all_trades: list = []
        last_error = ""

        for exch in exchanges:
            try:
                data = self.breeze.get_trade_list(
                    from_date=iso_from,
                    to_date=iso_to,
                    exchange_code=exch,
                    product="",
                    action="",
                    stock_code="",
                )
                success = data.get("Success") if isinstance(data, dict) else None
                if isinstance(success, list):
                    all_trades.extend(success)
                elif isinstance(success, dict):
                    all_trades.append(success)
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Trade list {exch}: {e}")

        if all_trades:
            return {"success": True, "data": {"Success": all_trades}}
        elif last_error:
            return {"success": False, "message": last_error}
        else:
            return {"success": True, "data": {"Success": []}}

    # ── Cancel / Modify ───────────────────────────────────────────────────

    def cancel_order(self, order_id: str, exchange: str) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            resp = self.breeze.cancel_order(
                exchange_code=exchange, order_id=order_id)
            return {"success": True, "data": resp}
        except Exception as e:
            return {"success": False, "message": str(e)}

    def modify_order(
        self, order_id: str, exchange: str,
        quantity: int = 0, price: float = 0,
        order_type: str = "", stoploss: float = 0,
    ) -> Dict:
        err = self._check()
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
                validity=None,
            )
            return {"success": True, "data": resp}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Portfolio ─────────────────────────────────────────────────────────

    def get_portfolio_positions(self) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            return {"success": True, "data": self.breeze.get_portfolio_positions()}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Margin ────────────────────────────────────────────────────────────

    def get_margin_required(
        self, stock_code, exchange, expiry_date, strike_price,
        option_type, action, quantity,
    ) -> Dict:
        err = self._check()
        if err:
            return err
        try:
            exp = format_expiry(expiry_date)
            right = "call" if option_type.upper() in ("CE", "CALL") else "put"
            data = self.breeze.get_margin(
                exchange_code=exchange,
                stock_code=stock_code,
                product_type="options",
                right=right,
                strike_price=str(strike_price),
                expiry_date=exp,
                quantity=str(quantity),
                action=action.lower(),
                order_type="market",
                price="",
            )
            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ── Bulk Square Off ───────────────────────────────────────────────────

    def square_off_all(self, exchange: str = "") -> List[Dict]:
        err = self._check()
        if err:
            return [err]

        pos_resp = self.get_portfolio_positions()
        if not pos_resp.get("success"):
            return [pos_resp]

        data = pos_resp.get("data", {})
        positions = data.get("Success", []) if isinstance(data, dict) else []
        if isinstance(positions, dict):
            positions = [positions]

        results = []
        for p in positions:
            try:
                if exchange and p.get("exchange_code") != exchange:
                    continue
                qty = abs(_safe_int(p.get("quantity", 0)))
                if qty == 0:
                    continue

                # Detect position type
                action_field = str(p.get("action", "")).lower()
                if action_field == "sell":
                    cur_pos = "short"
                elif action_field == "buy":
                    cur_pos = "long"
                else:
                    sell_q = _safe_int(p.get("sell_quantity", 0))
                    buy_q = _safe_int(p.get("buy_quantity", 0))
                    cur_pos = "short" if sell_q > buy_q else "long"

                r = self.square_off_position(
                    stock_code=p.get("stock_code", ""),
                    exchange=p.get("exchange_code", ""),
                    expiry_date=p.get("expiry_date", ""),
                    strike_price=_safe_int(p.get("strike_price", 0)),
                    option_type=str(p.get("right", "")).upper(),
                    quantity=qty,
                    current_position=cur_pos,
                )
                results.append(r)
            except Exception as e:
                results.append({"success": False, "message": str(e)})

        return results or [{"success": True, "message": "No positions"}]
