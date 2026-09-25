"""
Trade Blotter - Streamlit Application

Main entry point of the application.
This module manages the user interface, navigation, dashboards,
trade capture, confirmation workflow and audit trail views.
"""

import os
from datetime import date, datetime, timedelta
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st
from dotenv import load_dotenv

from core.database import init_db, connect
from services.trade_service import book_trade, list_trades, mark_matched, validate_trade_errors
from services.counterparty_service import list_counterparties, get_counterparty
from services.confirmation_service import generate_confirmation, render_trade_recap
from services.email_service import send_confirmation
from services.exposure_service import exposure_tables
from services.user_service import list_users
from seed_demo import seed


load_dotenv()

st.set_page_config(page_title="Trade Blotter", page_icon="▦", layout="wide", initial_sidebar_state="expanded")

init_db()

# Seed the synthetic demo dataset only when the database is empty.
# This makes fresh deployments immediately usable without resetting
# trades created during normal Streamlit reruns.
if not list_trades():
    seed()


NAVY="#17365D"; BLUE="#2E75B6"; PALE="#EAF2F8"; GREEN="#16794B"; ORANGE="#B76500"; RED="#B42318"; MUTED="#667085"

st.markdown(f"""<style>

.block-container{{padding-top:2rem;padding-bottom:3rem;max-width:1500px}}

[data-testid="stSidebar"]{{background:#F7F9FC;border-right:1px solid #E4E9F0}}

[data-testid="stSidebar"] div[role="radiogroup"]{{gap:.25rem}}

[data-testid="stSidebar"] div[role="radiogroup"] label{{padding:.58rem .7rem;border-radius:8px;transition:.15s}}

[data-testid="stSidebar"] div[role="radiogroup"] label:hover{{background:#EAF2F8}}

[data-testid="stSidebar"] div[role="radiogroup"] label > div:first-child{{display:none}}

[data-testid="stMetric"]{{border:1px solid #E2E8F0;padding:14px 16px;border-radius:12px;background:white}}

.hero{{padding:4.2rem 1rem 2.5rem;text-align:center}}

.hero h1{{font-size:3.5rem;color:{NAVY};margin-bottom:.35rem;letter-spacing:-1px}}

.hero .tag{{font-size:1.25rem;color:#475467;margin-bottom:1.6rem}}

.hero .author{{margin-top:2.2rem;font-size:1rem;color:#475467}}

.home-card{{border:1px solid #E2E8F0;border-radius:14px;padding:1.35rem;background:#fff;min-height:155px}}

.home-card h3{{color:{NAVY};margin:.1rem 0 .55rem}}

.page-title{{font-size:2.1rem;font-weight:700;color:#202939;margin-bottom:.1rem}}

.page-sub{{color:{MUTED};margin-bottom:1.5rem}}

.badge{{display:inline-block;padding:.25rem .58rem;border-radius:999px;font-size:.78rem;font-weight:700}}

.badge-green{{background:#E8F5EE;color:{GREEN}}}.badge-blue{{background:#EAF2F8;color:{BLUE}}}.badge-orange{{background:#FFF3E0;color:{ORANGE}}}.badge-red{{background:#FEECEB;color:{RED}}}.badge-gray{{background:#F2F4F7;color:#475467}}

.timeline{{display:flex;align-items:center;margin:1rem 0 1.4rem;gap:.35rem}}

.step{{flex:1;text-align:center;padding:.7rem .35rem;border-radius:9px;background:#F2F4F7;color:#667085;font-weight:700;font-size:.82rem}}

.step.done{{background:#E8F5EE;color:{GREEN}}}.step.current{{background:#EAF2F8;color:{NAVY};border:1px solid #A9C7E6}}

.connector{{color:#98A2B3;font-weight:700}}

.demo-pill{{font-size:.78rem;color:#475467;border:1px solid #D0D5DD;border-radius:999px;padding:.25rem .55rem;display:inline-block}}

</style>""",unsafe_allow_html=True)


ALL_PAGES=["⌂  Home","▦  Dashboard","≡  Trade Blotter","＋  Book Trade","✓  Confirmations","◷  Audit Trail"]

st.sidebar.markdown(f"<div style='font-size:1.25rem;font-weight:800;color:{NAVY};padding:.5rem .15rem .7rem'>TRADE BLOTTER</div>",unsafe_allow_html=True)


users=list_users()

if not users:

    st.error("No demo users are configured.")
    st.stop()

user_by_label={f"{u['full_name']} — {u['role'].title()}":u for u in users}

if "current_user_label" not in st.session_state or st.session_state.current_user_label not in user_by_label:

    default=next((label for label,u in user_by_label.items() if u["role"]=="TRADER"),next(iter(user_by_label)))
    st.session_state.current_user_label=default

current_label=st.sidebar.selectbox("Current User",list(user_by_label),key="current_user_label",help="Demo identity used for role-based access and audit events.")

current_user=user_by_label[current_label]

current_role=current_user["role"]

current_name=current_user["full_name"]

st.sidebar.caption(f"Demo User · {current_role.title()}")


PAGES=[p for p in ALL_PAGES if not (p.endswith("Book Trade") and current_role!="TRADER")]

page_names=[p.split("  ",1)[1] for p in PAGES]

if "active_page" not in st.session_state or st.session_state.active_page not in page_names:

    st.session_state.active_page="Home"

for idx, label in enumerate(PAGES):

    name=label.split("  ",1)[1]
    if st.sidebar.button(label, key=f"nav_{idx}_{name}", type="primary" if st.session_state.active_page==name else "secondary", use_container_width=True):
        st.session_state.active_page=name
        st.rerun()

st.sidebar.markdown("---")

st.sidebar.markdown("<div class='demo-pill'>● DEMO ENVIRONMENT</div><div style='font-size:.78rem;color:#667085;margin-top:.45rem'>100% synthetic data</div>",unsafe_allow_html=True)

page=st.session_state.active_page


# ---------------------------------------
# Shared trade data and display helpers
# ---------------------------------------

trades = list_trades()
df = pd.DataFrame(trades)

if not df.empty:

    df["trade_date_dt"] = pd.to_datetime(df["trade_date"]).dt.date


def compact_amount(value, signed=False):
    """Format large amounts for dense UI tables without changing stored values."""
    if value is None or pd.isna(value):
        return "—"
    value = float(value)
    sign = "+" if signed and value > 0 else ""
    absolute = abs(value)
    if absolute >= 1_000_000_000:
        return f"{sign}{value / 1_000_000_000:,.1f}bn"
    if absolute >= 1_000_000:
        return f"{sign}{value / 1_000_000:,.1f}m"
    if absolute >= 1_000:
        return f"{sign}{value / 1_000:,.0f}k"
    return f"{sign}{value:,.0f}"


def moneyish(value):
    return compact_amount(value, signed=True)


def display_side(r):
    if r["product"] == "Bond":
        return r.get("side") or ""
    if r["product"] == "IRS":
        return r.get("direction") or ""
    return f"BUY {r.get('buy_currency', '')}"


def display_amount(r):
    if r["product"] == "Bond":
        return r.get("face_amount")
    if r["product"] == "IRS":
        return r.get("notional")
    return r.get("buy_amount")


def currency_for(r):
    if r["product"] == "Bond":
        return r.get("bond_currency")
    if r["product"] == "IRS":
        return r.get("irs_currency")
    return r.get("buy_currency")


def trade_economics(r):
    """Compact, product-aware economics used in the main blotter."""
    if r["product"] == "Bond":
        return f"{r.get('bond_currency', '')} {compact_amount(r.get('face_amount'))} · Price {r.get('clean_price', 0):.2f}"
    if r["product"] == "IRS":
        direction = str(r.get("direction", "")).replace("_", " ").title()
        return f"{r.get('irs_currency', '')} {compact_amount(r.get('notional'))} · {direction} {r.get('fixed_rate', 0):.3f}%"
    return (
        f"Buy {r.get('buy_currency', '')} {compact_amount(r.get('buy_amount'))} / "
        f"Sell {r.get('sell_currency', '')} {compact_amount(r.get('sell_amount'))} · "
        f"Fwd {r.get('forward_rate', 0):.4f}"
    )


def age_days(r):
    trade_date = pd.to_datetime(r["trade_date"]).date()
    return max((date.today() - trade_date).days, 0)


def is_exception(r):
    return r["confirmation_status"] != "MATCHED" and age_days(r) > 1


def control_status(r):
    return "EXCEPTION" if is_exception(r) else "OK"


def status_badge(status, exception=False):
    if exception:
        return "<span class='badge badge-red'>EXCEPTION</span>"
    palette = {
        "MATCHED": "green",
        "SENT": "blue",
        "SENT_DEMO": "blue",
        "GENERATED": "orange",
        "NOT_GENERATED": "gray",
    }
    cls = palette.get(status, "gray")
    return f"<span class='badge badge-{cls}'>{status.replace('_', ' ')}</span>"


def page_header(title, subtitle):
    st.markdown(f"<div class='page-title'>{title}</div><div class='page-sub'>{subtitle}</div>",unsafe_allow_html=True)


def audit_for(trade_id):
    with connect() as con:
        return pd.read_sql_query("SELECT * FROM audit_events WHERE trade_id=? ORDER BY event_time",con,params=(trade_id,))


def style_status_table(frame):
    """Use workflow colours for normal trades and red only for true exceptions."""
    status_col = frame.columns.get_loc("confirmation_status") if "confirmation_status" in frame.columns else None


    def row_style(row):
        styles = [""] * len(row)
        if row.get("control_status") == "EXCEPTION":
            return ["background-color:#FEECEB;color:#7A271A"] * len(row)
        if status_col is not None:
            status = row.get("confirmation_status")
            palette = {
                "MATCHED": "background-color:#E8F5EE;color:#16794B;font-weight:700",
                "SENT": "background-color:#EAF2F8;color:#2E75B6;font-weight:700",
                "SENT_DEMO": "background-color:#EAF2F8;color:#2E75B6;font-weight:700",
                "GENERATED": "background-color:#FFF3E0;color:#B76500;font-weight:700",
                "NOT_GENERATED": "background-color:#F2F4F7;color:#475467;font-weight:700",
            }
            styles[status_col] = palette.get(status, "")
        return styles


    return frame.style.apply(row_style, axis=1)


def elapsed_since(timestamp):
    if not timestamp or timestamp == "Pending":
        return None
    try:
        delta = datetime.now() - pd.to_datetime(timestamp).to_pydatetime()
    except (TypeError, ValueError):
        return None
    total_minutes = max(int(delta.total_seconds() // 60), 0)
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    if total_minutes < 1:
        return "just now"
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


# ======
# Home
# ======

if page == "Home":

    st.markdown("<div class='hero'><h1>TRADE BLOTTER</h1><div class='tag'>Post-Trade Management & Control Platform</div><div style='color:#667085'>Trade Capture  •  Confirmations  •  Matching  •  Positions  •  Audit & Controls</div><div class='author'>Developed by<br><b style='color:#17365D;font-size:1.15rem'>Gaspar RAYBAUD-MABILY</b></div></div>",unsafe_allow_html=True)
    c1,c2,c3=st.columns(3)
    with c1: st.markdown("<div class='home-card'><h3>TRADE CAPTURE</h3><p>Product-aware booking for Bonds, Interest Rate Swaps and FX Forwards with structured economics.</p></div>",unsafe_allow_html=True)
    with c2: st.markdown("<div class='home-card'><h3>POST-TRADE CONTROL</h3><p>Confirmation generation, simulated delivery, matching workflow, exception aging and persistent audit trail.</p></div>",unsafe_allow_html=True)
    with c3: st.markdown("<div class='home-card'><h3>POSITION MONITORING</h3><p>Product-specific net position views with clear conventions for Bonds, IRS and FX Forwards.</p></div>",unsafe_allow_html=True)
    st.markdown("<div style='text-align:center;color:#667085;margin-top:2.3rem'>Python • Streamlit • SQLite • Plotly • ReportLab<br><span style='font-size:.82rem'>Portfolio demonstration — all entities and trade data are synthetic.</span></div>",unsafe_allow_html=True)


# ============
# Dashboard
# ============

elif page == "Dashboard":

    page_header("Post-Trade Control Room","Monitor confirmation workflow, open exceptions and product-specific positions.")
    if df.empty: st.warning("No trades yet. Run seed_demo.py or book the first trade.")
    else:
        counts=df["confirmation_status"].value_counts(); total=len(df)
        pending=int(counts.get("NOT_GENERATED",0)); generated=int(counts.get("GENERATED",0)); awaiting=int(counts.get("SENT_DEMO",0)+counts.get("SENT",0)); matched=int(counts.get("MATCHED",0))
        cols=st.columns(5)
        for c,label,val in zip(cols,["Total trades","Pending generation","Generated / not sent","Awaiting match","Matched"],[total,pending,generated,awaiting,matched]): c.metric(label,val)
        st.markdown("### Confirmation & exception monitoring")
        st.info("**Exception definition** — A trade is flagged as an exception when its confirmation workflow remains incomplete for more than 1 day. This includes trades whose recap has not progressed to matching and confirmations sent but still unmatched.")
        work=df.copy(); work["age_days"]=work.apply(age_days,axis=1); work["control_status"]=work.apply(control_status,axis=1)
        exc=work[work.control_status=="EXCEPTION"].copy(); no_conf=exc[exc.confirmation_status.isin(["NOT_GENERATED","GENERATED"])] ; sent_aged=exc[exc.confirmation_status.isin(["SENT","SENT_DEMO"])]
        a,b,c=st.columns(3); a.metric("Unmatched > 1d",len(exc)); b.metric("No confirmation > 1d",len(no_conf)); c.metric("Sent / unmatched > 1d",len(sent_aged))
        left,right=st.columns(2)
        order=["NOT_GENERATED","GENERATED","SENT_DEMO","SENT","MATCHED"]
        status_df=work.groupby("confirmation_status").size().reset_index(name="trades")
        with left:
            fig=px.bar(status_df,x="confirmation_status",y="trades",title="Confirmation workflow",category_orders={"confirmation_status":order},text="trades")
            fig.update_layout(xaxis_title="",yaxis_title="Trades",showlegend=False); st.plotly_chart(fig,use_container_width=True)
        with right:
            if exc.empty: st.success("No open exceptions.")
            else:
                cp=exc.groupby("counterparty").size().sort_values(ascending=True).reset_index(name="exceptions")
                fig=px.bar(cp,x="exceptions",y="counterparty",orientation="h",title="Exceptions by counterparty",text="exceptions")
                fig.update_layout(xaxis_title="Exceptions",yaxis_title="",showlegend=False); st.plotly_chart(fig,use_container_width=True)
        st.markdown("### Position Overview")
        st.caption("Position measures are product-specific. They are not market value, P&L or a complete risk measure.")
        exp=exposure_tables(); e1,e2,e3=st.columns(3)
        with e1:
            st.markdown("**Bonds · Net Face Position**")
            if exp["bond"].empty: st.write("No bond position")
            else:
                for _,r in exp["bond"].iterrows(): st.metric(r.currency,moneyish(r.net_face_amount))
        with e2:
            st.markdown("**IRS · Net Fixed-Leg Notional**"); st.caption("Receive Fixed = + · Pay Fixed = −")
            if exp["irs"].empty: st.write("No IRS position")
            else:
                for _,r in exp["irs"].iterrows(): st.metric(r.currency,moneyish(r.net_fixed_notional))
        with e3:
            st.markdown("**FX Forwards · Net Currency Position**")
            if exp["fx"].empty: st.write("No FX position")
            else:
                for _,r in exp["fx"].iterrows(): st.metric(r.currency,moneyish(r.net_amount))
        st.markdown("### Oldest open exceptions")
        if exc.empty: st.success("No open exceptions.")
        else:
            oldest=exc.sort_values(["age_days","trade_date"],ascending=[False,True]).head(12).copy()
            oldest["direction"]=oldest.apply(display_side,axis=1)
            show=oldest[["trade_id","age_days","product","instrument","direction","counterparty","confirmation_status","control_status"]]
            st.dataframe(style_status_table(show),use_container_width=True,hide_index=True)
        st.markdown("### Activity mix")
        mix=df.groupby("product").size().reset_index(name="trades")
        fig=px.bar(mix,x="product",y="trades",text="trades",title="Trades by product")
        fig.update_layout(xaxis_title="",yaxis_title="Trades")
        st.plotly_chart(fig,use_container_width=True)


        st.markdown("### Today's Trading Activity")
        today_df=work[work["trade_date_dt"]==date.today()].copy()
        t1,t2,t3=st.columns(3)
        t1.metric("Trades today",len(today_df))
        t2.metric("Active traders",today_df["trader"].nunique() if not today_df.empty else 0)
        t3.metric("Counterparties",today_df["counterparty"].nunique() if not today_df.empty else 0)
        if today_df.empty:
            st.caption("No trades are dated today in the current synthetic dataset. New trades booked today will appear here automatically.")
        else:
            daily_mix=today_df.groupby("product").size().to_dict()
            st.caption(" · ".join(f"{product}: {daily_mix.get(product,0)}" for product in ["Bond","IRS","FX Forward"]))


        st.markdown("### Trading Analytics")
        analysis=st.selectbox("Analysis",["Trade Activity Over Time","Trades by Trader","Trades by Counterparty","Confirmation Aging"],label_visibility="collapsed")
        if analysis=="Trade Activity Over Time":
            activity=work.groupby("trade_date_dt").size().reset_index(name="trades").sort_values("trade_date_dt")
            activity["trade_date_dt"]=activity["trade_date_dt"].astype(str)
            fig=px.line(activity,x="trade_date_dt",y="trades",markers=True,title="Trade Activity Over Time")
            fig.update_layout(xaxis_title="Trade date",yaxis_title="Trades")
        elif analysis=="Trades by Trader":
            analytics=work.groupby("trader").size().sort_values(ascending=True).reset_index(name="trades")
            fig=px.bar(analytics,x="trades",y="trader",orientation="h",text="trades",title="Trades by Trader")
            fig.update_layout(xaxis_title="Trades",yaxis_title="")
        elif analysis=="Trades by Counterparty":
            analytics=work.groupby("counterparty").size().sort_values(ascending=True).reset_index(name="trades")
            fig=px.bar(analytics,x="trades",y="counterparty",orientation="h",text="trades",title="Trades by Counterparty")
            fig.update_layout(xaxis_title="Trades",yaxis_title="")
        else:
            with connect() as con:
                sent_events=pd.read_sql_query("SELECT trade_id, MAX(event_time) AS sent_at FROM audit_events WHERE event_type='EMAIL_SENT_DEMO' GROUP BY trade_id",con)
            sent_open=work[work["confirmation_status"].isin(["SENT","SENT_DEMO"])][["trade_id"]].merge(sent_events,on="trade_id",how="left")
            now=datetime.now()
            def aging_bucket(ts):
                if pd.isna(ts): return "Unknown"
                hours=max((now-pd.to_datetime(ts).to_pydatetime()).total_seconds()/3600,0)
                if hours<1: return "< 1h"
                if hours<4: return "1–4h"
                if hours<24: return "4–24h"
                return "> 24h"
            sent_open["bucket"]=sent_open["sent_at"].apply(aging_bucket)
            order_buckets=["< 1h","1–4h","4–24h","> 24h","Unknown"]
            analytics=sent_open.groupby("bucket").size().reindex(order_buckets,fill_value=0).reset_index(name="trades")
            fig=px.bar(analytics,x="bucket",y="trades",text="trades",title="Confirmation Aging",category_orders={"bucket":order_buckets})
            fig.update_layout(xaxis_title="Time since sent",yaxis_title="Awaiting match")
        st.plotly_chart(fig,use_container_width=True)


# ===============
# Trade Blotter
# ===============

elif page == "Trade Blotter":

    page_header("Trade Blotter", "Search, filter and inspect booked trades and their product economics.")
    if df.empty:
        st.info("No trades booked.")
    else:
        work = df.copy()
        work["control_status"] = work.apply(control_status, axis=1)
        work["direction"] = work.apply(display_side, axis=1)
        work["currency"] = work.apply(currency_for, axis=1)
        work["trade_economics"] = work.apply(trade_economics, axis=1)


        q = st.text_input("Search", placeholder="Trade ID, instrument, counterparty, trader...")
        f1, f2, f3, f4 = st.columns(4)
        products = f1.multiselect("Product", sorted(work["product"].dropna().unique()))
        desks = f2.multiselect("Desk", sorted(work["desk"].dropna().unique()))
        counterparties = f3.multiselect("Counterparty", sorted(work["counterparty"].dropna().unique()))
        statuses = f4.multiselect("Workflow status", sorted(work["confirmation_status"].dropna().unique()))


        f5, f6, f7 = st.columns(3)
        currencies = f5.multiselect("Currency", sorted(work["currency"].dropna().unique()))
        controls = f6.multiselect("Control status", ["OK", "EXCEPTION"])
        date_range = f7.date_input(
            "Trade date range",
            value=(work["trade_date_dt"].min(), work["trade_date_dt"].max()),
        )


        view = work.copy()
        if q:
            mask = view.astype(str).apply(
                lambda col: col.str.contains(q, case=False, na=False)
            ).any(axis=1)
            view = view[mask]
        if products:
            view = view[view["product"].isin(products)]
        if desks:
            view = view[view["desk"].isin(desks)]
        if counterparties:
            view = view[view["counterparty"].isin(counterparties)]
        if statuses:
            view = view[view["confirmation_status"].isin(statuses)]
        if currencies:
            view = view[view["currency"].isin(currencies)]
        if controls:
            view = view[view["control_status"].isin(controls)]
        if isinstance(date_range, (tuple, list)) and len(date_range) == 2:
            start_date, end_date = date_range
            view = view[
                (view["trade_date_dt"] >= start_date)
                & (view["trade_date_dt"] <= end_date)
            ]


        st.caption(f"{len(view)} trade(s) shown")
        table = view[[
            "trade_id", "trade_date", "trader", "desk", "product", "instrument",
            "direction", "trade_economics", "counterparty", "confirmation_status", "control_status",
        ]].rename(columns={
            "trade_id": "Trade ID",
            "trade_date": "Trade Date",
            "trader": "Trader",
            "desk": "Desk",
            "product": "Product",
            "instrument": "Instrument",
            "direction": "Direction",
            "trade_economics": "Trade Economics",
            "counterparty": "Counterparty",
            "confirmation_status": "confirmation_status",
            "control_status": "control_status",
        })
        styled = style_status_table(table).set_properties(
            subset=["Trade Economics"], **{"font-weight": "600"}
        )
        st.dataframe(
            styled,
            use_container_width=True,
            hide_index=True,
            column_config={
                "confirmation_status": "Workflow Status",
                "control_status": "Control Status",
                "Trade Economics": st.column_config.TextColumn("Trade Economics", width="large"),
            },
        )


        st.markdown("### Trade Details")
        if view.empty:
            st.info("No trade matches the current filters.")
        else:
            trade_id = st.selectbox("Select a trade", view["trade_id"].tolist())
            row = view[view["trade_id"] == trade_id].iloc[0]
            exception_badge = status_badge(row["confirmation_status"], True) if row["control_status"] == "EXCEPTION" else ""
            st.markdown(
                f"**{row['instrument']}**   {status_badge(row['confirmation_status'])}   {exception_badge}",
                unsafe_allow_html=True,
            )


            c1, c2, c3, c4 = st.columns(4)
            detail_cards = [
                (c1, "Product", row["product"]),
                (c2, "Direction", row["direction"]),
                (c3, "Trade Economics", trade_economics(row)),
                (c4, "Counterparty", row["counterparty"]),
            ]
            for col, label, value in detail_cards:
                col.markdown(
                    f"""<div style='border:1px solid #E2E8F0;border-radius:12px;background:#fff;padding:14px 16px;min-height:118px'>
                    <div style='font-size:.9rem;color:#344054;margin-bottom:.65rem'>{label}</div>
                    <div style='font-size:1.45rem;line-height:1.25;font-weight:500;color:#202939;overflow-wrap:anywhere'>{value}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )


            if row["product"] == "Bond":
                details = {
                    "Face Amount": f"{row['bond_currency']} {row['face_amount']:,.0f}",
                    "Clean Price": f"{row['clean_price']:.4f}",
                    "ISIN": row["isin"],
                    "Maturity": row["bond_maturity"],
                    "Settlement": row["settlement_date"],
                }
            elif row["product"] == "IRS":
                details = {
                    "Notional": f"{row['irs_currency']} {row['notional']:,.0f}",
                    "Fixed Rate": f"{row['fixed_rate']:.4f}%",
                    "Floating Index": row["floating_index"],
                    "Effective Date": row["effective_date"],
                    "Maturity": row["irs_maturity"],
                }
            else:
                details = {
                    "Currency Pair": row["currency_pair"],
                    "Buy Amount": f"{row['buy_currency']} {row['buy_amount']:,.0f}",
                    "Sell Amount": f"{row['sell_currency']} {row['sell_amount']:,.0f}",
                    "Forward Rate": f"{row['forward_rate']:.6f}",
                    "Value Date": row["value_date"],
                }
            st.dataframe(
                pd.DataFrame(details.items(), columns=["Field", "Value"]),
                use_container_width=True,
                hide_index=True,
            )


# ==============
# Book Trade
# ==============

elif page == "Book Trade":

    page_header("Book Trade","Capture a new transaction using product-specific economics.")
    product=st.selectbox("Product",["Bond","IRS","FX Forward"],help="The form changes because each product has different economics.")
    cps=[c["name"] for c in list_counterparties()]


    # Do not rely on widget min/max bounds for control: manually typed out-of-range
    # values can otherwise be replaced by Streamlit's last valid server value.
    c1,c2,c3=st.columns(3)
    trade_date=c1.date_input("Trade date",date.today(),key="book_trade_date",help="Trade date cannot be in the future.")
    c2.text_input("Trader",current_name,disabled=True); trader=current_name
    counterparty=c3.selectbox("Counterparty",cps)
    c1,c2=st.columns(2)
    broker=c1.text_input("Broker","Demo Broker")
    comments=c2.text_input("Comments","Manual demo trade")


    visual_errors={}
    if trade_date > date.today(): visual_errors["book_trade_date"]="Trade date cannot be in the future."


    if product=="Bond":
        st.markdown("#### Bond economics")
        c1,c2,c3=st.columns(3)
        instrument=c1.text_input("Description","OAT Demo 3.00% 2031")
        isin=c2.text_input("ISIN","FR00000DEM01",key="bond_isin")
        side=c3.selectbox("Side",["BUY","SELL"])
        c1,c2,c3=st.columns(3)
        face=c1.number_input("Face amount",value=5_000_000.00,step=100_000.00,format="%.2f",key="bond_face")
        price=c2.number_input("Clean price",value=99.42,step=0.01,format="%.2f",key="bond_price")
        ccy=c3.selectbox("Currency",["EUR","USD","GBP"])
        c1,c2=st.columns(2)
        settlement=c2.date_input("Settlement date",max(trade_date,date.today()+timedelta(days=2)),key="bond_settlement",help="Settlement date cannot be before trade date.")
        maturity=c1.date_input("Maturity date",max(settlement+timedelta(days=1),date.today()+timedelta(days=365*5)),key="bond_maturity",help="Maturity date must be after settlement date.")
        if len(isin.strip()) != 12 or not isin.strip()[:2].isalpha(): visual_errors["bond_isin"]="ISIN must contain exactly 12 characters and start with 2 letters."
        if float(face) <= 0: visual_errors["bond_face"]="Face amount must be greater than zero."
        if float(price) <= 0: visual_errors["bond_price"]="Clean price must be greater than zero."
        if settlement < trade_date: visual_errors["bond_settlement"]="Settlement date cannot be before the trade date."
        if maturity <= settlement: visual_errors["bond_maturity"]="Maturity date must be after the settlement date."
        payload=dict(product=product,desk="Credit",instrument=instrument,isin=isin,side=side,face_amount=round(float(face),2),clean_price=round(float(price),2),currency=ccy,maturity_date=maturity,settlement_date=settlement)
    elif product=="IRS":
        st.markdown("#### IRS economics")
        c1,c2,c3=st.columns(3)
        instrument=c1.text_input("Description","EUR IRS 5Y")
        direction=c2.selectbox("Direction",["PAY_FIXED","RECEIVE_FIXED"])
        ccy=c3.selectbox("Currency",["EUR","USD","GBP"])
        c1,c2,c3=st.columns(3)
        notional=c1.number_input("Notional",value=25_000_000.00,step=1_000_000.00,format="%.2f",key="irs_notional")
        rate=c2.number_input("Fixed rate (%)",value=2.847,step=0.001,format="%.4f",key="irs_rate")
        index=c3.selectbox("Floating index",["EURIBOR 6M","SOFR","SONIA"])
        c1,c2=st.columns(2)
        effective=c1.date_input("Effective date",max(trade_date,date.today()+timedelta(days=2)),key="irs_effective",help="Effective date cannot be before trade date.")
        maturity=c2.date_input("Maturity date",max(effective+timedelta(days=1),date.today()+timedelta(days=365*5)),key="irs_maturity",help="Maturity date must be after effective date.")
        if float(notional) <= 0: visual_errors["irs_notional"]="Notional must be greater than zero."
        if float(rate) < 0: visual_errors["irs_rate"]="Fixed rate cannot be negative."
        if effective < trade_date: visual_errors["irs_effective"]="Effective date cannot be before the trade date."
        if maturity <= effective: visual_errors["irs_maturity"]="Maturity date must be after the effective date."
        payload=dict(product=product,desk="Rates",instrument=instrument,direction=direction,notional=round(float(notional),2),currency=ccy,fixed_rate=float(rate),floating_index=index,effective_date=effective,maturity_date=maturity)
    else:
        st.markdown("#### FX Forward economics")
        c1,c2,c3=st.columns(3)
        pair=c1.selectbox("Currency pair",["EUR/USD","GBP/USD","EUR/GBP","USD/JPY"])
        buy_ccy=c2.selectbox("Buy currency",pair.split("/"))
        sell_choices=[c for c in pair.split("/") if c != buy_ccy]
        sell_ccy=c3.selectbox("Sell currency",sell_choices)
        c1,c2,c3=st.columns(3)
        buy_amt=c1.number_input("Buy amount",value=5_000_000.00,step=100_000.00,format="%.2f",key="fx_buy")
        rate=c2.number_input("Forward rate",value=1.1285,step=0.0001,format="%.6f",key="fx_rate")
        sell_amt=c3.number_input("Sell amount",value=5_642_500.00,step=100_000.00,format="%.2f",key="fx_sell")
        value_date=st.date_input("Value date",max(trade_date+timedelta(days=1),date.today()+timedelta(days=90)),key="fx_value_date",help="Value date must be after trade date.")
        if float(buy_amt) <= 0: visual_errors["fx_buy"]="Buy amount must be greater than zero."
        if float(sell_amt) <= 0: visual_errors["fx_sell"]="Sell amount must be greater than zero."
        if float(rate) <= 0: visual_errors["fx_rate"]="Forward rate must be greater than zero."
        if value_date <= trade_date: visual_errors["fx_value_date"]="Value date must be after the trade date."
        instrument=pair+" 3M"
        payload=dict(product=product,desk="FX",instrument=instrument,currency_pair=pair,buy_currency=buy_ccy,buy_amount=round(float(buy_amt),2),sell_currency=sell_ccy,sell_amount=round(float(sell_amt),2),forward_rate=float(rate),value_date=value_date)


    # Unified inline validation: the invalid control itself turns red and gets a
    # small ! bubble. Hovering the bubble displays the field-specific reason.
    # This is intentionally separate from the blocking service validation below.
    import html as _html
    for field_key, msg in visual_errors.items():
        tooltip = _html.escape(msg, quote=True).replace("'", "'")
        css = f"""
        <style>
        .st-key-{field_key} {{ position: relative !important; }}
        .st-key-{field_key} [data-baseweb="input"],
        .st-key-{field_key} [data-testid="stDateInput"] [data-baseweb="input"],
        .st-key-{field_key} [data-testid="stDateInput"] > div > div {{
            border-color:#F04438 !important;
            background:#FFF1F0 !important;
            box-shadow:0 0 0 1px #F04438 inset !important;
        }}
        .st-key-{field_key} input {{
            color:#D92D20 !important;
            background:#FFF1F0 !important;
        }}
        .st-key-{field_key}::after {{
            content:"!";
            position:absolute;
            right:2.75rem;
            bottom:0.86rem;
            width:17px;height:17px;
            display:flex;align-items:center;justify-content:center;
            border:2px solid #F04438;border-radius:50%;
            color:#D92D20;background:#FFF1F0;
            font-size:11px;font-weight:800;line-height:1;
            z-index:20;cursor:help;pointer-events:auto;
        }}
        .st-key-{field_key}::before {{
            content:'{tooltip}';
            position:absolute;
            right:0;bottom:3.05rem;
            max-width:330px;
            padding:.42rem .58rem;
            border-radius:6px;
            background:#344054;color:white;
            font-size:.76rem;line-height:1.25;
            box-shadow:0 2px 8px rgba(16,24,40,.18);
            opacity:0;visibility:hidden;transform:translateY(3px);
            transition:opacity .12s ease, transform .12s ease;
            z-index:50;pointer-events:none;
        }}
        .st-key-{field_key}:hover::before {{
            opacity:1;visibility:visible;transform:translateY(0);
        }}
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)


    if st.button("Book Trade",type="primary",use_container_width=True):
        payload.update(trade_date=trade_date,trader=trader,counterparty=counterparty,broker=broker,comments=comments)
        errors=validate_trade_errors(payload)
        if errors:
            items="".join(f"<li style='margin:.28rem 0'>{msg}</li>" for msg in errors)
            st.markdown(f"<div style='background:#FEECEB;border:1px solid #FDA29B;border-radius:10px;padding:1rem 1.15rem;color:#B42318'><b>Trade cannot be booked. Please correct the following:</b><ul style='margin:.65rem 0 0 1.2rem;padding:0'>{items}</ul></div>",unsafe_allow_html=True)
        else:
            try:
                new_id=book_trade(payload, actor=current_name)
                st.success(f"✓ Trade {new_id} booked successfully.")
            except ValueError as e:
                items="".join(f"<li style='margin:.28rem 0'>{msg}</li>" for msg in str(e).splitlines() if msg.strip())
                st.markdown(f"<div style='background:#FEECEB;border:1px solid #FDA29B;border-radius:10px;padding:1rem 1.15rem;color:#B42318'><b>Trade cannot be booked. Please correct the following:</b><ul style='margin:.65rem 0 0 1.2rem;padding:0'>{items}</ul></div>",unsafe_allow_html=True)
            except Exception:
                st.error("The trade could not be booked because of an unexpected application error.")

# =================
# Confirmations
# =================

elif page == "Confirmations":

    page_header("Confirmations","Search the confirmation queue, review trade recaps and complete the matching workflow.")
    if df.empty:
        st.info("Book a trade first.")
    else:
        # Traders can monitor confirmations but processing actions are reserved for Operations/Supervisors.
        can_process=current_role in {"OPERATIONS","SUPERVISOR"}
        if not can_process:
            st.info("Read-only access · Confirmation processing is managed by Operations. Your trades are pre-filtered by default.")


        work=df.copy()
        work["control_status"]=work.apply(control_status,axis=1)
        work["currency"]=work.apply(currency_for,axis=1)


        search=st.text_input("Search",placeholder="Trade ID or instrument...")
        f1,f2,f3,f4,f5=st.columns(5)
        products=f1.multiselect("Product",sorted(work["product"].dropna().unique()))
        counterparties=f2.multiselect("Counterparty",sorted(work["counterparty"].dropna().unique()))
        trader_options=sorted(work["trader"].dropna().unique())
        default_traders=[current_name] if current_role=="TRADER" and current_name in trader_options else []
        traders_filter=f3.multiselect("Trader",trader_options,default=default_traders)
        statuses=f4.multiselect("Workflow Status",sorted(work["confirmation_status"].dropna().unique()))
        controls=f5.multiselect("Control Status",["OK","EXCEPTION"])


        filtered=work.copy()
        if search:
            mask=(filtered["trade_id"].astype(str).str.contains(search,case=False,na=False) |
                  filtered["instrument"].astype(str).str.contains(search,case=False,na=False))
            filtered=filtered[mask]
        if products: filtered=filtered[filtered["product"].isin(products)]
        if counterparties: filtered=filtered[filtered["counterparty"].isin(counterparties)]
        if traders_filter: filtered=filtered[filtered["trader"].isin(traders_filter)]
        if statuses: filtered=filtered[filtered["confirmation_status"].isin(statuses)]
        if controls: filtered=filtered[filtered["control_status"].isin(controls)]


        st.caption(f"{len(filtered)} trade(s) found")
        if filtered.empty:
            st.warning("No trade matches the selected filters.")
        else:
            labels={
                r["trade_id"]:f"{r['trade_id']} | {r['product']} | {r['instrument']} | {r['counterparty']} | {r['confirmation_status'].replace('_',' ')}"
                for _,r in filtered.iterrows()
            }
            trade_id=st.selectbox("Trade",filtered["trade_id"].tolist(),format_func=lambda tid:labels[tid])
            row=filtered[filtered["trade_id"]==trade_id].iloc[0]
            status=row.confirmation_status
            exception=is_exception(row)


            st.markdown(f"### {row['instrument']}")
            st.markdown(
                f"{display_side(row)} · {trade_economics(row)} · {row['counterparty']}    "
                f"{status_badge(status)}   {status_badge(status,True) if exception else ''}",
                unsafe_allow_html=True,
            )


            # Timeline colours describe progress: green = completed, blue = next action, grey = future.
            steps=["BOOKED","GENERATED","SENT","MATCHED"]
            completed_count={"NOT_GENERATED":1,"GENERATED":2,"SENT":3,"SENT_DEMO":3,"MATCHED":4}.get(status,1)
            html="<div class='timeline'>"
            for i,step in enumerate(steps):
                if i < completed_count:
                    cls="done"; marker="●"
                elif i == completed_count and completed_count < len(steps):
                    cls="next"; marker="●"
                else:
                    cls=""; marker="○"
                html+=f"<div class='step {cls}'>{marker} {step}</div>"
                if i<3: html+="<div class='connector'>→</div>"
            html+="</div>"
            st.markdown(html,unsafe_allow_html=True)


            events=audit_for(trade_id)
            event_map={}
            for _,event in events.iterrows():
                event_map.setdefault(event.event_type,event.event_time)
            booked_at=event_map.get("TRADE_BOOKED",f"{row['trade_date']} {row['trade_time']}")
            generated_at=event_map.get("CONFIRMATION_GENERATED","Pending")
            sent_at=event_map.get("EMAIL_SENT_DEMO",event_map.get("EMAIL_SENT","Pending"))
            matched_at=event_map.get("TRADE_MATCHED","Pending")
            t1,t2,t3,t4=st.columns(4)
            t1.caption(f"Booked\n{booked_at}")
            t2.caption(f"Generated\n{generated_at}")
            t3.caption(f"Sent\n{sent_at}")
            t4.caption(f"Matched\n{matched_at}")


            if status in ["SENT","SENT_DEMO","MATCHED"] and sent_at!="Pending":
                cp=get_counterparty(row["counterparty"])
                recipient=cp.get("confirmation_email","—") if cp else "—"
                delivery_channel="EMAIL — DEMO" if status=="SENT_DEMO" or "EMAIL_SENT_DEMO" in event_map else "EMAIL"
                delivery_status="Matched" if status=="MATCHED" else "Awaiting counterparty match"
                st.success("✓ Confirmation delivery simulated successfully" if delivery_channel.endswith("DEMO") else "✓ Confirmation sent successfully")
                # Delivery receipt is descriptive information, not a KPI: keep it compact and fully readable.
                st.markdown(
                    f"""<div style='border:1px solid #DCE3EC;border-radius:12px;background:#FFFFFF;padding:.9rem 1rem;margin:.25rem 0 1rem'>
                    <div style='display:grid;grid-template-columns:140px 1fr;gap:.42rem .9rem;font-size:.94rem'>
                      <div style='color:#667085'>Recipient</div><div style='font-weight:600;color:#202939'>{recipient}</div>
                      <div style='color:#667085'>Sent at</div><div style='font-weight:600;color:#202939'>{sent_at}</div>
                      <div style='color:#667085'>Channel</div><div style='font-weight:600;color:#202939'>{delivery_channel}</div>
                      <div style='color:#667085'>Status</div><div style='font-weight:600;color:#202939'>{delivery_status}</div>
                    </div></div>""",
                    unsafe_allow_html=True,
                )


            if status in ["SENT","SENT_DEMO"]:
                waiting_for=elapsed_since(sent_at)
                if exception:
                    st.error(f"OVERDUE — Awaiting counterparty match · Sent {waiting_for or 'over 1 day'} ago")
                else:
                    st.info(f"Awaiting counterparty match · {'Sent just now' if waiting_for == 'just now' else 'Sent ' + (waiting_for or 'recently') + ' ago'}")
            elif exception:
                st.error(f"CONTROL EXCEPTION · Trade is {age_days(row)} day(s) old and remains {status.replace('_',' ')}.")


            expected=Path(__file__).resolve().parent/"data"/"generated"/f"{trade_id}_trade_recap.pdf"


            # Generated recaps remain downloadable throughout the rest of the workflow.
            # On ephemeral/demo deployments the generated file may disappear after a restart,
            # so rebuild the same recap from the immutable trade data without changing status
            # or writing a second CONFIRMATION_GENERATED audit event.
            pdf_restore_error=None
            if status!="NOT_GENERATED" and not expected.exists():
                try:
                    render_trade_recap(
                        trade_id,
                        generated_at=None if generated_at=="Pending" else str(generated_at),
                    )
                except Exception as e:
                    pdf_restore_error=str(e)
            pdf_exists=expected.exists()


            if can_process:
                c1,c2,c3=st.columns(3)
                generate_label="✓ Trade recap generated" if status!="NOT_GENERATED" else "1 · Generate trade recap"
                if c1.button(generate_label,disabled=status!="NOT_GENERATED",use_container_width=True):
                    try:
                        generate_confirmation(trade_id,actor=current_name)
                        st.success("Trade recap generated. The next step is to send the confirmation.")
                        st.rerun()
                    except Exception as e: st.error(str(e))


                send_done=status in ["SENT","SENT_DEMO","MATCHED"]
                send_label="✓ Confirmation sent" if send_done else "2 · Send confirmation"
                send_disabled=status!="GENERATED" or not pdf_exists
                if c2.button(send_label,type="primary" if not send_disabled else "secondary",disabled=send_disabled,use_container_width=True):
                    try:
                        send_confirmation(trade_id,expected,actor=current_name)
                        st.rerun()
                    except Exception as e: st.error(str(e))


                matched_done=status=="MATCHED"
                match_label="✓ Matched" if matched_done else "3 · Mark matched"
                if c3.button(match_label,disabled=status not in ["SENT","SENT_DEMO"],use_container_width=True):
                    try:
                        mark_matched(trade_id,actor=current_name)
                        st.success("Trade marked MATCHED.")
                        st.rerun()
                    except Exception as e: st.error(str(e))


            if pdf_exists:
                with open(expected,"rb") as f:
                    st.download_button("Download PDF",f,file_name=f"{trade_id}_trade_recap.pdf",mime="application/pdf",use_container_width=True)
            elif status!="NOT_GENERATED":
                st.warning(f"The trade recap could not be restored for download: {pdf_restore_error or 'unknown error'}")


            st.caption("Confirmation workflow: Generate recap → Send confirmation → Match trade")


# ===============
# Audit Trail
# ===============

elif page == "Audit Trail":

    page_header("Audit Trail","Chronological record of booking, confirmation, delivery and matching events.")
    with connect() as con:
        events=pd.read_sql_query("""SELECT a.*, COALESCE(u.role,'SYSTEM') AS actor_role
            FROM audit_events a LEFT JOIN users u ON a.actor=u.full_name
            ORDER BY a.event_time DESC, a.id DESC""",con)
    if events.empty:
        st.info("No audit events recorded.")
    else:
        events["event_date"]=pd.to_datetime(events["event_time"]).dt.date
        min_event_date=events["event_date"].min(); max_event_date=events["event_date"].max()
        c1,c2,c3,c4=st.columns(4)
        types=c1.multiselect("Action",sorted(events.event_type.unique()))
        actors=c2.multiselect("User",sorted(events.actor.unique()))
        roles=c3.multiselect("Role",sorted(events.actor_role.unique()))
        tid=c4.text_input("Trade ID contains")
        selected_dates=st.date_input("Date range",value=(min_event_date,max_event_date),min_value=min_event_date,max_value=max_event_date)
        if types: events=events[events.event_type.isin(types)]
        if actors: events=events[events.actor.isin(actors)]
        if roles: events=events[events.actor_role.isin(roles)]
        if tid: events=events[events.trade_id.astype(str).str.contains(tid,case=False,na=False)]
        if isinstance(selected_dates,(tuple,list)) and len(selected_dates)==2:
            events=events[(events.event_date>=selected_dates[0]) & (events.event_date<=selected_dates[1])]


        display=events[["event_time","actor","actor_role","event_type","trade_id","details"]].copy()
        display["event_time"]=pd.to_datetime(display["event_time"]).dt.strftime("%d/%m/%Y %H:%M:%S")
        display["event_type"]=display["event_type"].str.replace("_"," ",regex=False).str.title()
        display["actor_role"]=display["actor_role"].str.replace("_"," ",regex=False).str.title()
        display=display.rename(columns={"event_time":"Timestamp","actor":"User","actor_role":"Role","event_type":"Action","trade_id":"Trade ID","details":"Details"})
        st.caption(f"{len(display)} event{'s' if len(display)!=1 else ''} shown")
        st.dataframe(display,use_container_width=True,hide_index=True)
