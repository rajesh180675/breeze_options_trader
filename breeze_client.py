"""
Breeze API wrapper — date parsing, robust option chain fetch, all trading ops.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import pytz
from breeze_connect import BreezeConnect

log = logging.getLogger(__name__)


# ── Date Parser ───────────────────────────────────────────────────────────────

def to_breeze_date(s: str) -> str:
    """
    Convert any date string to DD-Mon-YYYY for Breeze API.
      2026-02-12   → 12-Feb-2026
      12-Feb-2026  → 12-Feb-2026  (pass-through)
      12-FEB-2026  → 12-Feb-2026
    """
    if not s or not s.strip():
        return ""
    s = s.strip()
    for fmt, convert in [
        ("%d-%b-%Y", False), ("%d-%B-%Y", True), ("%Y-%m-%d", True),
        ("%Y-%m-%dT%H:%M:%S", True), ("%d/%m/%Y", True), ("%d-%m-%Y", True),
    ]:
        try:
            dt = datetime.strptime(s, fmt)
            return dt.strftime("%d-%b-%Y") if convert else s
        except ValueError:
            continue
    log.warning(f"Cannot parse date: {s}")
    return s


# ── Client Wrapper ────────────────────────────────────────────────────────────

class Client:
    """Thin wrapper around BreezeConnect with consistent returns."""

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.api: Optional[BreezeConnect] = None
        self.connected = False

    def _ok(self, data):
        return {"success": True, "data": data, "message": ""}

    def _fail(self, msg):
        return {"success": False, "data": {}, "message": str(msg)}

    def _check(self):
        return None if self.connected else self._fail("Not connected")

    # ── Connect ───────────────────────────────────────────────────────

    def connect(self, session_token: str) -> Dict:
        try:
            self.api = BreezeConnect(api_key=self.api_key)
            self.api.generate_session(
                api_secret=self.api_secret,
                session_token=session_token,
            )
            self.connected = True
            log.info("Connected to Breeze")
            return self._ok({"message": "Connected"})
        except Exception as e:
            self.connected = False
            log.error(f"Connect: {e}")
            return self._fail(e)

    # ── Account ───────────────────────────────────────────────────────

    def customer(self) -> Dict:
        if (e := self._check()): return e
        try:
            return self._ok(self.api.get_customer_details())
        except Exception as e:
            return self._fail(e)

    def funds(self) -> Dict:
        if (e := self._check()): return e
        try:
            return self._ok(self.api.get_funds())
        except Exception as e:
            return self._fail(e)

    # ── Option Chain (CRITICAL FIX) ───────────────────────────────────
    #
    # Breeze API requires `right` = "call" or "put".
    # We fetch BOTH sides and merge them.

    def option_chain(self, stock_code: str, exchange: str,
                     expiry: str) -> Dict:
        """Fetch complete option chain — calls + puts merged."""
        if (e := self._check()): return e

        exp = to_breeze_date(expiry)
        all_records: List[Dict] = []
        errors = []

        for side in ("call", "put"):
            try:
                result = self.api.get_option_chain_quotes(
                    stock_code=stock_code,
                    exchange_code=exchange,
                    product_type="options",
                    expiry_date=exp,
                    right=side,
                    strike_price="",
                )
                if isinstance(result, dict):
                    rows = result.get("Success", [])
                    if isinstance(rows, list):
                        all_records.extend(rows)
                        log.info(f"OC {stock_code} {side}: {len(rows)} rows")
                    else:
                        log.warning(f"OC {side}: Success not a list")
                else:
                    log.warning(f"OC {side}: unexpected type {type(result)}")
            except Exception as e:
                log.error(f"OC {side}: {e}")
                errors.append(f"{side}: {e}")

        if all_records:
            return self._ok({"Success": all_records})

        return self._fail(
            f"No option chain data. Errors: {'; '.join(errors)}"
            if errors else "No option chain data returned"
        )

    # ── Quotes ────────────────────────────────────────────────────────

    def quotes(self, stock_code, exchange, expiry,
               strike, opt_type) -> Dict:
        if (e := self._check()): return e
        try:
            return self._ok(self.api.get_quotes(
                stock_code=stock_code, exchange_code=exchange,
                expiry_date=to_breeze_date(expiry),
                product_type="options",
                right="call" if opt_type.upper() == "CE" else "put",
                strike_price=str(strike),
            ))
        except Exception as e:
            return self._fail(e)

    # ── Order Placement ───────────────────────────────────────────────

    def place(self, stock_code, exchange, expiry, strike,
              opt_type, action, qty,
              order_type="market", price=0) -> Dict:
        if (e := self._check()): return e
        try:
            right = "call" if opt_type.upper() == "CE" else "put"
            resp = self.api.place_order(
                stock_code=stock_code, exchange_code=exchange,
                product="options", action=action.lower(),
                order_type=order_type.lower(),
                quantity=str(qty),
                price=str(price) if order_type.lower() == "limit" else "",
                validity="day", validity_date="",
                stoploss="", disclosed_quantity="",
                expiry_date=to_breeze_date(expiry),
                right=right, strike_price=str(strike),
            )
            log.info(f"Order: {action} {stock_code} {strike}{right} x{qty}")
            return self._ok(resp)
        except Exception as e:
            log.error(f"Order: {e}")
            return self._fail(e)

    def sell_call(self, sc, ex, exp, strike, qty, ot="market", pr=0):
        return self.place(sc, ex, exp, strike, "CE", "sell", qty, ot, pr)

    def sell_put(self, sc, ex, exp, strike, qty, ot="market", pr=0):
        return self.place(sc, ex, exp, strike, "PE", "sell", qty, ot, pr)

    def square_off(self, sc, ex, exp, strike, opt_type, qty,
                   pos_type, ot="market", pr=0):
        action = "buy" if pos_type == "short" else "sell"
        log.info(f"Square off: {action} {sc} {strike} {opt_type} x{qty}")
        return self.place(sc, ex, exp, strike, opt_type, action, qty, ot, pr)

    # ── Portfolio ─────────────────────────────────────────────────────

    def positions(self) -> Dict:
        if (e := self._check()): return e
        try:
            return self._ok(self.api.get_portfolio_positions())
        except Exception as e:
            return self._fail(e)

    def orders(self, exchange="", from_d="", to_d="") -> Dict:
        if (e := self._check()): return e
        try:
            return self._ok(self.api.get_order_list(
                exchange_code=exchange,
                from_date=to_breeze_date(from_d) if from_d else "",
                to_date=to_breeze_date(to_d) if to_d else "",
            ))
        except Exception as e:
            return self._fail(e)

    def trades(self, exchange="", from_d="", to_d="") -> Dict:
        if (e := self._check()): return e
        try:
            return self._ok(self.api.get_trade_list(
                exchange_code=exchange,
                from_date=to_breeze_date(from_d) if from_d else "",
                to_date=to_breeze_date(to_d) if to_d else "",
            ))
        except Exception as e:
            return self._fail(e)

    def cancel(self, order_id, exchange) -> Dict:
        if (e := self._check()): return e
        try:
            return self._ok(self.api.cancel_order(
                exchange_code=exchange, order_id=order_id))
        except Exception as e:
            return self._fail(e)

    def modify(self, order_id, exchange, qty=0, price=0) -> Dict:
        if (e := self._check()): return e
        try:
            return self._ok(self.api.modify_order(
                order_id=order_id, exchange_code=exchange,
                quantity=str(qty) if qty > 0 else None,
                price=str(price) if price > 0 else None,
                order_type=None, stoploss=None, validity=None,
            ))
        except Exception as e:
            return self._fail(e)

    def margin(self, sc, ex, exp, strike, opt_type, action, qty) -> Dict:
        if (e := self._check()): return e
        try:
            return self._ok(self.api.get_margin(
                exchange_code=ex, stock_code=sc,
                product_type="options",
                right="call" if opt_type.upper() == "CE" else "put",
                strike_price=str(strike),
                expiry_date=to_breeze_date(exp),
                quantity=str(qty), action=action.lower(),
                order_type="market", price="",
            ))
        except Exception as e:
            return self._fail(e)

    def square_off_all(self, exchange="") -> List[Dict]:
        if (e := self._check()): return [e]
        from utils import detect_type
        pr = self.positions()
        if not pr["success"]:
            return [pr]
        data = pr.get("data", {})
        items = data.get("Success", []) if isinstance(data, dict) else []
        if isinstance(items, dict):
            items = [items]
        results = []
        for p in items:
            try:
                if exchange and p.get("exchange_code") != exchange:
                    continue
                qty = abs(int(p.get("quantity", 0)))
                if qty == 0:
                    continue
                pt = detect_type(p)
                r = self.square_off(
                    p.get("stock_code", ""), p.get("exchange_code", ""),
                    p.get("expiry_date", ""), int(p.get("strike_price", 0)),
                    str(p.get("right", "")).upper(), qty, pt,
                )
                results.append(r)
            except Exception as e:
                results.append(self._fail(e))
        return results or [self._ok({"message": "Nothing to close"})]
