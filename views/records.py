"""
views/records.py — Historical Records
Two tabs: Production Runs (closed) and Fault Records.
"""

import streamlit as st
from config import read_sql
from data.reference import LINES, SHIFTS, PRODUCT_NAMES, FAULT_MACHINES
from components.ui import efficiency, section_header


def render():
    st.markdown("# 📁 Historical Records")
    tab1, tab2 = st.tabs(["Production Runs", "Fault Records"])

    # ── Production Runs ───────────────────────────────────────────────────────
    with tab1:
        all_runs = read_sql(
            "SELECT * FROM production_runs ORDER BY record_date DESC, line_number, run_start"
        )
        if all_runs.empty:
            st.info("No production runs yet.")
        else:
            cf1, cf2, cf3, cf4 = st.columns(4)
            with cf1: fl  = st.selectbox("Line",    ["All Lines"]    + [f"Line {i}" for i in LINES])
            with cf2: fs  = st.selectbox("Shift",   ["All Shifts"]   + SHIFTS, key="p_shift")
            with cf3: fp  = st.selectbox("Product", ["All Products"] + PRODUCT_NAMES)
            with cf4: fst = st.selectbox("Status",  ["All", "closed", "open"])

            df = all_runs.copy()
            if fl  != "All Lines":    df = df[df["line_number"]   == int(fl.split(" ")[1])]
            if fs  != "All Shifts":   df = df[df["shift"]         == fs]
            if fp  != "All Products": df = df[df["product_name"]  == fp]
            if fst != "All":          df = df[df["status"]        == fst]

            # Compute efficiency only for closed runs with data
            def _eff(r):
                if r.get("status") == "closed" and r.get("packs_target", 0):
                    return efficiency(int(r.get("packs_produced") or 0), int(r["packs_target"]))
                return "—"
            df["efficiency_%"] = df.apply(_eff, axis=1)

            display_cols = [
                "record_date", "shift", "line_number", "product_name", "flavor",
                "pack_size", "packaging", "packs_produced", "packs_target",
                "efficiency_%", "actual_time_hrs", "down_time_hrs",
                "run_start", "run_end", "status", "operator_name", "handover_note", "logged_by"
            ]
            display_cols = [c for c in display_cols if c in df.columns]
            st.dataframe(df[display_cols], use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Export CSV",
                df[display_cols].to_csv(index=False).encode(),
                "production_runs.csv", "text/csv"
            )

    # ── Fault Records ─────────────────────────────────────────────────────────
    with tab2:
        all_faults = read_sql(
            "SELECT * FROM fault_records ORDER BY record_date DESC, line_number, fault_time"
        )
        if all_faults.empty:
            st.info("No fault records yet.")
        else:
            ff1, ff2, ff3 = st.columns(3)
            with ff1: ffl  = st.selectbox("Line",    ["All Lines"]    + [f"Line {i}" for i in LINES], key="fl_line")
            with ff2: ffm  = st.selectbox("Machine", ["All Machines"] + FAULT_MACHINES, key="fl_machine")
            with ff3: fflk = st.selectbox("Linked",  ["All", "Linked to run", "Unlinked"], key="fl_linked")

            fdf = all_faults.copy()
            if ffl  != "All Lines":        fdf = fdf[fdf["line_number"]    == int(ffl.split(" ")[1])]
            if ffm  != "All Machines":     fdf = fdf[fdf["fault_machine"]  == ffm]
            if fflk == "Linked to run":    fdf = fdf[fdf["production_run_id"].notna()]
            elif fflk == "Unlinked":       fdf = fdf[fdf["production_run_id"].isna()]

            display_cols = [
                "record_date", "shift", "line_number", "fault_time",
                "fault_machine", "fault_detail", "downtime_minutes",
                "reported_by", "notes", "production_run_id", "logged_by"
            ]
            display_cols = [c for c in display_cols if c in fdf.columns]
            st.dataframe(fdf[display_cols], use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Export CSV",
                fdf[display_cols].to_csv(index=False).encode(),
                "fault_records.csv", "text/csv"
            )