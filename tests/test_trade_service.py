"""
Automated tests for the Trade Blotter business rules.

These tests verify that invalid trades are rejected and that
the core booking and workflow controls behave as expected.
"""

import pytest
from services.trade_service import validate_trade

def test_bond_face_amount_must_be_positive():
    d=dict(trader="T",desk="Credit",product="Bond",instrument="X",counterparty="CP",broker="B",isin="DEMO",side="BUY",face_amount=0,clean_price=100,currency="EUR",maturity_date="2030-01-01",settlement_date="2026-01-01")
    with pytest.raises(ValueError): validate_trade(d)

def test_irs_direction_is_validated():
    d=dict(trader="T",desk="Rates",product="IRS",instrument="X",counterparty="CP",broker="B",direction="BUY",notional=1_000_000,currency="EUR",fixed_rate=3.0,floating_index="EURIBOR 6M",effective_date="2026-01-01",maturity_date="2031-01-01")
    with pytest.raises(ValueError): validate_trade(d)

def test_bond_maturity_must_follow_settlement():
    d=dict(trader="T",desk="Credit",product="Bond",instrument="X",counterparty="CP",broker="B",trade_date="2026-09-25",isin="DEMO",side="BUY",face_amount=1_000_000,clean_price=100,currency="EUR",maturity_date="2026-09-26",settlement_date="2026-09-28")
    with pytest.raises(ValueError, match="maturity"):
        validate_trade(d)


def test_irs_maturity_must_follow_effective_date():
    d=dict(trader="T",desk="Rates",product="IRS",instrument="X",counterparty="CP",broker="B",trade_date="2026-09-25",direction="PAY_FIXED",notional=1_000_000,currency="EUR",fixed_rate=3.0,floating_index="EURIBOR 6M",effective_date="2026-09-28",maturity_date="2026-09-27")
    with pytest.raises(ValueError, match="maturity"):
        validate_trade(d)


def test_fx_currencies_must_match_pair():
    d=dict(trader="T",desk="FX",product="FX Forward",instrument="X",counterparty="CP",broker="B",trade_date="2026-09-25",currency_pair="EUR/USD",buy_currency="EUR",buy_amount=1_000_000,sell_currency="GBP",sell_amount=900_000,forward_rate=1.1,value_date="2026-12-25")
    with pytest.raises(ValueError, match="currency pair"):
        validate_trade(d)

def test_future_trade_date_is_rejected():
    d=dict(trader="T",desk="Credit",product="Bond",instrument="X",counterparty="CP",broker="B",trade_date="2099-01-01",isin="DEMO",side="BUY",face_amount=1_000_000,clean_price=100,currency="EUR",maturity_date="2100-01-01",settlement_date="2099-01-03")
    with pytest.raises(ValueError, match="future"):
        validate_trade(d)

def test_bond_settlement_cannot_precede_trade_date():
    d=dict(trader="T",desk="Credit",product="Bond",instrument="X",counterparty="CP",broker="B",trade_date="2026-09-25",isin="DEMO",side="BUY",face_amount=1_000_000,clean_price=100,currency="EUR",maturity_date="2030-01-01",settlement_date="2026-09-24")
    with pytest.raises(ValueError, match="Settlement"):
        validate_trade(d)

def test_bond_clean_price_must_be_positive():
    d=dict(trader="T",desk="Credit",product="Bond",instrument="X",counterparty="CP",broker="B",trade_date="2026-09-25",isin="DEMO",side="BUY",face_amount=1_000_000,clean_price=-99.42,currency="EUR",maturity_date="2030-01-01",settlement_date="2026-09-27")
    with pytest.raises(ValueError, match="Clean price"):
        validate_trade(d)

def test_bond_isin_must_have_12_chars_and_two_letter_prefix():
    d=dict(trader="T",desk="Credit",product="Bond",instrument="X",counterparty="CP",broker="B",trade_date="2026-09-25",isin="F123",side="BUY",face_amount=1_000_000,clean_price=100,currency="EUR",maturity_date="2030-01-01",settlement_date="2026-09-27")
    with pytest.raises(ValueError, match="12 characters"):
        validate_trade(d)


def test_multiple_bond_errors_are_reported_together():
    d=dict(trader="T",desk="Credit",product="Bond",instrument="X",counterparty="CP",broker="B",trade_date="2099-09-25",isin="123",side="BUY",face_amount=-1,clean_price=-99,currency="EUR",maturity_date="2026-09-20",settlement_date="2026-09-21")
    with pytest.raises(ValueError) as exc:
        validate_trade(d)
    msg=str(exc.value)
    assert "future" in msg
    assert "ISIN" in msg
    assert "Face amount" in msg
    assert "Clean price" in msg
    assert "maturity" in msg


def test_valid_bond_passes_validation():
    d=dict(trader="T",desk="Credit",product="Bond",instrument="X",counterparty="CP",broker="B",trade_date="2026-09-25",isin="FR0000000001",side="BUY",face_amount=1_000_000,clean_price=99.42,currency="EUR",maturity_date="2030-01-01",settlement_date="2026-09-27")
    validate_trade(d)
