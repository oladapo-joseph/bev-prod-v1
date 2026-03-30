"""
views/shift_handover.py — Shift Handover Summary
-------------------------------------------------
Generates a summary of the current (or selected) shift's production activity
and allows the outgoing shift lead to submit handover comments for the
incoming shift lead to read.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date, timedelta

from auth import production_day, current_shift
from config import read_sql, execute
from data.reference import LINES, SHIFTS
from components.ui import efficiency, eff_color, section_header, kpi_card


# ── Module-level cache for shift data ────────────────────────────────────────
@st.cache_data(ttl=30)
def _load_shift_data(day: str, shift: str):
    runs = read_sql(
        "SELECT * FROM production_runs WHERE record_date=? AND shift=? ORDER BY line_number, run_start",
        params=[day, shift],
    )
    # Also grab runs that closed in this shift (cross-shift)
    closed_in = read_sql(
        "SELECT * FROM production_runs WHERE record_date=? AND closed_shift=? AND status='closed' ORDER BY line_number",
        params=[day, shift],
    )
    faults = read_sql(
        "SELECT * FROM fault_records WHERE record_date=? AND shift=? ORDER BY line_number",
        params=[day, shift],
    )
    open_runs = read_sql(
        "SELECT * FROM production_runs WHERE status='open' ORDER BY line_number, run_start"
    )
    return runs, closed_in, faults, open_runs


@st.cache_data(ttl=30)
def _load_handovers(day: str):
    return read_sql(
        "SELECT shift, full_name, submitted_by, comments, submitted_at "
        "FROM shift_handovers WHERE record_date=? ORDER BY submitted_at DESC",
        params=[day],
    )


def _prev_shift(shift_str: str) -> str:
    """Return the shift that comes before the given one (wraps around)."""
    idx = next((i for i, s in enumerate(SHIFTS) if s == shift_str), None)
    if idx is None:
        return ""
    return SHIFTS[(idx - 1) % len(SHIFTS)]


def render(username: str, full_name: str):
    st.markdown("# 📋 Shift Handover")
    section_header("End-of-shift summary · comments · incoming brief")

    # ── Shift selector ────────────────────────────────────────────────────────
    cur = current_shift()
    cur_idx = SHIFTS.index(cur) if cur in SHIFTS else 0

    sc1, sc2 = st.columns([1, 2])
    with sc1:
        day = st.date_input("Production Date", value=production_day(), key="ho_date")
    with sc2:
        shift = st.selectbox("Shift", SHIFTS, index=cur_idx, key="ho_shift")

    day_str = str(day)

    runs, closed_in, faults, open_runs = _load_shift_data(day_str, shift)

    # Merge: runs opened in this shift + runs closed in this shift (de-duplicated)
    if not runs.empty and not closed_in.empty:
        all_shift_runs = pd.concat([runs, closed_in]).drop_duplicates(subset=["id"])
    elif not runs.empty:
        all_shift_runs = runs
    elif not closed_in.empty:
        all_shift_runs = closed_in
    else:
        all_shift_runs = pd.DataFrame()

    closed_runs = all_shift_runs[all_shift_runs["status"] == "closed"] if not all_shift_runs.empty else pd.DataFrame()

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # KPI STRIP
    # ══════════════════════════════════════════════════════════════════════════
    total_produced = int(closed_runs["packs_produced"].sum()) if not closed_runs.empty else 0
    total_target   = int(closed_runs["packs_target"].sum())   if not closed_runs.empty else 0
    overall_eff    = efficiency(total_produced, total_target)
    total_faults   = len(faults)
    total_dt       = int(faults["downtime_minutes"].sum())     if not faults.empty else 0
    n_closed       = len(closed_runs)
    n_open         = len(open_runs)
    unlinked_ct    = int(faults["production_run_id"].isna().sum()) if not faults.empty else 0

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    with k1: kpi_card(n_closed,             "Runs Closed")
    with k2: kpi_card(f"{total_produced:,}", "Cases Produced")
    with k3: kpi_card(f"{overall_eff}%",     "Efficiency",
                      "danger" if overall_eff < 70 else "warn" if overall_eff < 85 else "")
    with k4: kpi_card(total_faults,          "Faults",
                      "danger" if total_faults >= 10 else "warn" if total_faults > 0 else "")
    with k5: kpi_card(f"{total_dt} min",     "Total Downtime",
                      "danger" if total_dt > 120 else "warn" if total_dt > 60 else "")
    with k6: kpi_card(n_open,               "Open Runs",
                      "warn" if n_open > 0 else "")

    # ══════════════════════════════════════════════════════════════════════════
    # LINE-BY-LINE SUMMARY TABLE
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    section_header("Line-by-line activity")

    if closed_runs.empty:
        st.info("No closed runs for this shift yet.")
    else:
        table_rows = []
        for ln in LINES:
            lp = closed_runs[closed_runs["line_number"] == ln]
            if lp.empty:
                continue
            lf = faults[faults["line_number"] == ln] if not faults.empty else pd.DataFrame()

            products = ", ".join(
                f"{r.get('product_name','')} {r.get('flavor','') or ''} {r.get('pack_size','') or ''} {r.get('packaging','') or ''}".strip()
                for _, r in lp.iterrows()
            )
            produced = int(lp["packs_produced"].sum())
            target   = int(lp["packs_target"].sum())
            eff      = efficiency(produced, target)
            dt_min   = int(lf["downtime_minutes"].sum()) if not lf.empty else 0
            fc       = len(lf)
            runs_str = f"{len(lp)} run(s)"

            table_rows.append({
                "Line":      f"Line {ln}",
                "Products":  products,
                "Runs":      runs_str,
                "Produced":  f"{produced:,}",
                "Target":    f"{target:,}",
                "Eff %":     f"{eff}%",
                "Downtime":  f"{dt_min} min",
                "Faults":    fc,
            })

        if table_rows:
            st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════════
    # OPEN RUNS CARRYING OVER
    # ══════════════════════════════════════════════════════════════════════════
    if not open_runs.empty:
        st.markdown("---")
        section_header("⚠️ Open runs carrying over to next shift")
        for _, r in open_runs.iterrows():
            try:
                elapsed = (datetime.now() - datetime.strptime(
                    str(r.get("run_start", ""))[:19], "%Y-%m-%d %H:%M:%S"
                )).total_seconds() / 3600
                elapsed_str = f"{elapsed:.1f}h elapsed"
            except Exception:
                elapsed_str = ""
            st.markdown(
                "<div style='background:#ffcc0010;border:1px solid var(--warn);"
                "border-radius:10px;padding:12px 18px;margin-bottom:8px'>"
                "<div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>"
                "<span class='line-badge'>LINE %d</span>"
                "<span style='font-size:.9rem;font-weight:500'>%s %s &middot; %s %s</span>"
                "<span style='margin-left:auto;font-size:.75rem;color:var(--warn);font-family:Space Mono,monospace'>▶ OPEN · %s</span>"
                "</div>"
                "<div style='font-size:.76rem;color:var(--muted);margin-top:6px'>"
                "Started: %s &nbsp;·&nbsp; Shift: %s &nbsp;·&nbsp; Operator: %s"
                "</div></div>" % (
                    int(r.get("line_number", 0)),
                    r.get("product_name", ""), r.get("flavor", "") or "",
                    r.get("pack_size", "") or "", r.get("packaging", "") or "",
                    elapsed_str,
                    str(r.get("run_start", ""))[:16],
                    str(r.get("shift", "")).split("(")[0].strip(),
                    r.get("operator_name", "") or "—",
                ),
                unsafe_allow_html=True,
            )

    # ══════════════════════════════════════════════════════════════════════════
    # UNLINKED FAULTS WARNING
    # ══════════════════════════════════════════════════════════════════════════
    if unlinked_ct > 0:
        st.markdown("---")
        st.warning(
            f"⚠️ **{unlinked_ct} unlinked fault(s)** from this shift have not been attached to a run. "
            "Attach them when closing the relevant run before the next shift starts."
        )

    # ══════════════════════════════════════════════════════════════════════════
    # OUTGOING SHIFT LEAD COMMENTS
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    section_header("Outgoing shift lead — handover comments")

    # Check if current user already submitted for this shift today
    existing = read_sql(
        "SELECT id, full_name, comments, submitted_at FROM shift_handovers "
        "WHERE record_date=? AND shift=? AND submitted_by=? ORDER BY submitted_at DESC",
        params=[day_str, shift, username],
    )

    if not existing.empty:
        last = existing.iloc[0]
        st.success(
            f"✅ You submitted a handover for this shift at **{str(last['submitted_at'])[:16]}**."
        )
        with st.expander("View / update your submission"):
            new_comments = st.text_area(
                "Update comments", value=last["comments"] or "", height=140,
                key="ho_update_comments",
            )
            if st.button("💾 Update Handover", key="ho_update_btn"):
                execute(
                    "UPDATE shift_handovers SET comments=?, submitted_at=? WHERE id=?",
                    (new_comments.strip() or None,
                     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                     int(last["id"])),
                )
                st.success("Handover updated.")
                st.cache_data.clear()
                st.rerun()
    else:
        comments = st.text_area(
            "Comments",
            height=140,
            placeholder=(
                "— Key issues encountered during this shift\n"
                "— Any pending actions for the next shift\n"
                "— Equipment to watch / recurring faults\n"
                "— Safety observations\n"
                "— Anything else the incoming lead needs to know"
            ),
            key="ho_comments",
        )
        if st.button("📋 Submit Handover", key="ho_submit_btn"):
            execute(
                "INSERT INTO shift_handovers (record_date, shift, submitted_by, full_name, comments) "
                "VALUES (?,?,?,?,?)",
                (day_str, shift, username, full_name, comments.strip() or None),
            )
            st.success("✅ Handover submitted. The incoming shift lead will see your notes.")
            st.cache_data.clear()
            st.rerun()

    # ══════════════════════════════════════════════════════════════════════════
    # PREVIOUS SHIFT'S HANDOVER (incoming brief)
    # ══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    section_header("Incoming brief — previous shift's handover")

    prev_shift = _prev_shift(shift)
    # Previous shift may be on the previous production day (e.g. Night → Morning)
    if prev_shift == SHIFTS[2]:  # Night shift is the one before Morning
        prev_day = str(day - timedelta(days=1))
    else:
        prev_day = day_str

    prev_handovers = read_sql(
        "SELECT full_name, comments, submitted_at FROM shift_handovers "
        "WHERE record_date=? AND shift=? ORDER BY submitted_at DESC",
        params=[prev_day, prev_shift],
    )

    if prev_handovers.empty:
        st.info(f"No handover was submitted for the {prev_shift.split('(')[0].strip()} shift.")
    else:
        for _, h in prev_handovers.iterrows():
            submitted_time = str(h.get("submitted_at", ""))[:16]
            shift_short    = prev_shift.split("(")[0].strip()
            comments_text  = h.get("comments") or "_No comments left._"
            st.markdown(
                "<div style='background:var(--surface2);border:1px solid var(--border);"
                "border-left:4px solid var(--manager);border-radius:10px;"
                "padding:16px 20px;margin-bottom:10px'>"
                "<div style='display:flex;justify-content:space-between;align-items:center;"
                "margin-bottom:10px'>"
                "<div>"
                "<span style='font-family:Space Mono,monospace;font-size:.75rem;"
                "color:var(--manager);font-weight:700'>%s SHIFT HANDOVER</span>"
                "<span style='font-size:.75rem;color:var(--muted);margin-left:10px'>by %s</span>"
                "</div>"
                "<span style='font-size:.7rem;color:var(--muted)'>%s</span>"
                "</div>"
                "<div style='font-size:.88rem;color:var(--text);white-space:pre-wrap;"
                "line-height:1.7'>%s</div>"
                "</div>" % (
                    shift_short.upper(),
                    h.get("full_name", ""),
                    submitted_time,
                    comments_text,
                ),
                unsafe_allow_html=True,
            )
