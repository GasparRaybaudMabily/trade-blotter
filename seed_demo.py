"""
Trade Blotter - Demo data seeder

Creates a fresh synthetic dataset for demonstration purposes.
It populates the SQLite database with demo users, counterparties,
trades and coherent post-trade workflow histories.
"""

from datetime import date, datetime, timedelta
import random
from core.database import reset_db
from services.trade_service import book_trade, set_seed_status
from services.audit_service import log_event
from services.confirmation_service import render_trade_recap

RNG=random.Random(42)
TODAY=date.today()-timedelta(days=1)  # Seeded trades are historical before the app session starts.
COUNTERPARTIES=["Atlas Bank Demo","Meridian Markets Demo","Northstar Securities Demo","Helios Capital Demo","Orion Bank Demo"]
TRADERS=["Alex Martin","Emma Laurent","Lucas Bernard","Sofia Moreau"]
OPERATIONS=["Sophie Bernard","Lucas Robert","Camille Moreau","Thomas Leroy"]
BROKERS=["Demo Broker Europe","Demo Broker Markets"]
BONDS=[
    ("FR00000DEM01","OAT Demo 3.00% 2031","EUR",date(2031,5,25),99.40),
    ("DE00000DEM02","Bund Demo 2.60% 2033","EUR",date(2033,8,15),101.20),
    ("GB00000DEM03","UK Gilt Demo 4.00% 2032","GBP",date(2032,10,22),98.75),
    ("US00000DEM04","US Treasury Demo 3.75% 2030","USD",date(2030,11,15),100.10),
]
IRS=[("EUR IRS 2Y","EUR","EURIBOR 6M",2),("EUR IRS 5Y","EUR","EURIBOR 6M",5),("USD IRS 5Y","USD","SOFR",5),("GBP IRS 10Y","GBP","SONIA",10)]
FX=[("EUR/USD","EUR","USD",1.1285),("GBP/USD","GBP","USD",1.3450),("EUR/GBP","EUR","GBP",0.8390),("USD/JPY","USD","JPY",149.50)]

def random_trade_date(): return TODAY-timedelta(days=RNG.randint(0,29))
def common(product,instrument,trade_date,desk):
    hh=RNG.randint(7,16); mm=RNG.randint(0,59); ss=RNG.randint(0,59)
    return dict(trade_date=trade_date,trade_time=f"{hh:02d}:{mm:02d}:{ss:02d}",created_at=f"{trade_date} {hh:02d}:{mm:02d}:{ss:02d}",
        trader=RNG.choice(TRADERS),desk=desk,product=product,instrument=instrument,counterparty=RNG.choice(COUNTERPARTIES),
        broker=RNG.choice(BROKERS),comments="Synthetic demo trade")

def _event_time(base: datetime, minutes: int):
    return (base + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")

def seed():
    reset_db(); ids=[]
    for _ in range(100):
        p=RNG.choices(["Bond","IRS","FX Forward"],weights=[40,35,25])[0]; td=random_trade_date()
        if p=="Bond":
            isin,instr,ccy,mat,base=RNG.choice(BONDS); d=common(p,instr,td,"Credit")
            d.update(isin=isin,side=RNG.choice(["BUY","SELL"]),face_amount=RNG.choice([500_000,1_000_000,2_000_000,5_000_000,10_000_000,25_000_000,50_000_000,100_000_000]),
                     clean_price=round(base+RNG.uniform(-2,2),3),currency=ccy,maturity_date=mat,settlement_date=td+timedelta(days=2))
        elif p=="IRS":
            instr,ccy,index,years=RNG.choice(IRS); d=common(p,instr,td,"Rates")
            d.update(direction=RNG.choice(["PAY_FIXED","RECEIVE_FIXED"]),notional=RNG.choice([5_000_000,10_000_000,25_000_000,50_000_000,100_000_000,250_000_000,500_000_000]),
                     currency=ccy,fixed_rate=round(RNG.uniform(2.0,5.0),4),floating_index=index,effective_date=td+timedelta(days=2),
                     maturity_date=td.replace(year=td.year+years))
        else:
            pair,buy,sell,rate=RNG.choice(FX)
            if RNG.random()<0.5: buy,sell=sell,buy; rate=1/rate
            d=common(p,pair+" 3M",td,"FX"); buy_amt=RNG.choice([200_000,500_000,1_000_000,2_000_000,5_000_000,10_000_000,25_000_000,50_000_000,100_000_000]); sell_amt=buy_amt*rate
            d.update(currency_pair=pair,buy_currency=buy,buy_amount=buy_amt,sell_currency=sell,sell_amount=round(sell_amt,2),
                     forward_rate=round(rate,6),value_date=td+timedelta(days=90))
        tid=book_trade(d,actor=d["trader"]); ids.append(tid)
        status=RNG.choices(["NOT_GENERATED","GENERATED","SENT_DEMO","MATCHED"],weights=[25,20,30,25])[0]
        set_seed_status(tid,status,"CONFIRMED" if status=="MATCHED" else "BOOKED")
        base_dt=datetime.fromisoformat(d["created_at"])
        # book_trade already wrote TRADE_BOOKED at runtime; replace that seed event with a realistic timestamp.
        from core.database import connect
        with connect() as con:
            con.execute("UPDATE audit_events SET event_time=? WHERE trade_id=? AND event_type='TRADE_BOOKED'", (_event_time(base_dt,0),tid))
        ops_actor=RNG.choice(OPERATIONS)
        gen_min=RNG.randint(5,45); sent_min=gen_min+RNG.randint(3,30); match_min=sent_min+RNG.randint(15,360)
        if status in {"GENERATED","SENT_DEMO","MATCHED"}:
            generated_at=_event_time(base_dt,gen_min)
            log_event(tid,"CONFIRMATION_GENERATED",ops_actor,"Synthetic seeded workflow event",generated_at)
            render_trade_recap(tid,generated_at)
        if status in {"SENT_DEMO","MATCHED"}: log_event(tid,"EMAIL_SENT_DEMO",ops_actor,"Synthetic seeded workflow event",_event_time(base_dt,sent_min))
        if status=="MATCHED": log_event(tid,"TRADE_MATCHED",ops_actor,"Synthetic seeded workflow event",_event_time(base_dt,match_min))
    print(f"Demo database created with {len(ids)} synthetic trades (random seed = 42).")

if __name__=="__main__": seed()
