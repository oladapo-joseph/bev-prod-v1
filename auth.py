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
    return st.session_state.get("user") is not None


def current_user() -> dict:
    return st.session_state.get("user", {})


def logout():
    st.session_state.pop("user", None)
    st.rerun()