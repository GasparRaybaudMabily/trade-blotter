"""
Trade Blotter - Data models

Defines the core trade structures used by the application.
Each supported product has its own economics while sharing
a common set of trade and workflow information.
"""

from dataclasses import dataclass

@dataclass(frozen=True)
class Trade:
    trade_id: str
    trade_date: str
    trade_time: str
    trader: str
    desk: str
    product: str
    instrument: str
    counterparty: str
    broker: str
    status: str = "BOOKED"
    confirmation_status: str = "NOT_GENERATED"
    comments: str = ""

@dataclass(frozen=True)
class BondDetails:
    isin: str
    side: str
    face_amount: float
    clean_price: float
    currency: str
    maturity_date: str
    settlement_date: str

@dataclass(frozen=True)
class IRSDetails:
    direction: str
    notional: float
    currency: str
    fixed_rate: float
    floating_index: str
    effective_date: str
    maturity_date: str

@dataclass(frozen=True)
class FXForwardDetails:
    currency_pair: str
    buy_currency: str
    buy_amount: float
    sell_currency: str
    sell_amount: float
    forward_rate: float
    value_date: str
