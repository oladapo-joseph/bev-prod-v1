"""
pages/user_management.py — User Management page (Admin only)
"""

import streamlit as st
import pyodbc

from config import read_sql, execute
from db import hash_pw
from components.ui import section_header


def render():
    st.markdown("# 👤 User Management")
    section_header("Admin only — manage system users")

    users_df = read_sql("SELECT id, username, full_name, role, active, created_at FROM users ORDER BY role, username")
    st.dataframe(
        users_df.rename(columns={"id": "ID", "username": "Username", "full_name": "Full Name",
                                  "role": "Role", "active": "Active", "created_at": "Created"}),
        use_container_width=True, hide_index=True,
    )

    st.markdown("---")
    st.markdown("### Add New User")

    # Incrementing this key forces all input widgets below to re-mount as
    # fresh (empty) widgets after a successful submission.
    _form_ver = st.session_state.get("_um_form_ver", 0)

    na1, na2 = st.columns(2)
    with na1:
        new_user     = st.text_input("Username",  placeholder="e.g. lead3",    key=f"um_user_{_form_ver}")
        new_fullname = st.text_input("Full Name", placeholder="e.g. John Doe", key=f"um_name_{_form_ver}")
    with na2:
        new_role = st.selectbox("Role", ["shift_lead", "engineer", "manager", "admin"], key=f"um_role_{_form_ver}")
        new_pw   = st.text_input("Password",         type="password", key=f"um_pw_{_form_ver}")
        new_pw2  = st.text_input("Confirm Password", type="password", key=f"um_pw2_{_form_ver}")

    if st.button("➕ Add User"):
        if not all([new_user, new_fullname, new_pw]):
            st.error("Please fill in all fields.")
        elif new_pw != new_pw2:
            st.error("Passwords do not match.")
        else:
            h, s = hash_pw(new_pw)
            try:
                execute(
                    "INSERT INTO users (username, full_name, role, password_hash, salt) VALUES (?,?,?,?,?)",
                    (new_user.strip(), new_fullname, new_role, h, s),
                )
                st.success(f"✅ User '{new_user}' created as {new_role}")
                st.session_state["_um_form_ver"] = _form_ver + 1
                st.rerun()
            except pyodbc.Error as e:
                if "unique" in str(e).lower() or "duplicate" in str(e).lower() or "2627" in str(e) or "2601" in str(e):
                    st.error("Username already exists.")
                else:
                    st.error(f"Error creating user: {e}")

    st.markdown("---")
    st.markdown("### Deactivate / Reactivate User")
    da1, da2 = st.columns(2)
    with da1:
        toggle_user = st.selectbox("Select User", users_df["username"].tolist())
    with da2:
        action = st.selectbox("Action", ["Deactivate", "Reactivate"])

    if st.button("Apply"):
        execute(
            "UPDATE users SET active=? WHERE username=?",
            (0 if action == "Deactivate" else 1, toggle_user),
        )
        st.success(f"User '{toggle_user}' {action.lower()}d.")
        st.rerun()