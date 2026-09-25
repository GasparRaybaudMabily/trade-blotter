"""
Trade Blotter - User service

Provides the synthetic users and roles used by the application.
These demo identities support role-based access for Traders,
Operations and Supervisors.
"""

from core.database import connect


def list_users(active_only=True):
    sql = "SELECT user_id, full_name, role, active FROM users"
    if active_only:
        sql += " WHERE active=1"
    sql += " ORDER BY CASE role WHEN 'TRADER' THEN 1 WHEN 'OPERATIONS' THEN 2 ELSE 3 END, full_name"
    with connect() as con:
        return [dict(r) for r in con.execute(sql).fetchall()]


def get_user(full_name):
    with connect() as con:
        row = con.execute("SELECT user_id, full_name, role, active FROM users WHERE full_name=?", (full_name,)).fetchone()
    return dict(row) if row else None
