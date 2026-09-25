"""
Trade Blotter - Counterparty service

Provides access to the synthetic counterparties used in the demo.
Counterparty information is used throughout the trade capture
and confirmation workflows.
"""

from core.database import connect

def list_counterparties():
    with connect() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM counterparties WHERE active=1 ORDER BY name").fetchall()]

def get_counterparty(name):
    with connect() as con:
        r = con.execute("SELECT * FROM counterparties WHERE name=?", (name,)).fetchone()
        return dict(r) if r else None
