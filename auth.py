"""
auth.py — Authentication helpers
"""

import streamlit as st
from db import hash_pw
from config import get_conn


def authenticate(username: str, password: str) -> dict | None:
    """
    Verify credentials against the users table.
    Returns user dict on success, None on failure.
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT full_name, role, password_hash, salt, active FROM users WHERE username = ?",
            (username.strip(),)
        )
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row or not row[4]:
        return None

    full_name, role, stored_hash, salt, _ = row
    h, _ = hash_pw(password, salt)
    if h == stored_hash:
        return {"username": username.strip(), "full_name": full_name, "role": role}
    return None


def require_login() -> bool:
    """
    Returns True if a user is logged in AND still active in the DB.
    Re-checks the DB at most once every 5 minutes to avoid a query on every rerun.
    """
    from datetime import datetime, timedelta
    user = st.session_state.get("user")
    if user is None:
        return False

    now = datetime.now()
    last_check = st.session_state.get("_active_checked_at")
    if last_check and (now - last_check) < timedelta(minutes=5):
        return True

    # Re-verify active flag in DB
    conn = get_conn()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT active FROM users WHERE username=?", (user["username"],))
        row = cursor.fetchone()
    finally:
        conn.close()

    if not row or not row[0]:
        # Deactivated — force logout
        st.session_state.clear()
        return False

    st.session_state["_active_checked_at"] = now
    return True


def current_user() -> dict:
    return st.session_state.get("user", {})


def logout():
    # Clear all session state so cached data from the previous user doesn't leak
    st.session_state.clear()
    st.rerun()


# ── Production day helpers ────────────────────────────────────────────────────
from datetime import date, datetime, timedelta

def production_day() -> date:
    """
    Returns the current PRODUCTION DAY date.

    The production day belongs to the date the Night shift STARTED.
    Night shift runs 21:00 – 07:00, so between midnight and 07:00
    we are still in the previous calendar day's production day.

    Examples:
      2026-03-22 06:30 → production day is 2026-03-21  (Night shift still running)
      2026-03-22 08:00 → production day is 2026-03-22  (Morning shift)
      2026-03-22 22:30 → production day is 2026-03-22  (Night shift just started)
    """
    now = datetime.now()
    # Night shift carryover: 00:00 to 07:00 belongs to the previous production day
    if now.hour < 7:
        return now.date() - timedelta(days=1)
    return now.date()


def current_shift() -> str:
    """
    Returns the current shift name based on wall-clock time.
      07:00 – 14:00  Morning
      14:00 – 21:00  Afternoon
      21:00 – 07:00  Night  (crosses midnight)
    """
    from data.reference import SHIFTS
    h = datetime.now().hour
    if 7 <= h < 14:  return SHIFTS[0]   # Morning
    if 14 <= h < 21: return SHIFTS[1]   # Afternoon
    return SHIFTS[2]                     # Night (21:00–07:00)