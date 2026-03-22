"""
views/log_fault.py — Log Fault / Downtime
------------------------------------------
Fully independent of production runs.
Faults are logged with:
  - line, shift, date
  - fault_time (when it ACTUALLY happened, not when logged)
  - machine, detail, downtime, reporter, notes
production_run_id is NULL and gets backfilled when the run is closed.
A sidebar badge shows unlinked fault count for awareness.
"""

import streamlit as st
from datetime import date, datetime

from config import read_sql, execute
from data.reference import LINES, SHIFTS, FAULT_DATA, FAULT_MACHINES
from components.ui import section_header


def render(username: str, full_name: str):
    st.markdown("# ⚠️ Log Fault / Downtime")
    section_header("Log faults as they happen — independent of production records")

    if "fault_form_key" not in st.session_state:
        st.session_state["fault_form_key"] = 0
    ffk = st.session_state["fault_form_key"]

    # ── Context selectors ─────────────────────────────────────────────────────
    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("Date", value=str(date.today()), disabled=True, key=f"fd_{ffk}")
    with c2:
        f_shift = st.selectbox("Shift", ["— Select Shift —"] + SHIFTS, key=f"fs_{ffk}")
    with c3:
        f_line = st.selectbox(
            "Line Number", ["— Select Line —"] + LINES,
            format_func=lambda x: f"Line {x}" if isinstance(x, int) else x,
            key=f"fl_{ffk}",
        )

    # ── Show open run on this line (informational only) ───────────────────────
    if f_shift != "— Select Shift —" and isinstance(f_line, int):
        open_run = read_sql(
            """SELECT id, product_name, flavor, pack_size, packaging, run_start
               FROM production_runs
               WHERE record_date=? AND shift=? AND line_number=? AND status='open'
               ORDER BY run_start DESC""",
            params=[str(date.today()), f_shift, f_line],
        )
        if not open_run.empty:
            r = open_run.iloc[0]
            st.markdown(
                f"<div style='background:#00e5a010;border:1px solid var(--accent);border-radius:8px;"
                f"padding:10px 16px;margin-bottom:4px'>"
                f"<span style='font-size:.75rem;color:var(--accent);font-family:Space Mono,monospace;"
                f"text-transform:uppercase'>▶ Active run on this line: "
                f"{r['product_name']} {r.get('flavor','') or ''} "
                f"{r.get('pack_size','') or ''} — started {r['run_start']}</span><br>"
                f"<span style='font-size:.72rem;color:var(--muted)'>"
                f"This fault will be available to link when the run is closed.</span></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='background:#ffffff08;border:1px solid var(--border);border-radius:8px;"
                "padding:10px 16px;margin-bottom:4px'>"
                "<span style='font-size:.75rem;color:var(--muted)'>No active run on this line — "
                "fault will be saved as unlinked and can be attached when a run is closed.</span></div>",
                unsafe_allow_html=True,
            )

        # Unlinked fault count for this line/shift today
        unlinked_count = read_sql(
            """SELECT COUNT(*) as cnt FROM fault_records
               WHERE record_date=? AND shift=? AND line_number=?
                 AND production_run_id IS NULL""",
            params=[str(date.today()), f_shift, f_line],
        )
        cnt = int(unlinked_count["cnt"].iloc[0]) if not unlinked_count.empty else 0
        if cnt > 0:
            st.markdown(
                f"<div style='font-size:.75rem;color:var(--warn);margin-bottom:12px'>"
                f"⚠️ {cnt} unlinked fault(s) already logged for this line/shift today.</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Fault time ────────────────────────────────────────────────────────────
    fault_time_input = st.time_input(
        "Time Fault Occurred",
        value=datetime.now().time(),
        key=f"ftime_{ffk}",
        help="When did the fault actually happen? (may differ from now)",
    )
    fault_time_str = fault_time_input.strftime("%H:%M") if fault_time_input else None

    # ── Fault details ─────────────────────────────────────────────────────────
    c4, c5 = st.columns(2)
    with c4:
        fault_machine = st.selectbox(
            "Fault Area / Machine", ["— Select Machine —"] + FAULT_MACHINES, key=f"fm_{ffk}"
        )
        if fault_machine and fault_machine != "— Select Machine —":
            fault_detail = st.selectbox(
                "Fault Detail", ["— Select Detail —"] + FAULT_DATA[fault_machine], key=f"fdet_{ffk}"
            )
        else:
            st.selectbox("Fault Detail", ["— Select Machine first —"], disabled=True, key=f"fdet_{ffk}")
            fault_detail = None
    with c5:
        downtime    = st.number_input("Downtime (minutes)", min_value=0, step=1, value=0, key=f"fdt_{ffk}")
        reported_by = st.text_input("Reported By", value=full_name, key=f"frep_{ffk}")

    notes = st.text_area(
        "Notes (optional)", height=90,
        placeholder="Root cause, actions taken, parts replaced…",
        key=f"fnotes_{ffk}",
    )

    # ── Validation ────────────────────────────────────────────────────────────
    _ph = ("— Select Machine —", "— Select Detail —", "— Select Machine first —", None)
    f_ready = (
        f_shift != "— Select Shift —" and isinstance(f_line, int) and
        fault_machine not in _ph and fault_detail not in _ph and
        downtime > 0 and reported_by.strip() != ""
    )
    if not f_ready:
        missing = []
        if f_shift == "— Select Shift —":   missing.append("Shift")
        if not isinstance(f_line, int):     missing.append("Line Number")
        if fault_machine in _ph:            missing.append("Fault Machine")
        if fault_detail in _ph:             missing.append("Fault Detail")
        if downtime == 0:                   missing.append("Downtime > 0")
        if not reported_by.strip():         missing.append("Reported By")
        st.info(f"Required: {', '.join(missing)}")

    if st.button("⚠️  Save Fault", disabled=not f_ready, key=f"fsave_{ffk}"):
        execute(
            """INSERT INTO fault_records
               (record_date, shift, line_number, fault_time,
                fault_machine, fault_detail, downtime_minutes,
                reported_by, notes, logged_by)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (str(date.today()), f_shift, f_line, fault_time_str,
             fault_machine, fault_detail, downtime,
             reported_by.strip(), notes.strip() or None, username),
        )
        st.success(
            f"⚠️ Fault saved — {fault_machine} › {fault_detail} | "
            f"{downtime} min @ {fault_time_str} | Line {f_line} "
            f"(unlinked — will attach on run close)"
        )
        st.session_state["fault_form_key"] += 1
        st.rerun()

    # ── Today's fault log for this line ──────────────────────────────────────
    if f_shift != "— Select Shift —" and isinstance(f_line, int):
        st.markdown("---")
        section_header(f"Today's faults — Line {f_line} · {f_shift.split('(')[0].strip()}")
        todays = read_sql(
            """SELECT fault_time, fault_machine, fault_detail,
                      downtime_minutes, reported_by,
                      CASE WHEN production_run_id IS NULL THEN 'Unlinked' ELSE 'Linked' END as status
               FROM fault_records
               WHERE record_date=? AND shift=? AND line_number=?
               ORDER BY fault_time, created_at""",
            params=[str(date.today()), f_shift, f_line],
        )
        if todays.empty:
            st.info("No faults logged yet for this line/shift today.")
        else:
            total_dt = int(todays["downtime_minutes"].sum())
            st.markdown(
                f"<div style='font-family:Space Mono,monospace;font-size:.8rem;"
                f"color:var(--muted);margin-bottom:8px'>"
                f"Total downtime: <span style='color:var(--warn)'>{total_dt} min</span> "
                f"across {len(todays)} fault(s)</div>",
                unsafe_allow_html=True,
            )
            st.dataframe(
                todays.rename(columns={
                    "fault_time": "Time", "fault_machine": "Machine",
                    "fault_detail": "Detail", "downtime_minutes": "Downtime (min)",
                    "reported_by": "Reported By", "status": "Status",
                }),
                use_container_width=True, hide_index=True,
            )