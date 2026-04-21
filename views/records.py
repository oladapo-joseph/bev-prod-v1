"""
views/records.py — Historical Records
Two tabs: Production Runs (closed) and Fault Records.
Manager/admin also get an Edit Records tab.
Engineers only see Fault Records.
"""

import streamlit as st
from datetime import datetime
from config import read_sql, execute
from auth import current_user
from data.reference import LINES, SHIFTS, PRODUCT_NAMES, FAULT_MACHINES
from components.ui import efficiency, section_header


def render():
    st.markdown("# 📁 Historical Records")
    role        = current_user().get("role", "")
    is_engineer = role == "engineer"
    can_edit    = role in ("manager", "admin")

    if is_engineer:
        tab2, = st.tabs(["Fault Records"])
    else:
        tabs = ["Production Runs", "Fault Records"] + (["✏️ Edit Records"] if can_edit else [])
        tab1, tab2, *_edit_tabs = st.tabs(tabs)
        tab_edit = _edit_tabs[0] if _edit_tabs else None

    # ── Production Runs (non-engineers only) ──────────────────────────────────
    if not is_engineer:
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
                if fl  != "All Lines":    df = df[df["line_number"]  == int(fl.split(" ")[1])]
                if fs  != "All Shifts":   df = df[df["shift"]        == fs]
                if fp  != "All Products": df = df[df["product_name"] == fp]
                if fst != "All":          df = df[df["status"]       == fst]

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
            ff1, ff2, ff3, ff4 = st.columns(4)
            with ff1: ffl  = st.selectbox("Line",    ["All Lines"]    + [f"Line {i}" for i in LINES], key="fl_line")
            with ff2: ffm  = st.selectbox("Machine", ["All Machines"] + FAULT_MACHINES, key="fl_machine")
            with ff3: fflk = st.selectbox("Linked",  ["All", "Linked to run", "Unlinked"], key="fl_linked")
            with ff4: ffst = st.selectbox("Status",  ["All", "open", "closed"], key="fl_status")

            fdf = all_faults.copy()
            if ffl  != "All Lines":     fdf = fdf[fdf["line_number"]   == int(ffl.split(" ")[1])]
            if ffm  != "All Machines":  fdf = fdf[fdf["fault_machine"] == ffm]
            if fflk == "Linked to run": fdf = fdf[fdf["production_run_id"].notna()]
            elif fflk == "Unlinked":    fdf = fdf[fdf["production_run_id"].isna()]
            if ffst != "All":           fdf = fdf[fdf["status"].fillna("open") == ffst]

            display_cols = [
                "record_date", "shift", "line_number", "fault_time",
                "fault_machine", "fault_detail", "downtime_minutes",
                "actual_downtime_minutes", "status", "root_cause",
                "reported_by", "notes", "engineer_notes",
                "closed_by", "production_run_id", "logged_by"
            ]
            display_cols = [c for c in display_cols if c in fdf.columns]
            st.dataframe(fdf[display_cols], use_container_width=True, hide_index=True)
            st.download_button(
                "⬇️ Export CSV",
                fdf[display_cols].to_csv(index=False).encode(),
                "fault_records.csv", "text/csv"
            )

    # ── Edit Records (manager / admin only) ───────────────────────────────────
    if not is_engineer and can_edit:
        with tab_edit:
            section_header("Edit a closed production run")
            st.caption("Changes are logged by your username and are permanent.")

            closed_runs = read_sql(
                "SELECT id, record_date, shift, line_number, product_name, flavor, "
                "pack_size, packaging, packs_produced, packs_rejected, packs_target, "
                "handover_note, logged_by, edited_by, edited_at "
                "FROM production_runs WHERE status='closed' "
                "ORDER BY record_date DESC, line_number"
            )

            if closed_runs.empty:
                st.info("No closed runs to edit.")
            else:
                run_map = {
                    f"[{r.record_date}] Line {r.line_number} — "
                    f"{r.product_name} {r.flavor or ''} {r.pack_size or ''} {r.packaging or ''} "
                    f"| {r.shift.split('(')[0].strip()}": r
                    for r in closed_runs.itertuples()
                }
                selected_label = st.selectbox("Select run to edit", list(run_map.keys()), key="edit_sel")
                er = run_map[selected_label]

                edited_by = getattr(er, "edited_by", None) or None
                edited_at = getattr(er, "edited_at", None) or None
                edit_info = f" &nbsp;·&nbsp; **Last edited by:** {edited_by} at {edited_at}" if edited_by else ""
                st.markdown(f"**Run ID:** `{er.id}` &nbsp;·&nbsp; **Logged by:** {er.logged_by or '—'}{edit_info}")
                st.markdown("")

                _eid = er.id
                ec1, ec2 = st.columns(2)
                with ec1:
                    e_produced = st.number_input(
                        "Packs Produced (cases)", min_value=0, step=1,
                        value=int(er.packs_produced or 0), key=f"edit_prod_{_eid}"
                    )
                with ec2:
                    e_rejected = st.number_input(
                        "Packs Rejected", min_value=0, step=1,
                        value=int(er.packs_rejected or 0), key=f"edit_rej_{_eid}"
                    )

                e_target = st.number_input(
                    "Target (cases) — override if needed", min_value=0, step=1,
                    value=int(er.packs_target or 0), key=f"edit_tgt_{_eid}",
                    help="Leave as-is to keep the auto-calculated run-time target"
                )
                e_note = st.text_area(
                    "Handover Note", value=er.handover_note or "No note", height=80, key=f"edit_note_{_eid}"
                )

                e_confirmed = st.checkbox(
                    "Confirm edit — this will overwrite the existing record", key=f"edit_confirm_{_eid}"
                )

                if st.button("💾  Save Changes", disabled=not e_confirmed, key=f"edit_save_{_eid}"):
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    editor  = current_user().get("username", "unknown")
                    execute(
                        "UPDATE production_runs SET "
                        "packs_produced=?, packs_rejected=?, packs_target=?, handover_note=?, "
                        "edited_by=?, edited_at=? "
                        "WHERE id=?",
                        (e_produced, e_rejected, e_target, e_note.strip() or None,
                         editor, now_str, int(er.id)),
                    )
                    st.success(f"✅ Run ID {er.id} updated by {editor} at {now_str}.")
                    st.rerun()
