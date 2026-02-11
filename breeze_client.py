"""
Breeze API Client Wrapper
Handles all interactions with ICICI Direct Breeze SDK
"""

import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
import pytz

from breeze_connect import BreezeConnect

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_expiry_date(date_str: str) -> str:
    """
    Parse expiry date from various formats and return in DD-Mon-YYYY format
    that Breeze API expects.
    
    Handles:
    - YYYY-MM-DD (2026-02-12)
    - DD-Mon-YYYY (12-Feb-2026)
    - DD-MMM-YYYY (12-FEB-2026)
    - YYYY-MM-DDTHH:MM:SS (ISO format)
    """
    if not date_str:
        return ""
    
    # If already in correct format, return as-is
    formats_to_try = [
        ("%d-%b-%Y", None),           # 12-Feb-2026 - already correct
        ("%d-%B-%Y", "%d-%b-%Y"),     # 12-February-2026
        ("%Y-%m-%d", "%d-%b-%Y"),     # 2026-02-12
        ("%Y-%m-%dT%H:%M:%S", "%d-%b-%Y"),  # ISO format
        ("%d/%m/%Y", "%d-%b-%Y"),     # 12/02/2026
        ("%m/%d/%Y", "%d-%b-%Y"),     # 02/12/2026
    ]
    
    date_str = date_str.strip()
    
    for input_fmt, output_fmt in formats_to_try:
        try:
            dt = datetime.strptime(date_str, input_fmt)
            if output_fmt:
                return dt.strftime(output_fmt)
            else:
                return date_str  # Already in correct format
        except ValueError:
            continue
    
    # If nothing worked, return original and let API handle it
    logger.warning(f"Could not parse date: {date_str}")
    return date_str


class BreezeClientWrapper:
    """
    Wrapper class for Breeze Connect API
    Provides simplified interface for options trading
    """

    def __init__(self, api_key: str, api_secret: str):
        """Initialize Breeze client"""
        self.api_key = api_key
        self.api_secret = api_secret
        self.breeze: Optional[BreezeConnect] = None
        self.is_connected = False
        self.ist = pytz.timezone("Asia/Kolkata")

    # ═══════════════════════════════════════════════════════════════════════════
    # CONNECTION
    # ═══════════════════════════════════════════════════════════════════════════

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

    # ═══════════════════════════════════════════════════════════════════════════
    # ACCOUNT INFO
    # ═══════════════════════════════════════════════════════════════════════════

    def get_customer_details(self) -> Dict[str, Any]:
        """Get customer profile details"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            result = self.breeze.get_customer_details()
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"Failed to get customer details: {e}")
            return {"success": False, "message": str(e)}

    def get_funds(self) -> Dict[str, Any]:
        """Get available funds/margin"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            result = self.breeze.get_funds()
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"Failed to get funds: {e}")
            return {"success": False, "message": str(e)}

    # ═══════════════════════════════════════════════════════════════════════════
    # MARKET DATA
    # ═══════════════════════════════════════════════════════════════════════════

    def get_option_chain(
        self,
        stock_code: str,
        exchange: str,
        expiry_date: str,
        product_type: str = "options",
        strike_price: str = "",
        option_type: str = "",
    ) -> Dict[str, Any]:
        """Get option chain data"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            formatted_expiry = parse_expiry_date(expiry_date)
            
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
        """Get real-time quotes for specific option"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            formatted_expiry = parse_expiry_date(expiry_date)
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

    # ═══════════════════════════════════════════════════════════════════════════
    # ORDER MANAGEMENT
    # ═══════════════════════════════════════════════════════════════════════════

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
        """Place an order"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            formatted_expiry = parse_expiry_date(expiry_date)
            right = "call" if option_type.upper() == "CE" else "put"

            logger.info(f"Placing order: {stock_code} {strike_price} {right} {action} {quantity}")

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
            logger.info(f"Order response: {resp}")
            return {"success": True, "data": resp}
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return {"success": False, "message": str(e)}

    def sell_call(
        self,
        stock_code: str,
        exchange: str,
        expiry_date: str,
        strike_price: int,
        quantity: int,
        order_type: str = "market",
        price: float = 0,
    ) -> Dict[str, Any]:
        """Sell Call Option (Short Call)"""
        return self.place_order(
            stock_code=stock_code,
            exchange=exchange,
            expiry_date=expiry_date,
            strike_price=strike_price,
            option_type="CE",
            action="sell",
            quantity=quantity,
            order_type=order_type,
            price=price,
        )

    def sell_put(
        self,
        stock_code: str,
        exchange: str,
        expiry_date: str,
        strike_price: int,
        quantity: int,
        order_type: str = "market",
        price: float = 0,
    ) -> Dict[str, Any]:
        """Sell Put Option (Short Put)"""
        return self.place_order(
            stock_code=stock_code,
            exchange=exchange,
            expiry_date=expiry_date,
            strike_price=strike_price,
            option_type="PE",
            action="sell",
            quantity=quantity,
            order_type=order_type,
            price=price,
        )

    def square_off_position(
        self,
        stock_code: str,
        exchange: str,
        expiry_date: str,
        strike_price: int,
        option_type: str,
        quantity: int,
        current_position: str,
        order_type: str = "market",
        price: float = 0,
    ) -> Dict[str, Any]:
        """Square off an existing position"""
        # Determine action based on current position
        action = "sell" if current_position.lower() == "long" else "buy"
        
        logger.info(f"Squaring off: {stock_code} {strike_price} {option_type} - {action} {quantity}")
        
        return self.place_order(
            stock_code=stock_code,
            exchange=exchange,
            expiry_date=expiry_date,
            strike_price=strike_price,
            option_type=option_type,
            action=action,
            quantity=quantity,
            order_type=order_type,
            price=price,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # PORTFOLIO
    # ═══════════════════════════════════════════════════════════════════════════

    def get_portfolio_positions(self) -> Dict[str, Any]:
        """Get current portfolio positions"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            result = self.breeze.get_portfolio_positions()
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"Failed to get positions: {e}")
            return {"success": False, "message": str(e)}

    def get_portfolio_holdings(self) -> Dict[str, Any]:
        """Get portfolio holdings"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            result = self.breeze.get_portfolio_holdings(
                exchange_code="NSE",
                from_date="",
                to_date="",
                stock_code="",
                portfolio_type=""
            )
            return {"success": True, "data": result}
        except Exception as e:
            logger.error(f"Failed to get holdings: {e}")
            return {"success": False, "message": str(e)}

    def get_order_list(
        self,
        exchange: str = "",
        from_date: str = "",
        to_date: str = "",
    ) -> Dict[str, Any]:
        """Get list of orders"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            # Format dates if provided
            formatted_from = parse_expiry_date(from_date) if from_date else ""
            formatted_to = parse_expiry_date(to_date) if to_date else ""
            
            data = self.breeze.get_order_list(
                exchange_code=exchange,
                from_date=formatted_from,
                to_date=formatted_to,
            )
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return {"success": False, "message": str(e)}

    def get_trade_list(
        self,
        exchange: str = "",
        from_date: str = "",
        to_date: str = "",
    ) -> Dict[str, Any]:
        """Get list of trades"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            formatted_from = parse_expiry_date(from_date) if from_date else ""
            formatted_to = parse_expiry_date(to_date) if to_date else ""
            
            data = self.breeze.get_trade_list(
                exchange_code=exchange,
                from_date=formatted_from,
                to_date=formatted_to,
            )
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return {"success": False, "message": str(e)}

    def cancel_order(self, order_id: str, exchange: str) -> Dict[str, Any]:
        """Cancel an order"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            resp = self.breeze.cancel_order(
                exchange_code=exchange,
                order_id=order_id,
            )
            logger.info(f"Order cancelled: {order_id}")
            return {"success": True, "data": resp}
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return {"success": False, "message": str(e)}

    def modify_order(
        self,
        order_id: str,
        exchange: str,
        quantity: int = 0,
        price: float = 0,
        order_type: str = "",
        stoploss: float = 0,
        validity: str = "",
    ) -> Dict[str, Any]:
        """Modify an existing order"""
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

    # ═══════════════════════════════════════════════════════════════════════════
    # MARGIN
    # ═══════════════════════════════════════════════════════════════════════════

    def get_margin_required(
        self,
        stock_code: str,
        exchange: str,
        expiry_date: str,
        strike_price: int,
        option_type: str,
        action: str,
        quantity: int,
    ) -> Dict[str, Any]:
        """Get margin required for a trade"""
        if not self.is_connected:
            return {"success": False, "message": "Not connected"}
        try:
            formatted_expiry = parse_expiry_date(expiry_date)
            right = "call" if option_type.upper() == "CE" else "put"
            
            data = self.breeze.get_margin(
                exchange_code=exchange,
                stock_code=stock_code,
                product_type="options",
                right=right,
                strike_price=str(strike_price),
                expiry_date=formatted_expiry,
                quantity=str(quantity),
                action=action.lower(),
                order_type="market",
                price="",
            )
            return {"success": True, "data": data}
        except Exception as e:
            logger.error(f"Failed to get margin: {e}")
            return {"success": False, "message": str(e)}

    # ═══════════════════════════════════════════════════════════════════════════
    # BULK OPERATIONS
    # ═══════════════════════════════════════════════════════════════════════════

    def square_off_all(self, exchange: str = "") -> List[Dict[str, Any]]:
        """Square off all open positions"""
        if not self.is_connected:
            return [{"success": False, "message": "Not connected"}]

        positions_response = self.get_portfolio_positions()
        if not positions_response.get("success"):
            return [positions_response]

        # Handle both dict and list responses
        data = positions_response.get("data", {})
        if isinstance(data, dict):
            positions = data.get("Success", [])
        else:
            positions = []

        if isinstance(positions, dict):
            positions = [positions]

        results: List[Dict[str, Any]] = []
        
        for position in positions:
            try:
                # Filter by exchange if specified
                if exchange and position.get("exchange_code") != exchange:
                    continue

                # Skip if no quantity
                quantity = int(position.get("quantity", 0))
                if quantity == 0:
                    continue

                # Determine position type
                current_pos = "long" if quantity > 0 else "short"

                logger.info(f"Squaring off: {position.get('stock_code')} qty={quantity}")

                result = self.square_off_position(
                    stock_code=position.get("stock_code", ""),
                    exchange=position.get("exchange_code", ""),
                    expiry_date=position.get("expiry_date", ""),
                    strike_price=int(position.get("strike_price", 0)),
                    option_type=position.get("right", "").upper(),
                    quantity=abs(quantity),
                    current_position=current_pos,
                )
                results.append(result)

            except Exception as e:
                logger.error(f"Error squaring off position: {e}")
                results.append({"success": False, "message": str(e)})

        return results if results else [{"success": True, "message": "No positions to square off"}]
