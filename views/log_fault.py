"""
views/log_fault.py — Log Fault / Downtime
------------------------------------------
Faults are automatically linked to the currently open run on the selected line.
If no run is open, the fault is saved unlinked with a clear warning.
The backfill step on run close handles any remaining edge cases.
"""

import streamlit as st
from datetime import date, datetime

from auth import production_day, current_shift, now
from config import read_sql, execute
from data.reference import LINES, SHIFTS, FAULT_DATA, FAULT_MACHINES
from components.ui import section_header


def render(username: str, full_name: str):
    st.markdown("# ⚠️ Log Fault / Downtime")
    section_header("Faults are auto-linked to the active run on the selected line")

    if "fault_form_key" not in st.session_state:
        st.session_state["fault_form_key"] = 0
    ffk = st.session_state["fault_form_key"]

    # ── Line & shift selectors ────────────────────────────────────────────────
    _cur_shift = current_shift()
    _shift_idx = SHIFTS.index(_cur_shift) + 1 if _cur_shift in SHIFTS else 0

    c1, c2, c3 = st.columns(3)
    with c1:
        st.text_input("Date", value=str(production_day()), disabled=True, key=f"fd_{ffk}")
    with c2:
        f_shift = st.selectbox("Shift", ["— Select Shift —"] + SHIFTS, index=_shift_idx, key=f"fs_{ffk}")
    with c3:
        f_line = st.selectbox(
            "Line Number", ["— Select Line —"] + LINES,
            format_func=lambda x: f"Line {x}" if isinstance(x, int) else x,
            key=f"fl_{ffk}",
        )

    # ── Auto-detect open run on this line ────────────────────────────────────
    active_run_id   = None
    active_run_info = None

    if isinstance(f_line, int):
        open_run = read_sql(
            "SELECT id, product_name, flavor, pack_size, packaging, shift, run_start "
            "FROM production_runs "
            "WHERE line_number=? AND status='open' "
            "ORDER BY run_start DESC",
            params=[f_line],
        )
        if not open_run.empty:
            r               = open_run.iloc[0]
            active_run_id   = int(r["id"])
            active_run_info = r

    # ── Status banner ─────────────────────────────────────────────────────────
    if isinstance(f_line, int):
        if active_run_info is not None:
            r = active_run_info
            prod_str  = "%s %s · %s %s" % (
                r.get("product_name",""), r.get("flavor","") or "",
                r.get("pack_size","")  or "", r.get("packaging","") or "",
            )
            shift_str = str(r.get("shift","")).split("(")[0].strip()
            start_str = str(r.get("run_start",""))[:16]
            st.markdown(
                "<div style='background:#00e5a010;border:1px solid var(--accent);"
                "border-radius:8px;padding:12px 16px;margin-bottom:8px'>"
                "<div style='font-size:.75rem;color:var(--accent);font-family:Space Mono,"
                "monospace;text-transform:uppercase;font-weight:700'>"
                "▶ Active run detected — fault will be auto-linked</div>"
                "<div style='font-size:.82rem;color:var(--text);margin-top:4px'>%s</div>"
                "<div style='font-size:.72rem;color:var(--muted);margin-top:2px'>"
                "%s · Started %s</div>"
                "</div>" % (prod_str, shift_str, start_str),
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<div style='background:#ff475710;border:1px solid var(--warn);"
                "border-radius:8px;padding:12px 16px;margin-bottom:8px'>"
                "<div style='font-size:.75rem;color:var(--warn);font-family:Space Mono,"
                "monospace;text-transform:uppercase;font-weight:700'>"
                "⚠️ No active run on this line</div>"
                "<div style='font-size:.78rem;color:var(--muted);margin-top:4px'>"
                "Fault will be saved unlinked. "
                "It can be attached manually when a run is closed.</div>"
                "</div>",
                unsafe_allow_html=True,
            )

    st.markdown("---")

    # ── Fault time ────────────────────────────────────────────────────────────
    fault_time_input = st.time_input(
        "Time Fault Occurred",
        value=now().time(),
        key=f"ftime_{ffk}",
        help="When did the fault actually happen? (may differ from now)",
    )
    fault_time_str = fault_time_input.strftime("%H:%M") if fault_time_input else None

    if fault_time_input and fault_time_input > now().time():
        st.warning("⚠️ Fault time is in the future — please enter the actual time the fault occurred.")

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

    # ── Downtime sanity check against run duration ────────────────────────────
    _dt_exceeds = False
    if active_run_id and downtime > 0:
        try:
            run_info = read_sql(
                "SELECT run_start, SUM(f.downtime_minutes) as existing_dt "
                "FROM production_runs p "
                "LEFT JOIN fault_records f ON f.production_run_id = p.id "
                "WHERE p.id = ? GROUP BY p.run_start",
                params=[active_run_id],
            )
            if not run_info.empty:
                run_start_str = str(run_info.iloc[0]["run_start"])[:19]
                elapsed_min   = (now() - datetime.strptime(run_start_str, "%Y-%m-%d %H:%M:%S")).total_seconds() / 60
                existing_dt   = float(run_info.iloc[0]["existing_dt"] or 0)
                total_dt      = existing_dt + downtime
                if total_dt > elapsed_min:
                    _dt_exceeds = True
                    st.error(
                        f"⛔ Cannot save — total downtime would be **{total_dt:.0f} min** "
                        f"but this run has only been active **{elapsed_min:.0f} min**. "
                        f"Reduce the downtime value before saving."
                    )
        except Exception:
            pass

    # ── Validation ────────────────────────────────────────────────────────────
    _ph = ("— Select Machine —", "— Select Detail —", "— Select Machine first —", None)
    _future_time = bool(fault_time_input and fault_time_input > now().time())
    f_ready = (
        f_shift != "— Select Shift —" and isinstance(f_line, int) and
        fault_machine not in _ph and fault_detail not in _ph and
        downtime > 0 and reported_by.strip() != "" and not _future_time and
        not _dt_exceeds
    )
    if not f_ready:
        missing = []
        if f_shift == "— Select Shift —": missing.append("Shift")
        if not isinstance(f_line, int):   missing.append("Line Number")
        if fault_machine in _ph:          missing.append("Fault Machine")
        if fault_detail in _ph:           missing.append("Fault Detail")
        if downtime == 0:                 missing.append("Downtime > 0")
        if not reported_by.strip():       missing.append("Reported By")
        st.info(f"Required: {', '.join(missing)}")

    if st.button("⚠️  Save Fault", disabled=not f_ready, key=f"fsave_{ffk}"):
        execute(
            "INSERT INTO fault_records "
            "(record_date, shift, line_number, fault_time, "
            "fault_machine, fault_detail, downtime_minutes, "
            "reported_by, notes, logged_by, production_run_id, status) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (str(production_day()), f_shift, f_line, fault_time_str,
             fault_machine, fault_detail, downtime,
             reported_by.strip(), notes.strip() or None,
             username, active_run_id, "open"),
        )

        if active_run_id:
            st.success(
                "⚠️ Fault saved & linked — %s › %s | %d min @ %s | Line %d" % (
                    fault_machine, fault_detail, downtime, fault_time_str, f_line
                )
            )
        else:
            st.warning(
                "⚠️ Fault saved (unlinked) — %s › %s | %d min @ %s | Line %d\n\n"
                "No active run was found on this line. Attach it when closing a run." % (
                    fault_machine, fault_detail, downtime, fault_time_str, f_line
                )
            )
        st.session_state["fault_form_key"] += 1
        st.rerun()

    # ── Today's fault log for this line (ALL shifts) ─────────────────────────
    if isinstance(f_line, int):
        st.markdown("---")
        section_header("All faults today — Line %d (all shifts)" % f_line)
        todays = read_sql(
            "SELECT fault_time, shift, fault_machine, fault_detail, "
            "downtime_minutes, reported_by, "
            "CASE WHEN production_run_id IS NULL THEN 'Unlinked' ELSE 'Linked' END as status "
            "FROM fault_records "
            "WHERE record_date=? AND line_number=? "
            "ORDER BY shift, fault_time, created_at",
            params=[str(production_day()), f_line],
        )
        if todays.empty:
            st.info("No faults logged yet for this line today.")
        else:
            total_dt = int(todays["downtime_minutes"].sum())
            linked   = int((todays["status"] == "Linked").sum())
            unlinked = int((todays["status"] == "Unlinked").sum())

            # Summary strip
            st.markdown(
                "<div style='font-family:Space Mono,monospace;font-size:.78rem;"
                "color:var(--muted);margin-bottom:12px'>"
                "Total downtime: <span style='color:var(--warn)'>%d min</span>"
                " &nbsp;|&nbsp; %d fault(s)"
                " &nbsp;|&nbsp; <span style='color:var(--accent)'>%d linked</span>"
                " &nbsp;<span style='color:var(--warn)'>%d unlinked</span>"
                "</div>" % (total_dt, len(todays), linked, unlinked),
                unsafe_allow_html=True,
            )

            # Group by shift so incoming lead can clearly see each shift's issues
            todays["shift_short"] = todays["shift"].str.split("(").str[0].str.strip()
            for shift_name, group in todays.groupby("shift_short", sort=False):
                shift_dt  = int(group["downtime_minutes"].sum())
                shift_fc  = len(group)
                dt_col    = "var(--red)" if shift_dt > 30 else ("var(--warn)" if shift_dt > 0 else "var(--accent)")
                st.markdown(
                    "<div style='display:flex;align-items:center;gap:12px;margin-bottom:6px;margin-top:10px'>"
                    "<span style='font-family:Space Mono,monospace;font-size:.72rem;"
                    "color:var(--muted);text-transform:uppercase;letter-spacing:1px'>%s</span>"
                    "<span style='font-size:.72rem;color:%s'>%d min downtime</span>"
                    "<span style='font-size:.72rem;color:var(--muted)'>%d fault(s)</span>"
                    "</div>" % (shift_name, dt_col, shift_dt, shift_fc),
                    unsafe_allow_html=True,
                )
                display_cols = ["fault_time", "fault_machine", "fault_detail",
                                "downtime_minutes", "reported_by", "status"]
                display_cols = [c for c in display_cols if c in group.columns]
                st.dataframe(
                    group[display_cols].rename(columns={
                        "fault_time":       "Time",
                        "fault_machine":    "Machine",
                        "fault_detail":     "Detail",
                        "downtime_minutes": "Downtime (min)",
                        "reported_by":      "Reported By",
                        "status":           "Status",
                    }),
                    use_container_width=True, hide_index=True,
                )