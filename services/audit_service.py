"""
Trade Blotter - Audit service

Records key actions performed throughout the trade lifecycle.
Audit events provide a chronological history of booking,
confirmation generation, delivery and matching activities.
"""

from datetime import datetime
from core.database import connect


def log_event(trade_id: str | None, event_type: str, actor: str = "SYSTEM", details: str = "", event_time: str | None = None):
    """Append an immutable audit event. event_time is optional and mainly used by the synthetic demo seeder."""
    with connect() as con:
        if event_time:
            con.execute(
                "INSERT INTO audit_events(event_time,trade_id,event_type,actor,details) VALUES(?,?,?,?,?)",
                (event_time, trade_id, event_type, actor, details),
            )
        else:
            # Use the application's local clock explicitly. SQLite CURRENT_TIMESTAMP is UTC,
            # which made freshly-created demo events appear roughly two hours old in France.
            local_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            con.execute(
                "INSERT INTO audit_events(event_time,trade_id,event_type,actor,details) VALUES(?,?,?,?,?)",
                (local_now, trade_id, event_type, actor, details),
            )
