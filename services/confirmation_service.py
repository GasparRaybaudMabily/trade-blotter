"""
Trade Blotter - Confirmation service

Handles the trade confirmation workflow and PDF recap generation.
It creates product-specific trade recaps and supports their retrieval
throughout the post-trade lifecycle.
"""

from datetime import datetime
from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from services.trade_service import get_trade, update_confirmation_status
from services.audit_service import log_event
from services.counterparty_service import get_counterparty

OUT=Path(__file__).resolve().parents[1]/"data"/"generated"
NAVY=colors.HexColor("#17365D")
BLUE=colors.HexColor("#2E75B6")
LIGHT=colors.HexColor("#F5F7FA")
BORDER=colors.HexColor("#D6DEE8")
TEXT=colors.HexColor("#263244")
MUTED=colors.HexColor("#667085")


def _amount(currency, value):
    return f"{currency} {float(value):,.0f}"


def economics_rows(t):
    if t["product"]=="Bond":
        return [["ISIN",t["isin"]],["Direction",t["side"]],["Face Amount",_amount(t["bond_currency"],t["face_amount"])],["Clean Price",f'{t["clean_price"]:.3f}'],["Maturity",t["bond_maturity"]],["Settlement",t["settlement_date"]]]
    if t["product"]=="IRS":
        return [["Direction",t["direction"].replace("_"," ")],["Notional",_amount(t["irs_currency"],t["notional"])],["Fixed Rate",f'{t["fixed_rate"]:.3f}%'],["Floating Index",t["floating_index"]],["Effective Date",t["effective_date"]],["Maturity",t["irs_maturity"]]]
    return [["Currency Pair",t["currency_pair"]],["Buy",_amount(t["buy_currency"],t["buy_amount"])],["Sell",_amount(t["sell_currency"],t["sell_amount"])],["Forward Rate",f'{t["forward_rate"]:.6f}'],["Value Date",t["value_date"]]]


def _section_table(rows, widths=(150,330)):
    table=Table(rows,colWidths=list(widths),hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(0,-1),LIGHT),("TEXTCOLOR",(0,0),(-1,-1),TEXT),
        ("FONTNAME",(0,0),(0,-1),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),9.5),
        ("LINEBELOW",(0,0),(-1,-1),0.35,BORDER),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
        ("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7),
    ]))
    return table


def render_trade_recap(trade_id:str, generated_at:str|None=None)->Path:
    """Render a stable trade-recap snapshot without changing workflow state."""
    trade=get_trade(trade_id)
    if not trade: raise ValueError("Trade not found.")
    cp=get_counterparty(trade["counterparty"])
    generated_at=generated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/f"{trade_id}_trade_recap.pdf"

    styles=getSampleStyleSheet()
    title=ParagraphStyle("recapTitle",parent=styles["Title"],fontName="Helvetica-Bold",fontSize=20,leading=24,textColor=NAVY,alignment=TA_LEFT,spaceAfter=2)
    subtitle=ParagraphStyle("subtitle",parent=styles["Normal"],fontSize=9,textColor=MUTED,leading=12)
    section=ParagraphStyle("section",parent=styles["Heading2"],fontName="Helvetica-Bold",fontSize=11,textColor=NAVY,spaceBefore=12,spaceAfter=6)
    demo=ParagraphStyle("demo",parent=styles["Normal"],fontName="Helvetica-Bold",fontSize=9,textColor=colors.white,alignment=TA_CENTER,leading=12)
    body=ParagraphStyle("body",parent=styles["BodyText"],fontSize=8.5,textColor=MUTED,leading=12)
    doc=SimpleDocTemplate(str(path),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=36,bottomMargin=36,title=f"Trade Recap {trade_id}")

    header=Table([[Paragraph("TRADE BLOTTER",title),Paragraph("TRADE RECAP",ParagraphStyle("r",parent=title,alignment=2,fontSize=14))],
                  [Paragraph("Post-Trade Management & Control Platform",subtitle),Paragraph(trade["product"],ParagraphStyle("rp",parent=subtitle,alignment=2))]],colWidths=[330,150])
    header.setStyle(TableStyle([("LINEBELOW",(0,-1),(-1,-1),1.5,BLUE),("BOTTOMPADDING",(0,-1),(-1,-1),9)]))
    banner=Table([[Paragraph("DEMONSTRATION DOCUMENT · SYNTHETIC DATA · NOT A LEGAL CONFIRMATION",demo)]],colWidths=[480])
    banner.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),NAVY),("TOPPADDING",(0,0),(-1,-1),7),("BOTTOMPADDING",(0,0),(-1,-1),7)]))

    reference=[["Trade Reference",trade["trade_id"]],["Trade Date / Time",f'{trade["trade_date"]} {trade["trade_time"]}'],["Product",trade["product"]],["Instrument",trade["instrument"]]]
    execution=[["Trader / Desk",f'{trade["trader"]} / {trade["desk"]}'],["Broker",trade["broker"]],["Counterparty",trade["counterparty"]],["Counterparty LEI",cp.get("lei","") if cp else ""]]
    document_info=[["Generated At",generated_at],["Delivery Channel",cp.get("confirmation_channel","EMAIL") if cp else "EMAIL"],["Document Type","TRADE RECAP"]]

    story=[header,Spacer(1,10),banner,Spacer(1,14),Paragraph("TRADE REFERENCE",section),_section_table(reference),
           Paragraph("TRADE ECONOMICS",section),_section_table(economics_rows(trade)),
           Paragraph("EXECUTION & COUNTERPARTY",section),_section_table(execution),
           Paragraph("DOCUMENT INFORMATION",section),_section_table(document_info),Spacer(1,16),
           Paragraph("This recap is generated by a portfolio demonstration application. All entities, identifiers and trade data are synthetic and the document is not intended for live trading, settlement or legal reliance.",body)]
    doc.build(story)
    return path


def generate_confirmation(trade_id:str,actor="USER")->Path:
    """Create the recap exactly once as the NOT_GENERATED -> GENERATED transition."""
    trade=get_trade(trade_id)
    if not trade: raise ValueError("Trade not found.")
    if trade["confirmation_status"]!="NOT_GENERATED":
        raise ValueError("A trade recap can only be generated from NOT_GENERATED status.")
    generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path=render_trade_recap(trade_id,generated_at)
    update_confirmation_status(trade_id,"GENERATED")
    log_event(trade_id,"CONFIRMATION_GENERATED",actor,path.name,generated_at)
    return path
