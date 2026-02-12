"""
Breeze Options Trader — Complete Application.
═══════════════════════════════════════════════
Every navigation link works. Option chain displays properly.
Smart credential management. Correct position detection.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from functools import wraps
import time, logging

import app_config as C
from breeze_client import Client
from utils import (
    si, sf, detect_type, close_action, calc_pnl,
    market_status, fmt_inr, fmt_expiry,
    process_oc, oc_pivot, oc_pcr, oc_max_pain, oc_atm, R,
)

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE CONFIG & CSS
# ══════════════════════════════════════════════════════════════════════════════

st.set_page_config(page_title="Breeze Options Trader", page_icon="📈",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
.hdr{font-size:2.2rem;font-weight:bold;text-align:center;padding:.8rem;
  background:linear-gradient(90deg,#1f77b4,#2ecc71);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.ph{font-size:1.6rem;font-weight:bold;color:#1f77b4;
  border-bottom:3px solid #1f77b4;padding-bottom:.4rem;margin-bottom:1rem}
.con{background:#d4edda;color:#155724;padding:3px 10px;border-radius:10px;font-weight:600}
.wb{background:#fff3cd;border-left:4px solid #ffc107;padding:.8rem;margin:.8rem 0;border-radius:0 6px 6px 0}
.ib{background:#e7f3ff;border-left:4px solid #2196F3;padding:.8rem;margin:.8rem 0;border-radius:0 6px 6px 0}
.sb{background:#d4edda;border-left:4px solid #28a745;padding:.8rem;margin:.8rem 0;border-radius:0 6px 6px 0}
.db{background:#f8d7da;border-left:4px solid #dc3545;padding:.8rem;margin:.8rem 0;border-radius:0 6px 6px 0}
.profit{color:#28a745!important;font-weight:bold}
.loss{color:#dc3545!important;font-weight:bold}
.stButton>button{width:100%}
.atm-row{background:#fffde7!important}
</style>""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# STATE HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def auth() -> bool:
    return st.session_state.get("authenticated", False)

def cli() -> Client:
    return st.session_state.get("breeze")

def go(page: str):
    st.session_state.page = page

def page() -> str:
    return st.session_state.get("page", "Dashboard")

def has_secrets() -> bool:
    try:
        return bool(st.secrets.get("BREEZE_API_KEY")) and bool(st.secrets.get("BREEZE_API_SECRET"))
    except Exception:
        return False

def log_activity(action: str, detail: str = ""):
    if "activity_log" not in st.session_state:
        st.session_state.activity_log = []
    st.session_state.activity_log.insert(0, {
        "time": datetime.now(C.IST).strftime("%H:%M:%S"),
        "action": action, "detail": detail,
    })
    st.session_state.activity_log = st.session_state.activity_log[:50]

def cache_oc(key, df):
    st.session_state.oc_cache[key] = df
    st.session_state.oc_ts[key] = datetime.now()

def get_oc(key, ttl=30):
    if key not in st.session_state.get("oc_cache", {}):
        return None
    ts = st.session_state.get("oc_ts", {}).get(key)
    if ts and (datetime.now() - ts).seconds < ttl:
        return st.session_state.oc_cache[key]
    return None

def guard(fn):
    @wraps(fn)
    def w(*a, **kw):
        try:
            return fn(*a, **kw)
        except Exception as e:
            log.error(f"{fn.__name__}: {e}")
            st.error(f"❌ {e}")
    return w


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

PAGES = ["Dashboard", "Option Chain", "Sell Options",
         "Square Off", "Orders & Trades", "Positions"]
ICONS = {"Dashboard": "🏠", "Option Chain": "📊", "Sell Options": "💰",
         "Square Off": "🔄", "Orders & Trades": "📋", "Positions": "📍"}
AUTH_PAGES = set(PAGES[1:])


def sidebar():
    with st.sidebar:
        st.markdown("## 📈 Breeze Trader")
        st.markdown("---")

        # ── Nav ───────────────────────────────────────────────────
        avail = PAGES if auth() else ["Dashboard"]
        cur = page()
        if cur not in avail:
            cur = "Dashboard"
        sel = st.radio("Nav", avail, index=avail.index(cur),
                       format_func=lambda p: f"{ICONS[p]} {p}",
                       label_visibility="collapsed")
        if sel != cur:
            go(sel); st.rerun()

        st.markdown("---")

        # ── Auth ──────────────────────────────────────────────────
        if not auth():
            _login()
        else:
            _account()

        st.markdown("---")

        # ── Settings ──────────────────────────────────────────────
        st.selectbox("Instrument", list(C.INSTRUMENTS.keys()),
                     key="selected_instrument")
        st.session_state.debug = st.checkbox(
            "🔧 Debug", value=st.session_state.get("debug", False))
        st.caption("v4.0")


def _login():
    """Smart login: only token if secrets configured, else full form."""
    secrets_ok = has_secrets()

    if secrets_ok:
        st.markdown('<div class="sb">✅ API Key & Secret loaded from secrets.<br>'
                    'Enter today\'s <b>Session Token</b>.</div>', unsafe_allow_html=True)
        with st.form("fast_login"):
            token = st.text_input("Session Token", type="password",
                                  placeholder="Today's token from ICICI")
            if st.form_submit_button("🔑 Connect", use_container_width=True):
                if not token:
                    st.warning("Enter token"); return
                _do_connect(st.secrets["BREEZE_API_KEY"],
                            st.secrets["BREEZE_API_SECRET"], token)
        with st.expander("Use different credentials"):
            _full_login()
    else:
        st.markdown('<div class="ib">💡 Store API Key & Secret in '
                    '<b>Streamlit Secrets</b> for daily quick login.</div>',
                    unsafe_allow_html=True)
        _full_login()


def _full_login():
    with st.form("full_login"):
        k = st.text_input("API Key", type="password")
        s = st.text_input("API Secret", type="password")
        t = st.text_input("Session Token", type="password")
        if st.form_submit_button("🔑 Connect", use_container_width=True):
            if not all([k, s, t]):
                st.warning("Fill all fields"); return
            _do_connect(k, s, t)


def _do_connect(key, secret, token):
    with st.spinner("Connecting..."):
        c = Client(key, secret)
        r = c.connect(token)
        if r["success"]:
            st.session_state.authenticated = True
            st.session_state.breeze = c
            st.session_state.login_time = datetime.now(C.IST).isoformat()
            log_activity("Connected")
            st.success("✅ Connected!")
            time.sleep(0.5); st.rerun()
        else:
            st.error(f"❌ {r['message']}")


def _account():
    c = cli()
    if not c: return
    st.markdown('<span class="con">✅ Connected</span>', unsafe_allow_html=True)

    try:
        r = R(c.customer())
        st.markdown(f"**👤 {r.get('name', 'User')}**")
    except Exception:
        pass

    # Session duration
    lt = st.session_state.get("login_time")
    if lt:
        try:
            d = datetime.now(C.IST) - datetime.fromisoformat(lt)
            h, m = divmod(int(d.total_seconds()) // 60, 60)
            st.caption(f"⏱ {h}h {m}m")
            if d.total_seconds() > 28800:
                st.warning("⚠️ Session may be stale")
        except Exception:
            pass

    st.markdown(f"**{market_status()}**")

    try:
        r = R(c.funds())
        st.metric("Margin", fmt_inr(sf(r.get("available_margin", 0))))
    except Exception:
        pass

    if st.button("🔓 Disconnect", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.breeze = None
        go("Dashboard"); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

def pg_dash():
    st.markdown('<div class="ph">🏠 Dashboard</div>', unsafe_allow_html=True)

    if not auth():
        # Welcome
        c1, c2, c3 = st.columns(3)
        c1.markdown("### 📊 Data\n- Live option chain\n- Real-time quotes\n- OI analysis")
        c2.markdown("### 💰 Trade\n- Sell options\n- Quick square off\n- Order management")
        c3.markdown("### 🛡️ Risk\n- Margin check\n- P&L tracking\n- Debug mode")
        st.markdown("---")
        st.subheader("📈 Instruments")
        st.dataframe(pd.DataFrame([{
            "Name": n, "Code": cfg["stock_code"], "Exchange": cfg["exchange"],
            "Lot": cfg["lot"], "Gap": cfg["gap"], "Expiry": cfg["expiry_day"],
        } for n, cfg in C.INSTRUMENTS.items()]), hide_index=True, use_container_width=True)
        st.info("👈 **Login to start**")
        return

    c = cli()
    st.subheader(f"📈 {market_status()}")

    # Funds
    try:
        f = R(c.funds())
        av, us = sf(f.get("available_margin", 0)), sf(f.get("utilized_margin", 0))
        mc = st.columns(3)
        mc[0].metric("Available", fmt_inr(av))
        mc[1].metric("Used", fmt_inr(us))
        mc[2].metric("Total", fmt_inr(av + us))
    except Exception:
        pass

    st.markdown("---")

    # Positions
    st.subheader("📍 Positions")
    try:
        pos = R(c.positions())
        active = [p for p in pos.items if si(p.get("quantity")) != 0]
        if not active:
            st.info("📭 No open positions")
        else:
            tot = 0.0
            rows = []
            for p in active:
                pt = detect_type(p)
                q = abs(si(p.get("quantity")))
                avg, ltp = sf(p.get("average_price")), sf(p.get("ltp", p.get("average_price")))
                pnl = calc_pnl(pt, avg, ltp, q)
                tot += pnl
                rows.append({"Instrument": C.display_name(p.get("stock_code", "")),
                             "Strike": p.get("strike_price"), "Type": p.get("right"),
                             "Pos": pt.upper(), "Qty": q, "P&L": f"₹{pnl:+,.2f}"})
            c1, c2 = st.columns([3, 1])
            c1.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            c2.metric("Total P&L", f"₹{tot:+,.2f}",
                       delta_color="normal" if tot >= 0 else "inverse")
    except Exception as e:
        st.warning(f"Positions: {e}")

    st.markdown("---")
    st.subheader("⚡ Quick Actions")
    cc = st.columns(4)
    if cc[0].button("📊 Option Chain", use_container_width=True): go("Option Chain"); st.rerun()
    if cc[1].button("💰 Sell Options", use_container_width=True): go("Sell Options"); st.rerun()
    if cc[2].button("🔄 Square Off", use_container_width=True): go("Square Off"); st.rerun()
    if cc[3].button("📋 Orders", use_container_width=True): go("Orders & Trades"); st.rerun()

    # Activity log
    al = st.session_state.get("activity_log", [])
    if al:
        st.markdown("---")
        with st.expander("📝 Session Activity"):
            st.dataframe(pd.DataFrame(al[:15]), hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: OPTION CHAIN
# ══════════════════════════════════════════════════════════════════════════════

@guard
def pg_oc():
    st.markdown('<div class="ph">📊 Option Chain</div>', unsafe_allow_html=True)
    c = cli()
    if not c: st.warning("Connect first"); return

    # Controls
    cc = st.columns([2, 2, 1])
    with cc[0]:
        inst = st.selectbox("Instrument", list(C.INSTRUMENTS.keys()), key="oc_i")
    cfg = C.INSTRUMENTS[inst]
    with cc[1]:
        exp = st.selectbox("Expiry", C.get_expiries(inst, 5),
                           format_func=fmt_expiry, key="oc_e")
    with cc[2]:
        st.markdown("<br>", unsafe_allow_html=True)
        refresh = st.button("🔄 Refresh", key="oc_r", use_container_width=True)

    # View controls
    cc2 = st.columns([2, 1, 1])
    with cc2[0]:
        view = st.radio("View", ["Traditional", "Flat", "Calls Only", "Puts Only"],
                        horizontal=True, key="oc_v")
    with cc2[1]:
        nstrikes = st.slider("Strikes ±ATM", 5, 30, 12, key="oc_n")

    # Fetch
    ck = f"{cfg['stock_code']}_{exp}"
    cached = None if refresh else get_oc(ck)

    if cached is not None:
        df = cached
        st.caption("📦 Cached (30s)")
    else:
        with st.spinner(f"Loading {inst} ({cfg['stock_code']}) option chain..."):
            raw = c.option_chain(cfg["stock_code"], cfg["exchange"], exp)

        if not raw["success"]:
            st.error(f"❌ {raw['message']}")
            if st.session_state.get("debug"):
                st.json(raw)
            return

        df = process_oc(raw["data"])

        if df.empty:
            st.warning("No option chain data returned.")
            if st.session_state.get("debug"):
                st.write("Raw data keys:", list(raw.get("data", {}).keys()))
                success = raw.get("data", {}).get("Success", [])
                st.write(f"Success items: {len(success) if isinstance(success, list) else 'not a list'}")
                if isinstance(success, list) and success:
                    st.json(success[0])
            return

        cache_oc(ck, df)
        log_activity("Option Chain", f"{inst} {fmt_expiry(exp)}")

    # Header
    st.subheader(f"{inst} ({cfg['stock_code']}) — {fmt_expiry(exp)}")

    # Metrics
    pcr = oc_pcr(df)
    mp = oc_max_pain(df)
    atm = oc_atm(df)
    call_oi = df[df["right"] == "Call"]["open_interest"].sum() if "right" in df.columns else 0
    put_oi = df[df["right"] == "Put"]["open_interest"].sum() if "right" in df.columns else 0

    mc = st.columns(5)
    mc[0].metric("PCR", f"{pcr:.2f}", delta="Bullish" if pcr > 1 else "Bearish")
    mc[1].metric("Max Pain", f"{mp:,}")
    mc[2].metric("ATM ≈", f"{atm:,.0f}")
    mc[3].metric("Call OI", f"{call_oi:,.0f}")
    mc[4].metric("Put OI", f"{put_oi:,.0f}")

    st.markdown("---")

    # Filter strikes around ATM
    if atm > 0 and "strike_price" in df.columns:
        strikes = sorted(df["strike_price"].unique())
        # Find ATM index
        atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - atm))
        lo = max(0, atm_idx - nstrikes)
        hi = min(len(strikes), atm_idx + nstrikes + 1)
        keep = strikes[lo:hi]
        show_df = df[df["strike_price"].isin(keep)].copy()
    else:
        show_df = df.copy()

    # Display based on view selection
    if view == "Traditional":
        chain = oc_pivot(show_df)
        if chain.empty:
            st.warning("Cannot create pivot view")
        else:
            # Highlight ATM row
            def highlight_atm(row):
                if abs(row.get("Strike", 0) - atm) < cfg["gap"] / 2:
                    return ["background-color: #fffde7; font-weight: bold"] * len(row)
                return [""] * len(row)

            styled = chain.style.apply(highlight_atm, axis=1)
            styled = styled.format({c: "{:,.0f}" for c in chain.columns if c != "Strike"})
            st.dataframe(styled, use_container_width=True, height=500, hide_index=True)

    elif view == "Calls Only":
        calls = show_df[show_df["right"] == "Call"] if "right" in show_df.columns else show_df
        _show_flat(calls)
    elif view == "Puts Only":
        puts = show_df[show_df["right"] == "Put"] if "right" in show_df.columns else show_df
        _show_flat(puts)
    else:  # Flat
        _show_flat(show_df)

    # OI Chart
    if "right" in show_df.columns and "open_interest" in show_df.columns:
        st.markdown("---")
        st.subheader("📊 OI Distribution")
        calls_oi = show_df[show_df["right"] == "Call"][["strike_price", "open_interest"]].rename(
            columns={"open_interest": "Call OI"})
        puts_oi = show_df[show_df["right"] == "Put"][["strike_price", "open_interest"]].rename(
            columns={"open_interest": "Put OI"})
        merged = pd.merge(calls_oi, puts_oi, on="strike_price",
                          how="outer").fillna(0).sort_values("strike_price")
        st.bar_chart(merged.set_index("strike_price"))

    # Debug
    if st.session_state.get("debug"):
        with st.expander("🔧 Raw Data"):
            st.write(f"Total rows: {len(df)}")
            if "right" in df.columns:
                st.write(f"Calls: {len(df[df['right']=='Call'])}, Puts: {len(df[df['right']=='Put'])}")
                st.write(f"Right values: {df['right'].unique().tolist()}")
            st.dataframe(df.head(20), hide_index=True)


def _show_flat(df):
    """Show flat table with standard columns."""
    cols = ["strike_price", "right", "ltp", "open_interest", "volume",
            "best_bid_price", "best_offer_price"]
    av = [c for c in cols if c in df.columns]
    names = {"strike_price": "Strike", "right": "Type", "ltp": "LTP",
             "open_interest": "OI", "volume": "Vol",
             "best_bid_price": "Bid", "best_offer_price": "Ask"}
    st.dataframe(df[av].rename(columns=names).sort_values("Strike") if av else df,
                 use_container_width=True, height=500, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SELL OPTIONS
# ══════════════════════════════════════════════════════════════════════════════

@guard
def pg_sell():
    st.markdown('<div class="ph">💰 Sell Options</div>', unsafe_allow_html=True)
    c = cli()
    if not c: st.warning("Connect first"); return

    c1, c2 = st.columns(2)
    with c1:
        inst = st.selectbox("Instrument", list(C.INSTRUMENTS.keys()), key="s_i")
        cfg = C.INSTRUMENTS[inst]
        exp = st.selectbox("Expiry", C.get_expiries(inst, 5),
                           format_func=fmt_expiry, key="s_e")
        opt = st.radio("Option", ["CE (Call)", "PE (Put)"], horizontal=True, key="s_o")
        oc = "CE" if "CE" in opt else "PE"
        strike = st.number_input("Strike", min_value=0, step=cfg["gap"], key="s_s")

    with c2:
        lots = st.number_input("Lots", 1, 100, 1, key="s_l")
        qty = lots * cfg["lot"]
        st.info(f"**Qty:** {qty} ({lots} × {cfg['lot']})")
        ot = st.radio("Order", ["Market", "Limit"], horizontal=True, key="s_ot")
        pr = st.number_input("Price", min_value=0.0, step=0.05, key="s_p") if ot == "Limit" else 0.0

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("📊 Quote", use_container_width=True, disabled=strike <= 0):
            with st.spinner("..."):
                q = R(c.quotes(cfg["stock_code"], cfg["exchange"], exp, strike, oc))
                if q.ok:
                    d = q.items[0] if q.items else q.data
                    st.success(f"LTP ₹{d.get('ltp','?')} · Bid ₹{d.get('best_bid_price','?')} · Ask ₹{d.get('best_offer_price','?')}")
                else:
                    st.error(q.msg)
    with c2:
        if st.button("💰 Margin", use_container_width=True, disabled=strike <= 0):
            with st.spinner("..."):
                m = R(c.margin(cfg["stock_code"], cfg["exchange"], exp, strike, oc, "sell", qty))
                st.info(f"Margin: ₹{m.get('required_margin','?')}") if m.ok else st.warning("N/A")

    st.markdown('<div class="db">⚠️ Option selling has <b>UNLIMITED RISK</b>.</div>', unsafe_allow_html=True)
    ok = st.checkbox("I accept the risks", key="s_c") and strike > 0 and (ot == "Market" or pr > 0)

    if st.button(f"🔴 SELL {oc}", type="primary", use_container_width=True, disabled=not ok):
        with st.spinner("Placing..."):
            fn = c.sell_call if oc == "CE" else c.sell_put
            r = R(fn(cfg["stock_code"], cfg["exchange"], exp, strike, qty, ot.lower(), pr))
            if r.ok:
                st.markdown(f'<div class="sb">✅ Order placed! ID: {r.get("order_id","?")}</div>',
                            unsafe_allow_html=True)
                st.balloons()
                log_activity("SELL", f"{inst} {strike} {oc} x{qty}")
            else:
                st.error(f"❌ {r.msg}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SQUARE OFF
# ══════════════════════════════════════════════════════════════════════════════

@guard
def pg_sqoff():
    st.markdown('<div class="ph">🔄 Square Off</div>', unsafe_allow_html=True)
    c = cli()
    if not c: st.warning("Connect first"); return

    with st.spinner("Loading..."):
        resp = R(c.positions())
    if not resp.ok: st.error(resp.msg); return

    opts = []
    for p in resp.items:
        if str(p.get("product_type", "")).lower() != "options": continue
        q = si(p.get("quantity"))
        if q == 0: continue
        pt = detect_type(p)
        avg, ltp = sf(p.get("average_price")), sf(p.get("ltp", p.get("average_price")))
        p["_t"] = pt; p["_q"] = abs(q); p["_a"] = close_action(pt)
        p["_pnl"] = calc_pnl(pt, avg, ltp, abs(q))
        opts.append(p)

    if not opts: st.info("📭 No open option positions"); return
    st.success(f"**{len(opts)}** position(s)")

    rows = [{"Instrument": C.display_name(p.get("stock_code","")),
             "Strike": p.get("strike_price"), "Option": p.get("right"),
             "Qty": p["_q"], "Position": p["_t"].upper(),
             "P&L": f"₹{p['_pnl']:+,.2f}", "To Close": p["_a"].upper()}
            for p in opts]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if st.session_state.get("debug"):
        with st.expander("🔧 Raw"):
            for p in opts:
                st.json({k: v for k, v in p.items() if not k.startswith("_")})

    st.markdown("---")
    st.subheader("Individual Square Off")
    labels = [f"{C.display_name(p.get('stock_code',''))} {p.get('strike_price')} "
              f"{p.get('right')} | {p['_t'].upper()} | Qty:{p['_q']}"
              for p in opts]
    idx = st.selectbox("Position", range(len(labels)), format_func=lambda x: labels[x])
    sel = opts[idx]
    act = sel["_a"]

    st.markdown(f'<div class="ib">📌 <b>{sel["_t"].upper()}</b> → will <b>{act.upper()}</b> to close.</div>',
                unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1: sq_ot = st.radio("Order", ["Market", "Limit"], horizontal=True, key="sq_ot")
    with c2: sq_pr = st.number_input("Price", 0.0, step=0.05, key="sq_pr") if sq_ot == "Limit" else 0.0
    sq_q = st.slider("Qty", 1, sel["_q"], sel["_q"], key="sq_q")

    if st.button(f"🔄 {act.upper()} {sq_q} to Close", type="primary", use_container_width=True):
        with st.spinner(f"{act.upper()}ing..."):
            r = R(c.square_off(
                sel.get("stock_code"), sel.get("exchange_code"), sel.get("expiry_date"),
                si(sel.get("strike_price")), str(sel.get("right","")).upper(),
                sq_q, sel["_t"], sq_ot.lower(), sq_pr))
            if r.ok:
                st.success(f"✅ {act.upper()} order placed!")
                log_activity("Square Off", f"{sel.get('stock_code')} {sel.get('strike_price')}")
                time.sleep(1); st.rerun()
            else:
                st.error(f"❌ {r.msg}")

    st.markdown("---")
    st.subheader("⚡ Square Off ALL")
    st.markdown('<div class="db">⚠️ Closes ALL at market.</div>', unsafe_allow_html=True)
    if st.checkbox("Confirm", key="sq_all"):
        if st.button("🔴 SQUARE OFF ALL", use_container_width=True):
            with st.spinner("Closing..."):
                res = c.square_off_all()
                ok = sum(1 for r in res if r.get("success"))
                if ok: st.success(f"✅ Closed {ok}")
                if len(res) - ok: st.warning(f"⚠️ Failed {len(res)-ok}")
                time.sleep(1); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: ORDERS & TRADES
# ══════════════════════════════════════════════════════════════════════════════

@guard
def pg_orders():
    st.markdown('<div class="ph">📋 Orders & Trades</div>', unsafe_allow_html=True)
    c = cli()
    if not c: st.warning("Connect first"); return

    t1, t2, t3 = st.tabs(["📋 Orders", "📊 Trades", "📝 Activity"])

    # ── Orders ────────────────────────────────────────────────────────
    with t1:
        cc = st.columns([1, 1, 1, 1])
        with cc[0]: exch = st.selectbox("Exchange", ["All", "NFO", "BFO"], key="o_e")
        with cc[1]: fd = st.date_input("From", datetime.now().date() - timedelta(7), key="o_f")
        with cc[2]: td = st.date_input("To", datetime.now().date(), key="o_t")
        with cc[3]:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄", key="o_r", use_container_width=True): st.rerun()

        with st.spinner("Loading orders..."):
            resp = R(c.orders("" if exch == "All" else exch,
                              fd.strftime("%Y-%m-%d"), td.strftime("%Y-%m-%d")))
        if not resp.ok:
            st.error(resp.msg)
        else:
            olist = resp.items
            if not olist:
                st.info("📭 No orders")
            else:
                # Summary
                mc = st.columns(4)
                mc[0].metric("Total", len(olist))
                mc[1].metric("Executed", sum(1 for o in olist if str(o.get("order_status","")).lower() == "executed"))
                mc[2].metric("Pending", sum(1 for o in olist if str(o.get("order_status","")).lower() in ("pending","open")))
                mc[3].metric("Rejected", sum(1 for o in olist if str(o.get("order_status","")).lower() == "rejected"))
                st.dataframe(pd.DataFrame(olist), use_container_width=True, height=350, hide_index=True)

                # Manage pending
                pending = [o for o in olist if str(o.get("order_status","")).lower() in ("pending","open")]
                if pending:
                    st.markdown("---")
                    st.subheader("Manage Pending")
                    plbl = [f"#{o.get('order_id','?')} {o.get('stock_code','')} {o.get('action','')}" for o in pending]
                    pi = st.selectbox("Order", range(len(plbl)), format_func=lambda x: plbl[x], key="op_s")
                    ps = pending[pi]

                    # Show details
                    with st.expander("📄 Details", expanded=True):
                        dc = st.columns(3)
                        dc[0].write(f"**ID:** {ps.get('order_id')}"); dc[0].write(f"**Code:** {ps.get('stock_code')}")
                        dc[1].write(f"**Action:** {ps.get('action')}"); dc[1].write(f"**Strike:** {ps.get('strike_price')}")
                        dc[2].write(f"**Qty:** {ps.get('quantity')}"); dc[2].write(f"**Price:** ₹{ps.get('price')}")

                    ac = st.columns(2)
                    with ac[0]:
                        if st.button("❌ Cancel", use_container_width=True, key="op_c"):
                            with st.spinner("..."):
                                cr = R(c.cancel(ps.get("order_id"), ps.get("exchange_code")))
                                if cr.ok: st.success("✅"); log_activity("Cancel", ps.get("order_id","")); time.sleep(1); st.rerun()
                                else: st.error(cr.msg)
                    with ac[1]:
                        with st.expander("✏️ Modify"):
                            np = st.number_input("Price", 0.0, value=sf(ps.get("price", 0)), step=0.05, key="op_p")
                            nq = st.number_input("Qty", 1, value=max(1, si(ps.get("quantity", 1))), key="op_q")
                            if st.button("💾 Save", key="op_sv"):
                                mr = R(c.modify(ps.get("order_id"), ps.get("exchange_code"), nq, np))
                                if mr.ok: st.success("✅"); time.sleep(1); st.rerun()
                                else: st.error(mr.msg)

    # ── Trades ────────────────────────────────────────────────────────
    with t2:
        cc = st.columns([1, 1, 1, 1])
        with cc[0]: te = st.selectbox("Exchange", ["All", "NFO", "BFO"], key="t_e")
        with cc[1]: tf = st.date_input("From", datetime.now().date() - timedelta(7), key="t_f")
        with cc[2]: tt = st.date_input("To", datetime.now().date(), key="t_t")
        with cc[3]:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("🔄", key="t_r", use_container_width=True): st.rerun()

        with st.spinner("Loading trades..."):
            tresp = R(c.trades("" if te == "All" else te,
                               tf.strftime("%Y-%m-%d"), tt.strftime("%Y-%m-%d")))
        if not tresp.ok:
            st.error(tresp.msg)
        else:
            tlist = tresp.items
            if not tlist:
                st.info("📭 No trades")
            else:
                mc = st.columns(3)
                mc[0].metric("Total", len(tlist))
                mc[1].metric("Buys", sum(1 for t in tlist if str(t.get("action","")).lower() == "buy"))
                mc[2].metric("Sells", sum(1 for t in tlist if str(t.get("action","")).lower() == "sell"))
                st.dataframe(pd.DataFrame(tlist), use_container_width=True, height=350, hide_index=True)

    # ── Activity ──────────────────────────────────────────────────────
    with t3:
        al = st.session_state.get("activity_log", [])
        if al:
            st.dataframe(pd.DataFrame(al), hide_index=True, use_container_width=True)
        else:
            st.info("No activity this session")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: POSITIONS
# ══════════════════════════════════════════════════════════════════════════════

@guard
def pg_pos():
    st.markdown('<div class="ph">📍 Positions</div>', unsafe_allow_html=True)
    c = cli()
    if not c: st.warning("Connect first"); return

    if st.button("🔄 Refresh", key="p_r", use_container_width=True): st.rerun()

    with st.spinner("Loading..."):
        resp = R(c.positions())
    if not resp.ok: st.error(resp.msg); return

    enhanced = []
    total = 0.0
    for p in resp.items:
        q = si(p.get("quantity"))
        if q == 0: continue
        pt = detect_type(p)
        aq = abs(q)
        avg, ltp = sf(p.get("average_price")), sf(p.get("ltp", p.get("average_price")))
        pnl = calc_pnl(pt, avg, ltp, aq)
        total += pnl
        enhanced.append({"sc": p.get("stock_code",""), "disp": C.display_name(p.get("stock_code","")),
                         "ex": p.get("exchange_code",""), "exp": p.get("expiry_date",""),
                         "strike": p.get("strike_price",""), "right": p.get("right",""),
                         "qty": aq, "type": pt, "avg": avg, "ltp": ltp, "pnl": pnl, "_raw": p})

    if not enhanced: st.info("📭 No active positions"); return

    mc = st.columns(4)
    mc[0].metric("Total", len(enhanced))
    mc[1].metric("Long", sum(1 for e in enhanced if e["type"] == "long"))
    mc[2].metric("Short", sum(1 for e in enhanced if e["type"] == "short"))
    mc[3].metric("P&L", f"₹{total:+,.2f}", delta_color="normal" if total >= 0 else "inverse")

    st.dataframe(pd.DataFrame([{
        "Instrument": e["disp"], "Strike": e["strike"], "Option": e["right"],
        "Qty": e["qty"], "Position": e["type"].upper(),
        "Avg": f"₹{e['avg']:.2f}", "LTP": f"₹{e['ltp']:.2f}",
        "P&L": f"₹{e['pnl']:+,.2f}", "Close": close_action(e["type"]).upper(),
    } for e in enhanced]), use_container_width=True, hide_index=True)

    if st.session_state.get("debug"):
        with st.expander("🔧 Raw"):
            for e in enhanced: st.json(e["_raw"])

    st.markdown("---")
    for e in enhanced:
        em = "📈" if e["pnl"] >= 0 else "📉"
        badge = "🟢 LONG" if e["type"] == "long" else "🔴 SHORT"
        with st.expander(f"{em} {e['disp']} {e['strike']} {e['right']} | {badge} | ₹{e['pnl']:+,.2f}"):
            c1, c2, c3 = st.columns(3)
            c1.write(f"**Code:** {e['sc']}"); c1.write(f"**Exchange:** {e['ex']}"); c1.write(f"**Expiry:** {e['exp']}")
            c2.write(f"**Position:** {e['type'].upper()}"); c2.write(f"**Qty:** {e['qty']}"); c2.write(f"**Avg:** ₹{e['avg']:.2f}")
            color = "profit" if e["pnl"] >= 0 else "loss"
            c3.write(f"**LTP:** ₹{e['ltp']:.2f}")
            c3.markdown(f"<span class='{color}'>₹{e['pnl']:+,.2f}</span>", unsafe_allow_html=True)
            c3.write(f"**Close:** {close_action(e['type']).upper()}")
            if st.button("🔄 Square Off", key=f"sq_{e['sc']}_{e['strike']}_{e['right']}", use_container_width=True):
                go("Square Off"); st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# ROUTER
# ══════════════════════════════════════════════════════════════════════════════

ROUTER = {
    "Dashboard": pg_dash,
    "Option Chain": pg_oc,
    "Sell Options": pg_sell,
    "Square Off": pg_sqoff,
    "Orders & Trades": pg_orders,
    "Positions": pg_pos,
}


def main():
    C.init_state()
    sidebar()
    st.markdown('<h1 class="hdr">📈 Breeze Options Trader</h1>', unsafe_allow_html=True)
    st.markdown("---")
    p = page()
    if p in AUTH_PAGES and not auth():
        st.warning("🔒 Login required")
        st.info("👈 Enter credentials in sidebar")
        return
    ROUTER.get(p, pg_dash)()


if __name__ == "__main__":
    main()
