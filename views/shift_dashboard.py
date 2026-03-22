"""
views/shift_dashboard.py — Shift Dashboard
-------------------------------------------
Closed runs are filtered by the selected date/shift.
Open (active) runs are fetched with NO date filter so overnight
runs that started on a previous day remain visible to the next shift.
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime

from config import read_sql
from data.reference import SHIFTS
from components.ui import efficiency, eff_color, kpi_card, section_header, calc_oee, oee_badge, oee_color


def render():
    st.markdown("# 📊 Shift Dashboard")

    cd1, cd2 = st.columns([1, 2])
    with cd1:
        dash_date = st.date_input("View Date", value=date.today())
    with cd2:
        dash_shift = st.selectbox("Filter by Shift", ["All Shifts"] + SHIFTS)

    sf_prod  = "" if dash_shift == "All Shifts" else f" AND shift='{dash_shift}'"
    sf_fault = "" if dash_shift == "All Shifts" else f" AND shift='{dash_shift}'"

    # ── Closed runs — filtered by date (and optionally shift) ─────────────────
    closed = read_sql(
        f"SELECT * FROM production_runs "
        f"WHERE record_date=? AND status='closed'{sf_prod} "
        f"ORDER BY line_number, run_start",
        params=[str(dash_date)],
    )

    # ── Open runs — NO date filter so overnight runs always appear ─────────────
    open_query = (
        "SELECT * FROM production_runs WHERE status='open'"
        + (f" AND shift='{dash_shift}'" if dash_shift != "All Shifts" else "")
        + " ORDER BY line_number, run_start"
    )
    open_ = read_sql(open_query)

    # Faults for the selected date (for closed run linking + unlinked display)
    fault_df = read_sql(
        f"SELECT * FROM fault_records WHERE record_date=?{sf_fault} ORDER BY line_number",
        params=[str(dash_date)],
    )

    if closed.empty and open_.empty:
        st.warning("No runs found for this date/shift.")
        return

    # ── KPIs ──────────────────────────────────────────────────────────────────
    tp  = int(closed["packs_produced"].sum()) if not closed.empty else 0
    tt  = int(closed["packs_target"].sum())   if not closed.empty else 0
    ov  = efficiency(tp, tt)
    tdt = int(fault_df["downtime_minutes"].sum()) if not fault_df.empty else 0
    tfc = len(fault_df)
    unlinked_ct = int(fault_df["production_run_id"].isna().sum()) if not fault_df.empty else 0

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1: kpi_card(f"{len(open_)}",  "Active Runs",        "warn" if not open_.empty else "")
    with k2: kpi_card(f"{tp:,}",        "Cases Produced")
    with k3: kpi_card(f"{ov}%",         "Overall Efficiency",  "warn" if ov < 85 else "")
    with k4: kpi_card(tfc,              "Total Faults",        "danger" if tfc > 5 else "warn" if tfc > 2 else "")
    with k5: kpi_card(f"{tdt} min",     "Total Downtime",      "warn" if tdt > 60 else "")

    if unlinked_ct > 0:
        st.markdown(
            f"<div style='background:#ffcc0010;border:1px solid var(--warn);border-radius:8px;"
            f"padding:10px 16px;margin-bottom:12px'>"
            f"<span style='font-size:.78rem;color:var(--warn);font-family:Space Mono,monospace;"
            f"text-transform:uppercase'>"
            f"⚠️ {unlinked_ct} unlinked fault(s) — attach them when closing a run"
            f"</span></div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ── Open / active runs ────────────────────────────────────────────────────
    if not open_.empty:
        section_header("▶ Active Runs")
        for _, row in open_.iterrows():
            # Carryover badge — run opened on a different date
            run_date   = str(row.get("record_date", ""))[:10]
            today_str  = str(date.today())
            is_carry   = run_date and run_date != today_str
            carry_html = ""
            if is_carry:
                carry_html = (
                    "<span style='font-size:.65rem;color:var(--manager);"
                    "background:#7c6ff720;border:1px solid var(--manager);"
                    "border-radius:4px;padding:1px 7px;margin-left:6px'>"
                    "🔄 Carried over from %s</span>" % run_date
                )

            try:
                elapsed = (datetime.now() - datetime.strptime(
                    str(row.get("run_start", ""))[:19], "%Y-%m-%d %H:%M:%S"
                )).total_seconds() / 3600
                elapsed_str = "%.1fh elapsed" % elapsed
            except Exception:
                elapsed_str = ""

            shift_disp   = str(row.get("shift", "")).split("(")[0].strip()
            run_start_s  = str(row.get("run_start", "—"))[:16]
            operator_s   = row.get("operator_name") or "—"
            target_s     = "{:,}".format(int(row.get("packs_target") or 0))
            line_no      = int(row.get("line_number") or 0)
            prod_name    = row.get("product_name") or ""
            flavor_s     = row.get("flavor") or ""
            pack_s       = row.get("pack_size") or ""
            pkg_s        = row.get("packaging") or ""

            card = (
                "<div style='background:#00e5a008;border:1px solid var(--accent);"
                "border-radius:12px;padding:14px 20px;margin-bottom:8px;"
                "position:relative;overflow:hidden'>"
                "<div style='position:absolute;top:0;left:0;width:4px;height:100%%;"
                "background:var(--accent)'></div>"
                "<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap'>"
                "<span class='line-badge'>LINE %d</span>"
                "<span style='font-size:.9rem;font-weight:500'>%s %s &middot; %s %s</span>"
                "%s"
                "<span style='margin-left:auto;font-family:Space Mono,monospace;"
                "font-size:.72rem;font-weight:700;color:var(--accent)'>▶ RUNNING</span>"
                "</div>"
                "<div style='display:flex;gap:24px;font-size:.78rem;color:var(--muted);flex-wrap:wrap'>"
                "<span>Shift: %s</span>"
                "<span>Started: %s</span>"
                "<span style='color:var(--accent)'>%s</span>"
                "<span>Target: %s cases</span>"
                "<span>Operator: %s</span>"
                "</div>"
                "</div>"
            ) % (
                line_no, prod_name, flavor_s, pack_s, pkg_s,
                carry_html,
                shift_disp, run_start_s, elapsed_str, target_s, operator_s,
            )
            st.markdown(card, unsafe_allow_html=True)

    # ── Closed runs ───────────────────────────────────────────────────────────
    if not closed.empty:
        section_header("✅ Completed Runs")
        for _, row in closed.iterrows():
            e   = efficiency(int(row.get("packs_produced") or 0), int(row.get("packs_target") or 0))
            col = eff_color(e)
            rid = row.get("id")
            lf  = fault_df[fault_df["production_run_id"] == rid] if (rid is not None and not fault_df.empty) else pd.DataFrame()
            fdt = int(lf["downtime_minutes"].sum()) if not lf.empty else 0
            fc2 = len(lf)

            import math as _math
            _to_float = lambda v, d: d if (v is None or (isinstance(v, float) and _math.isnan(v))) else float(v)
            _to_int   = lambda v:    0 if (v is None or (isinstance(v, float) and _math.isnan(v))) else int(v)
            actual_hrs   = _to_float(row.get("actual_time_hrs"), 0.0)
            plan_hrs_r   = _to_float(row.get("plan_time_hrs"),  8.0)
            rejected_r   = _to_int(row.get("packs_rejected"))
            shift_disp   = str(row.get("shift", "")).split("(")[0].strip()
            run_start_s  = str(row.get("run_start", ""))[:16]
            run_end_s    = str(row.get("run_end",   ""))[:16]
            prod_name    = row.get("product_name") or ""
            flavor_s     = row.get("flavor")       or ""
            pack_s       = row.get("pack_size")    or ""
            pkg_s        = row.get("packaging")    or ""
            line_no      = int(row.get("line_number") or 0)
            produced     = int(row.get("packs_produced") or 0)
            target       = int(row.get("packs_target")   or 0)
            oee_r        = calc_oee(plan_hrs_r, actual_hrs, produced, target, rejected_r)
            handover     = row.get("handover_note") or ""

            # Cross-shift badge
            closed_shift = str(row.get("closed_shift") or "").split("(")[0].strip()
            cross_html   = ""
            if closed_shift and closed_shift != shift_disp:
                cross_html = (
                    "<span style='font-size:.65rem;color:var(--manager);"
                    "background:#7c6ff720;border:1px solid var(--manager);"
                    "border-radius:4px;padding:1px 7px;margin-left:6px'>"
                    "🔄 %s → %s</span>" % (shift_disp, closed_shift)
                )

            fdt_col = "var(--red)" if fdt > 30 else ("var(--warn)" if fdt > 0 else "var(--accent)")
            fc2_col = "var(--red)" if fc2 > 2  else ("var(--warn)" if fc2 > 0 else "var(--accent)")
            handover_html = (
                "<div style='margin-top:8px;font-size:.75rem;color:var(--muted)'>"
                "<b style='color:var(--text)'>Handover:</b> %s</div>" % handover
            ) if handover else ""

            card = (
                "<div class='metric-card' style='padding:14px 20px'>"
                "<div style='display:flex;align-items:center;gap:10px;margin-bottom:8px;flex-wrap:wrap'>"
                "<span class='line-badge'>LINE %d</span>"
                "<span style='font-size:.9rem;font-weight:500'>%s %s &middot; %s %s</span>"
                "<span style='color:var(--muted);font-size:.78rem'>%s</span>"
                "%s"
                "<span style='margin-left:auto;font-size:.7rem;color:var(--muted)'>%s → %s</span>"
                "</div>"
                "<div style='display:flex;gap:20px;margin-bottom:8px;flex-wrap:wrap'>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.2rem;color:%s'>%s%%</div>"
                "<div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Efficiency</div></div>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.2rem;color:var(--text)'>%s</div>"
                "<div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Produced</div></div>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.2rem;color:var(--muted)'>%s</div>"
                "<div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Target</div></div>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.2rem;color:var(--text)'>%.2fh</div>"
                "<div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Actual Time</div></div>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.2rem;color:%s'>%d min</div>"
                "<div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Downtime</div></div>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.2rem;color:%s'>%d</div>"
                "<div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Faults</div></div>"
                "</div>"
                "<div style='height:5px;background:var(--border);border-radius:3px'>"
                "<div style='height:5px;background:%s;border-radius:3px;width:%d%%'></div></div>"
                "%s"
                "</div>"
            ) % (
                line_no, prod_name, flavor_s, pack_s, pkg_s,
                shift_disp, cross_html,
                run_start_s, run_end_s,
                col, e,
                "{:,}".format(produced),
                "{:,}".format(target),
                actual_hrs,
                fdt_col, fdt,
                fc2_col, fc2,
                col, min(e, 100),
                handover_html,
            )
            st.markdown(card + oee_badge(oee_r), unsafe_allow_html=True)

            if not lf.empty:
                cols_lf = [c for c in ["fault_time","fault_machine","fault_detail","downtime_minutes","reported_by"] if c in lf.columns]
                with st.expander(f"  ↳ {fc2} fault(s) — {fdt} min downtime"):
                    st.dataframe(
                        lf[cols_lf].rename(columns={
                            "fault_time": "Time", "fault_machine": "Machine",
                            "fault_detail": "Detail", "downtime_minutes": "Downtime (min)",
                            "reported_by": "Reported By",
                        }), use_container_width=True, hide_index=True,
                    )

    # ── Unlinked faults ───────────────────────────────────────────────────────
    unlinked = fault_df[fault_df["production_run_id"].isna()] if not fault_df.empty else pd.DataFrame()
    if not unlinked.empty:
        st.markdown("---")
        section_header("⚠️ Unlinked Faults — not yet attached to a run")
        cols_ul = [c for c in ["line_number","fault_time","fault_machine","fault_detail","downtime_minutes","reported_by"] if c in unlinked.columns]
        st.dataframe(
            unlinked[cols_ul].rename(columns={
                "line_number": "Line", "fault_time": "Time",
                "fault_machine": "Machine", "fault_detail": "Detail",
                "downtime_minutes": "Downtime (min)", "reported_by": "Reported By",
            }), use_container_width=True, hide_index=True,
        )