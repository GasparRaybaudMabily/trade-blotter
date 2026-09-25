# Architecture — V4.1

Streamlit is the UI layer. Service modules contain business logic. SQLite persists the data.

## Relational trade model

`trades` stores fields common to every trade. Product economics live in one specialised table linked by `trade_id`:

- `bond_details`
- `irs_details`
- `fx_forward_details`

`counterparties` stores reference data and `audit_events` stores the immutable-style activity history.

## Workflow

`NOT_GENERATED -> GENERATED -> SENT/SENT_DEMO -> MATCHED`

The UI and service layer prevent matching before a confirmation has been sent.

## Exposure conventions (demo)

- Bonds: BUY positive / SELL negative face amount, grouped by currency.
- IRS: RECEIVE_FIXED positive / PAY_FIXED negative notional, grouped by currency.
- FX forwards: bought currency positive / sold currency negative.

These are monitoring aggregates for a portfolio demonstration, not valuation or risk measures (no DV01/PV01, duration, FX conversion, market value, or P&L).
