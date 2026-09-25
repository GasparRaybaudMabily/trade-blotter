"""
Trade Blotter - Trade service

Contains the business logic related to trade capture and lifecycle management.
It validates trade economics, books new transactions and provides
the trade data consumed by the application.
"""

from datetime import date, datetime
import secrets
from core.database import connect
from services.audit_service import log_event

PRODUCT_TABLES = {"Bond":"bond_details", "IRS":"irs_details", "FX Forward":"fx_forward_details"}

def new_trade_id() -> str:
    now = datetime.now()
    return f"TRD-{now:%Y%m%d}-{now:%H%M%S}-{secrets.token_hex(2).upper()}"

def _as_date(value, field_name):
    try:
        return value if isinstance(value, date) else datetime.strptime(str(value), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} must be a valid date.")


def validate_trade_errors(data: dict) -> list[str]:
    """Return every blocking validation error for a trade."""
    errors = []
    common = ["trader", "desk", "product", "instrument", "counterparty", "broker"]
    missing = [k for k in common if data.get(k) in (None, "")]
    if missing:
        errors.append("Missing required fields: " + ", ".join(missing) + ".")

    product = data.get("product")
    if product not in PRODUCT_TABLES:
        errors.append("Unsupported product.")
        return errors

    try:
        trade_date = _as_date(data.get("trade_date", date.today()), "Trade date")
        if trade_date > date.today():
            errors.append("Trade date cannot be in the future.")
    except ValueError as exc:
        errors.append(str(exc))
        trade_date = None

    if product == "Bond":
        req = ["isin", "side", "face_amount", "clean_price", "currency", "maturity_date", "settlement_date"]
        product_missing = [k for k in req if data.get(k) in (None, "")]
        if product_missing:
            errors.append("Missing required fields: " + ", ".join(product_missing) + ".")

        isin = str(data.get("isin", "")).strip().upper()
        if isin and (len(isin) != 12 or not isin[:2].isalpha()):
            errors.append("ISIN must contain exactly 12 characters and start with 2 letters.")
        if data.get("side") not in {"BUY", "SELL"}:
            errors.append("Bond side must be BUY or SELL.")
        try:
            if float(data.get("face_amount", 0)) <= 0:
                errors.append("Face amount must be greater than zero.")
        except (TypeError, ValueError):
            errors.append("Face amount must be a valid number.")
        try:
            if float(data.get("clean_price", 0)) <= 0:
                errors.append("Clean price must be greater than zero.")
        except (TypeError, ValueError):
            errors.append("Clean price must be a valid number.")

        settlement = maturity = None
        try:
            settlement = _as_date(data.get("settlement_date"), "Settlement date")
        except ValueError as exc:
            errors.append(str(exc))
        try:
            maturity = _as_date(data.get("maturity_date"), "Maturity date")
        except ValueError as exc:
            errors.append(str(exc))
        if trade_date and settlement and settlement < trade_date:
            errors.append("Settlement date cannot be before the trade date.")
        if settlement and maturity and maturity <= settlement:
            errors.append("Bond maturity must be after the settlement date.")

    elif product == "IRS":
        req = ["direction", "notional", "currency", "fixed_rate", "floating_index", "effective_date", "maturity_date"]
        product_missing = [k for k in req if data.get(k) in (None, "")]
        if product_missing:
            errors.append("Missing required fields: " + ", ".join(product_missing) + ".")
        if data.get("direction") not in {"PAY_FIXED", "RECEIVE_FIXED"}:
            errors.append("IRS direction must be PAY_FIXED or RECEIVE_FIXED.")
        try:
            if float(data.get("notional", 0)) <= 0:
                errors.append("Notional must be greater than zero.")
        except (TypeError, ValueError):
            errors.append("Notional must be a valid number.")
        try:
            if float(data.get("fixed_rate", -1)) < 0:
                errors.append("Fixed rate cannot be negative.")
        except (TypeError, ValueError):
            errors.append("Fixed rate must be a valid number.")
        effective = maturity = None
        try:
            effective = _as_date(data.get("effective_date"), "Effective date")
        except ValueError as exc:
            errors.append(str(exc))
        try:
            maturity = _as_date(data.get("maturity_date"), "Maturity date")
        except ValueError as exc:
            errors.append(str(exc))
        if trade_date and effective and effective < trade_date:
            errors.append("Effective date cannot be before the trade date.")
        if effective and maturity and maturity <= effective:
            errors.append("IRS maturity must be after the effective date.")

    else:
        req = ["currency_pair", "buy_currency", "buy_amount", "sell_currency", "sell_amount", "forward_rate", "value_date"]
        product_missing = [k for k in req if data.get(k) in (None, "")]
        if product_missing:
            errors.append("Missing required fields: " + ", ".join(product_missing) + ".")
        try:
            if float(data.get("buy_amount", 0)) <= 0:
                errors.append("Buy amount must be greater than zero.")
        except (TypeError, ValueError):
            errors.append("Buy amount must be a valid number.")
        try:
            if float(data.get("sell_amount", 0)) <= 0:
                errors.append("Sell amount must be greater than zero.")
        except (TypeError, ValueError):
            errors.append("Sell amount must be a valid number.")
        try:
            if float(data.get("forward_rate", 0)) <= 0:
                errors.append("Forward rate must be greater than zero.")
        except (TypeError, ValueError):
            errors.append("Forward rate must be a valid number.")
        if data.get("buy_currency") == data.get("sell_currency"):
            errors.append("Buy and sell currencies must be different.")
        pair_ccys = set(str(data.get("currency_pair", "")).split("/"))
        if pair_ccys != {data.get("buy_currency"), data.get("sell_currency")}:
            errors.append("Buy and sell currencies must match the selected currency pair.")
        try:
            value_date = _as_date(data.get("value_date"), "Value date")
            if trade_date and value_date <= trade_date:
                errors.append("FX forward value date must be after the trade date.")
        except ValueError as exc:
            errors.append(str(exc))

    # Preserve order while removing duplicates.
    return list(dict.fromkeys(errors))


def validate_trade(data: dict):
    errors = validate_trade_errors(data)
    if errors:
        raise ValueError("\n".join(errors))

def book_trade(data: dict, actor="USER") -> str:
    validate_trade(data)
    now = datetime.now()
    trade_id = data.get("trade_id") or new_trade_id()
    trade_date = str(data.get("trade_date", now.date()))
    trade_time = data.get("trade_time") or now.strftime("%H:%M:%S")
    created_at = data.get("created_at") or f"{trade_date} {trade_time}"
    with connect() as con:
        con.execute("""INSERT INTO trades
        (trade_id,trade_date,trade_time,trader,desk,product,instrument,counterparty,broker,status,confirmation_status,comments,created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            trade_id, trade_date, trade_time, data["trader"], data["desk"], data["product"], data["instrument"],
            data["counterparty"], data["broker"], "BOOKED", "NOT_GENERATED", data.get("comments",""), created_at))
        if data["product"] == "Bond":
            con.execute("""INSERT INTO bond_details VALUES (?,?,?,?,?,?,?,?)""", (
                trade_id,data["isin"],data["side"],round(float(data["face_amount"]),2),round(float(data["clean_price"]),2),
                data["currency"],str(data["maturity_date"]),str(data["settlement_date"])))
            summary=f'{data["side"]} {float(data["face_amount"]):,.0f} {data["currency"]} {data["instrument"]}'
        elif data["product"] == "IRS":
            con.execute("""INSERT INTO irs_details VALUES (?,?,?,?,?,?,?,?)""", (
                trade_id,data["direction"],round(float(data["notional"]),2),data["currency"],float(data["fixed_rate"]),
                data["floating_index"],str(data["effective_date"]),str(data["maturity_date"])))
            summary=f'{data["direction"]} {float(data["notional"]):,.0f} {data["currency"]} {data["instrument"]}'
        else:
            con.execute("""INSERT INTO fx_forward_details VALUES (?,?,?,?,?,?,?,?)""", (
                trade_id,data["currency_pair"],data["buy_currency"],round(float(data["buy_amount"]),2),data["sell_currency"],
                round(float(data["sell_amount"]),2),float(data["forward_rate"]),str(data["value_date"])))
            summary=f'BUY {float(data["buy_amount"]):,.0f} {data["buy_currency"]} / SELL {data["sell_currency"]}'
    log_event(trade_id, "TRADE_BOOKED", actor, summary)
    return trade_id

def list_trades():
    sql="""SELECT t.*,
      b.isin,b.side,b.face_amount,b.clean_price,b.currency AS bond_currency,b.maturity_date AS bond_maturity,b.settlement_date,
      i.direction,i.notional,i.currency AS irs_currency,i.fixed_rate,i.floating_index,i.effective_date,i.maturity_date AS irs_maturity,
      f.currency_pair,f.buy_currency,f.buy_amount,f.sell_currency,f.sell_amount,f.forward_rate,f.value_date
    FROM trades t
    LEFT JOIN bond_details b ON t.trade_id=b.trade_id
    LEFT JOIN irs_details i ON t.trade_id=i.trade_id
    LEFT JOIN fx_forward_details f ON t.trade_id=f.trade_id
    ORDER BY t.created_at DESC"""
    with connect() as con:
        return [dict(r) for r in con.execute(sql).fetchall()]

def get_trade(trade_id):
    rows=[r for r in list_trades() if r["trade_id"]==trade_id]
    return rows[0] if rows else None

def update_confirmation_status(trade_id, status):
    with connect() as con:
        con.execute("UPDATE trades SET confirmation_status=? WHERE trade_id=?", (status,trade_id))

def set_seed_status(trade_id, confirmation_status, status="BOOKED"):
    with connect() as con:
        con.execute("UPDATE trades SET confirmation_status=?, status=? WHERE trade_id=?", (confirmation_status,status,trade_id))

def mark_matched(trade_id, actor="USER"):
    trade=get_trade(trade_id)
    if not trade: raise ValueError("Trade not found.")
    if trade["confirmation_status"] not in {"SENT","SENT_DEMO"}:
        raise ValueError("The confirmation must be sent before the trade can be marked MATCHED.")
    with connect() as con:
        con.execute("UPDATE trades SET confirmation_status='MATCHED', status='CONFIRMED' WHERE trade_id=?", (trade_id,))
    log_event(trade_id, "TRADE_MATCHED", actor, "Trade economics marked as matched")
