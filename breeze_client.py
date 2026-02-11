"""
Breeze API Client Wrapper
Handles all interactions with ICICI Direct Breeze SDK
"""

import logging
from datetime import datetime
from typing import Dict, List, Any
import pytz

# ── NOTE ──────────────────────────────────────────────────────────────────────
# breeze_connect internally does  `from config import SECURITY_MASTER_URL`.
# Our project-level config.py already exposes that constant, so no patching
# or sys.modules hacking is needed.  Just import normally.
# ──────────────────────────────────────────────────────────────────────────────
from breeze_connect import BreezeConnect

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BreezeClientWrapper:
    """
    Wrapper class for Breeze Connect API
    Provides simplified interface for options trading
    """

    def __init__(self, api_key: str, api_secret: str):
        """Initialize Breeze client"""
        self.api_key = api_key
        self.api_secret = api_secret
        self.breeze = None
        self.is_connected = False
        self.ist = pytz.timezone("Asia/Kolkata")

    # ── connection ────────────────────────────────────────────────────────────

    def connect(self, session_token: str) -> Dict[str, Any]:
        """Connect to Breeze API with session token"""
        try:
            logger.info("Creating BreezeConnect instance...")
            self.breeze = BreezeConnect(api_key=self.api_key)

            logger.info("Generating session...")
            self.breeze.generate_session(
                api_secret=self.api_secret,
                session_token=session_token,
            )

            self.is_connected = True
            logger.info("Successfully connected to Breeze API")
            return {"success": True, "message": "Connected successfully"}

        except Exception as e:
            logger.error(f"Connection failed: {e}")
            self.is_connected = False
            return {"success": False, "message": str(e)}

    # ── account info ──────────────────────────────────────────────────────────

    def get_customer_details(self) -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            return {"success": True, "data": self.breeze.get_customer_details()}
        except Exception as e:
            logger.error(f"Failed to get customer details: {e}")
            return {"success": False, "message": str(e)}

    def get_funds(self) -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            return {"success": True, "data": self.breeze.get_funds()}
        except Exception as e:
            logger.error(f"Failed to get funds: {e}")
            return {"success": False, "message": str(e)}

    # ── market data ───────────────────────────────────────────────────────────

    def get_option_chain(
        self,
        stock_code: str,
        exchange: str,
        expiry_date: str,
        product_type: str = "options",
        strike_price: str = "",
        option_type: str = "",
    ) -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            formatted_expiry = datetime.strptime(expiry_date, "%Y-%m-%d").strftime(
                "%d-%b-%Y"
            )
            data = self.breeze.get_option_chain_quotes(
                stock_code=stock_code,
                exchange_code=exchange,
                product_type=product_type,
                expiry_date=formatted_expiry,
                right=option_type if option_type else "",
                strike_price=str(strike_price) if strike_price else "",
            )
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"Failed to get option chain: {e}")
            return {"success": False, "message": str(e)}

    def get_quotes(
        self,
        stock_code: str,
        exchange: str,
        expiry_date: str,
        strike_price: int,
        option_type: str,
        product_type: str = "options",
    ) -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            formatted_expiry = datetime.strptime(expiry_date, "%Y-%m-%d").strftime(
                "%d-%b-%Y"
            )
            right = "call" if option_type.upper() == "CE" else "put"
            data = self.breeze.get_quotes(
                stock_code=stock_code,
                exchange_code=exchange,
                expiry_date=formatted_expiry,
                product_type=product_type,
                right=right,
                strike_price=str(strike_price),
            )
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"Failed to get quotes: {e}")
            return {"success": False, "message": str(e)}

    # ── order management ──────────────────────────────────────────────────────

    def place_order(
        self,
        stock_code: str,
        exchange: str,
        expiry_date: str,
        strike_price: int,
        option_type: str,
        action: str,
        quantity: int,
        order_type: str = "market",
        price: float = 0,
        product_type: str = "options",
        stoploss: float = 0,
        validity: str = "day",
        validity_date: str = "",
        disclosed_quantity: int = 0,
    ) -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            formatted_expiry = datetime.strptime(expiry_date, "%Y-%m-%d").strftime(
                "%d-%b-%Y"
            )
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
                validity_date=validity_date,
                disclosed_quantity=(
                    str(disclosed_quantity) if disclosed_quantity > 0 else ""
                ),
                expiry_date=formatted_expiry,
                right=right,
                strike_price=str(strike_price),
            )
            logger.info(f"Order placed: {resp}")
            return {"success": True, "data": resp}
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return {"success": False, "message": str(e)}

    def sell_call(
        self, stock_code, exchange, expiry_date, strike_price,
        quantity, order_type="market", price=0,
    ) -> Dict[str, Any]:
        return self.place_order(
            stock_code=stock_code, exchange=exchange,
            expiry_date=expiry_date, strike_price=strike_price,
            option_type="CE", action="sell",
            quantity=quantity, order_type=order_type, price=price,
        )

    def sell_put(
        self, stock_code, exchange, expiry_date, strike_price,
        quantity, order_type="market", price=0,
    ) -> Dict[str, Any]:
        return self.place_order(
            stock_code=stock_code, exchange=exchange,
            expiry_date=expiry_date, strike_price=strike_price,
            option_type="PE", action="sell",
            quantity=quantity, order_type=order_type, price=price,
        )

    def square_off_position(
        self, stock_code, exchange, expiry_date, strike_price,
        option_type, quantity, current_position,
        order_type="market", price=0,
    ) -> Dict[str, Any]:
        action = "sell" if current_position.lower() == "long" else "buy"
        return self.place_order(
            stock_code=stock_code, exchange=exchange,
            expiry_date=expiry_date, strike_price=strike_price,
            option_type=option_type, action=action,
            quantity=quantity, order_type=order_type, price=price,
        )

    # ── portfolio ─────────────────────────────────────────────────────────────

    def get_portfolio_positions(self) -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            return {"success": True, "data": self.breeze.get_portfolio_positions()}
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return {"success": False, "message": str(e)}

    def get_order_list(
        self, exchange: str = "", from_date: str = "", to_date: str = ""
    ) -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            data = self.breeze.get_order_list(
                exchange_code=exchange, from_date=from_date, to_date=to_date,
            )
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return {"success": False, "message": str(e)}

    def cancel_order(self, order_id: str, exchange: str) -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            resp = self.breeze.cancel_order(
                exchange_code=exchange, order_id=order_id,
            )
            logger.info(f"Order cancelled: {order_id}")
            return {"success": True, "data": resp}
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return {"success": False, "message": str(e)}

    def modify_order(
        self, order_id: str, exchange: str,
        quantity: int = 0, price: float = 0,
        order_type: str = "", stoploss: float = 0, validity: str = "",
    ) -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
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
            logger.info(f"Order modified: {order_id}")
            return {"success": True, "data": resp}
        except Exception as e:
            logger.error(f"Failed to modify order: {e}")
            return {"success": False, "message": str(e)}

    # ── margin ────────────────────────────────────────────────────────────────

    def get_margin_required(
        self, stock_code, exchange, expiry_date, strike_price,
        option_type, action, quantity,
    ) -> Dict[str, Any]:
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            formatted_expiry = datetime.strptime(expiry_date, "%Y-%m-%d").strftime(
                "%d-%b-%Y"
            )
            right = "call" if option_type.upper() == "CE" else "put"
            data = self.breeze.get_margin(
                exchange_code=exchange, stock_code=stock_code,
                product_type="options", right=right,
                strike_price=str(strike_price),
                expiry_date=formatted_expiry,
                quantity=str(quantity), action=action.lower(),
                order_type="market", price="",
            )
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"Failed to get margin: {e}")
            return {"success": False, "message": str(e)}

    # ── bulk square-off ───────────────────────────────────────────────────────

    def square_off_all(self, exchange: str = "") -> List[Dict[str, Any]]:
        if not self.is_connected:
            return [{"success": False, "message": "Not connected"}]

        positions_response = self.get_portfolio_positions()
        if not positions_response["success"]:
            return [positions_response]

        results: List[Dict[str, Any]] = []
        for position in positions_response.get("data", {}).get("Success", []):
            try:
                if exchange and position.get("exchange_code") != exchange:
                    continue
                quantity = abs(int(position.get("quantity", 0)))
                if quantity == 0:
                    continue
                current_pos = (
                    "long" if int(position.get("quantity", 0)) > 0 else "short"
                )
                result = self.square_off_position(
                    stock_code=position.get("stock_code"),
                    exchange=position.get("exchange_code"),
                    expiry_date=position.get("expiry_date"),
                    strike_price=int(position.get("strike_price", 0)),
                    option_type=position.get("right", "").upper(),
                    quantity=quantity,
                    current_position=current_pos,
                )
                results.append(result)
            except Exception as e:
                results.append({"success": False, "message": str(e)})

        return results
