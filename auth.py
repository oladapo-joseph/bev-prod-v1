"""
auth.py — Authentication helpers
"""

import streamlit as st
from datetime import date, datetime, timedelta, timezone
from db import hash_pw
from config import get_conn

# ── Timezone ──────────────────────────────────────────────────────────────────
# All time-aware operations in this app use WAT (West Africa Time = UTC+1).
# WAT does not observe DST, so this offset is always correct.
_WAT = timezone(timedelta(hours=1))


def now() -> datetime:
    """
    Returns the current naive datetime in WAT (GMT+1).
    Use this everywhere instead of datetime.now() so the app is
    timezone-correct regardless of which server it runs on.
    """
    return datetime.now(_WAT).replace(tzinfo=None)


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


SESSION_TIMEOUT_MINUTES = 30


def require_login() -> bool:
    """
    Returns True if a user is logged in, session is still active, and the
    account is still active in the DB (re-checked every 5 minutes).
    Logs the user out automatically after SESSION_TIMEOUT_MINUTES of inactivity.
    """
    user = st.session_state.get("user")
    if user is None:
        return False

    _now = now()

    # ── Inactivity timeout ────────────────────────────────────────────────────
    last_activity = st.session_state.get("_last_activity")
    if last_activity and (_now - last_activity) > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
        st.session_state.clear()
        st.warning(
            f"⏱️ Your session expired after {SESSION_TIMEOUT_MINUTES} minutes of inactivity. "
            "Please log in again."
        )
        return False

    # ── DB active-flag check (at most every 5 minutes) ────────────────────────
    last_check = st.session_state.get("_active_checked_at")
    if not last_check or (_now - last_check) >= timedelta(minutes=5):
        conn = get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT active FROM users WHERE username=?", (user["username"],))
            row = cursor.fetchone()
        finally:
            conn.close()

        if not row or not row[0]:
            st.session_state.clear()
            return False

        st.session_state["_active_checked_at"] = _now

    # Stamp activity on every successful check
    st.session_state["_last_activity"] = _now
    return True


def current_user() -> dict:
    return st.session_state.get("user", {})


def logout():
    # Clear all session state so cached data from the previous user doesn't leak
    st.session_state.clear()
    st.rerun()


# ── Production day helpers ────────────────────────────────────────────────────

def production_day() -> date:
    """
    Returns the current PRODUCTION DAY date in WAT.
    Night shift (21:00–07:00) belongs to the date the shift STARTED,
    so 00:00–07:00 WAT is still the previous calendar day.
    """
    _now = now()
    if _now.hour < 7:
        return _now.date() - timedelta(days=1)
    return _now.date()


def current_shift() -> str:
    """
    Returns the current shift name based on WAT wall-clock time.
      07:00 – 14:00  Morning
      14:00 – 21:00  Afternoon
      21:00 – 07:00  Night  (crosses midnight)
    """
    from data.reference import SHIFTS
    h = now().hour
    if 7 <= h < 14:  return SHIFTS[0]   # Morning
    if 14 <= h < 21: return SHIFTS[1]   # Afternoon
    return SHIFTS[2]                     # Night (21:00–07:00)
