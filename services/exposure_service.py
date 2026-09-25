"""
Trade Blotter - Position service

Builds the product-specific position views displayed on the dashboard.
Bond, IRS and FX Forward positions are calculated using conventions
appropriate to each product rather than a single generic exposure measure.
"""

import pandas as pd
from services.trade_service import list_trades

def exposure_tables():
    df=pd.DataFrame(list_trades())
    if df.empty:
        return {"bond":pd.DataFrame(),"irs":pd.DataFrame(),"fx":pd.DataFrame()}

    bonds=df[df["product"]=="Bond"].copy()
    if not bonds.empty:
        bonds["signed_face"] = bonds.apply(lambda r: r["face_amount"] if r["side"]=="BUY" else -r["face_amount"], axis=1)
        bond_exp=bonds.groupby("bond_currency",as_index=False)["signed_face"].sum().rename(columns={"bond_currency":"currency","signed_face":"net_face_amount"})
    else: bond_exp=pd.DataFrame()

    irs=df[df["product"]=="IRS"].copy()
    if not irs.empty:
        irs["signed_notional"] = irs.apply(lambda r: r["notional"] if r["direction"]=="RECEIVE_FIXED" else -r["notional"], axis=1)
        irs_exp=irs.groupby("irs_currency",as_index=False)["signed_notional"].sum().rename(columns={"irs_currency":"currency","signed_notional":"net_fixed_notional"})
    else: irs_exp=pd.DataFrame()

    fx=df[df["product"]=="FX Forward"].copy()
    rows=[]
    for _,r in fx.iterrows():
        rows += [(r["buy_currency"],r["buy_amount"]),(r["sell_currency"],-r["sell_amount"])]
    fx_exp=pd.DataFrame(rows,columns=["currency","net_amount"]).groupby("currency",as_index=False)["net_amount"].sum() if rows else pd.DataFrame()
    return {"bond":bond_exp,"irs":irs_exp,"fx":fx_exp}
