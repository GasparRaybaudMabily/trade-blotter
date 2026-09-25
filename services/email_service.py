"""
Trade Blotter - Email service

Simulates the delivery of trade confirmations to counterparties.
No real emails are sent: delivery events are recorded only
to demonstrate the post-trade workflow.
"""

import os, smtplib
from email.message import EmailMessage
from pathlib import Path
from dotenv import load_dotenv
from services.counterparty_service import get_counterparty
from services.trade_service import get_trade, update_confirmation_status
from services.audit_service import log_event

load_dotenv()

def summary(t):
    if t["product"]=="Bond": return f'{t["side"]} {t["face_amount"]:,.0f} {t["bond_currency"]} @ {t["clean_price"]:.4f}'
    if t["product"]=="IRS": return f'{t["direction"]} {t["notional"]:,.0f} {t["irs_currency"]} @ {t["fixed_rate"]:.4f}% vs {t["floating_index"]}'
    return f'BUY {t["buy_amount"]:,.0f} {t["buy_currency"]} / SELL {t["sell_amount"]:,.0f} {t["sell_currency"]} @ {t["forward_rate"]:.6f}'

def send_confirmation(trade_id:str,pdf_path:Path,actor="USER")->dict:
    trade=get_trade(trade_id)
    if not trade: raise ValueError("Trade not found.")
    if trade["confirmation_status"]!="GENERATED": raise ValueError("Generate the confirmation before sending it.")
    cp=get_counterparty(trade["counterparty"]); mode=os.getenv("APP_MODE","DEMO").upper(); subject=f"Trade Recap {trade_id} | {trade['instrument']}"
    body=f"""Dear Operations Team,\n\nPlease find attached the demonstration trade recap for {trade_id}.\n\nProduct: {trade['product']}\nInstrument: {trade['instrument']}\nEconomics: {summary(trade)}\n\nPlease review the trade economics.\n\nRegards,\nTrade Blotter\n"""
    if mode!="LIVE":
        update_confirmation_status(trade_id,"SENT_DEMO"); log_event(trade_id,"EMAIL_SENT_DEMO",actor,f"To={cp['confirmation_email']}; Subject={subject}"); return {"mode":"DEMO","to":cp["confirmation_email"],"subject":subject}
    host=os.environ["SMTP_HOST"]; port=int(os.getenv("SMTP_PORT","587")); username=os.environ["SMTP_USERNAME"]; password=os.environ["SMTP_PASSWORD"]; sender=os.environ["SMTP_FROM"]
    msg=EmailMessage(); msg["From"],msg["To"],msg["Subject"]=sender,cp["confirmation_email"],subject; msg.set_content(body); msg.add_attachment(pdf_path.read_bytes(),maintype="application",subtype="pdf",filename=pdf_path.name)
    with smtplib.SMTP(host,port,timeout=20) as smtp: smtp.starttls(); smtp.login(username,password); smtp.send_message(msg)
    update_confirmation_status(trade_id,"SENT"); log_event(trade_id,"EMAIL_SENT",actor,f"To={cp['confirmation_email']}; Subject={subject}"); return {"mode":"LIVE","to":cp["confirmation_email"],"subject":subject}
