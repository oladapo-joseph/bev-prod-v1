"""
views/shift_dashboard.py — Shift Dashboard
-------------------------------------------
Layout:
  ▶ Active Runs   — one card per open run, grouped by line
  ✅ Completed    — LINE level summary card (aggregated), then per-run
                    expanders inside showing individual product + faults

Hierarchy:
  LINE N  ← aggregate: total cases, efficiency, downtime, OEE
    └── [expander] Product A · Shift · Run time     ← individual run
          └── fault table
    └── [expander] Product B · Shift · Run time
          └── fault table
"""

import streamlit as st
import pandas as pd
import math
from datetime import date, datetime

from auth import current_shift
from config import read_sql
from data.reference import LINES, SHIFTS, HOURLY_TARGETS
from components.ui import (
    efficiency, eff_color, kpi_card, section_header,
    calc_oee, oee_badge,
)

# ── NaN-safe helpers ──────────────────────────────────────────────────────────
def _f(v, d=0.0):
    return d if (v is None or (isinstance(v, float) and math.isnan(v))) else float(v)

def _i(v, d=0):
    return d if (v is None or (isinstance(v, float) and math.isnan(v))) else int(v)

def _s(v, d=""):
    return d if v is None else str(v)


def render():
    st.markdown("# 📊 Shift Dashboard")

    SHIFT_SHORT = ["Morning", "Afternoon", "Night"]
    _cur_short  = current_shift().split("(")[0].strip()
    _shift_idx  = SHIFT_SHORT.index(_cur_short) + 1 if _cur_short in SHIFT_SHORT else 0

    cd1, cd2 = st.columns([1, 2])
    with cd1:
        dash_date = st.date_input("View Date", value=date.today())
    with cd2:
        dash_shift = st.selectbox("Filter by Shift", ["All Shifts"] + SHIFT_SHORT, index=_shift_idx)

    date_str = str(dash_date)

    # Closed runs — parameterized, no f-string injection
    if dash_shift == "All Shifts":
        closed = read_sql(
            "SELECT * FROM production_runs WHERE record_date=? AND status='closed' ORDER BY line_number, run_start",
            params=[date_str],
        )
    else:
        closed = read_sql(
            "SELECT * FROM production_runs WHERE record_date=? AND status='closed' ORDER BY line_number, run_start",
            params=[date_str],
        )
        if not closed.empty:
            closed = closed[closed["shift"].str.split("(").str[0].str.strip() == dash_shift]

    # Open runs — filter by selected date so carryover runs from other days are labelled, not silently included
    if dash_shift == "All Shifts":
        open_ = read_sql(
            "SELECT * FROM production_runs WHERE status='open' ORDER BY line_number, run_start"
        )
    else:
        open_ = read_sql(
            "SELECT * FROM production_runs WHERE status='open' ORDER BY line_number, run_start"
        )
        if not open_.empty:
            open_ = open_[open_["shift"].str.split("(").str[0].str.strip() == dash_shift]

    # All faults for the selected date — parameterized
    if dash_shift == "All Shifts":
        fault_df = read_sql(
            "SELECT * FROM fault_records WHERE record_date=? ORDER BY line_number",
            params=[date_str],
        )
    else:
        fault_df = read_sql(
            "SELECT * FROM fault_records WHERE record_date=? ORDER BY line_number",
            params=[date_str],
        )
        if not fault_df.empty:
            fault_df = fault_df[fault_df["shift"].str.split("(").str[0].str.strip() == dash_shift]

    if closed.empty and open_.empty:
        st.warning("No runs found for this date/shift.")
        return

    # ── Plant-level KPIs ──────────────────────────────────────────────────────
    tp  = int(closed["packs_produced"].sum()) if not closed.empty else 0
    tt  = int(closed["packs_target"].sum())   if not closed.empty else 0
    tdt = int(fault_df["downtime_minutes"].sum()) if not fault_df.empty else 0
    tfc = len(fault_df)
    unlinked_ct = int(fault_df["production_run_id"].isna().sum()) if not fault_df.empty else 0

    # Plant OEE — aggregate across all closed runs
    if not closed.empty:
        _act_hrs  = float(closed["actual_time_hrs"].fillna(0).sum())
        _rej      = int(closed["packs_rejected"].fillna(0).sum())
        _down_hrs = tdt / 60.0
        _plant_oee = calc_oee(_act_hrs, _act_hrs, tp, tt, _rej, _down_hrs)
    else:
        _plant_oee = {"oee": 0.0}
    ov = _plant_oee["oee"]

    k1, k2, k3, k4, k5 = st.columns(5)
    with k1: kpi_card(f"{len(open_)}",  "Active Runs",    "warn" if not open_.empty else "")
    with k2: kpi_card(f"{tp:,}",        "Cases Produced")
    with k3: kpi_card(f"{ov}%",         "OEE",            "danger" if ov < 65 else ("warn" if ov < 85 else ""))
    with k4: kpi_card(tfc,              "Total Faults",   "danger" if tfc >= 10 else "warn" if tfc > 0 else "")
    with k5: kpi_card(f"{tdt} min",     "Total Downtime", "warn" if tdt > 60 else "")

    if unlinked_ct > 0:
        st.markdown(
            "<div style='background:#ffcc0010;border:1px solid var(--warn);border-radius:8px;"
            "padding:10px 16px;margin-bottom:12px'>"
            "<span style='font-size:.78rem;color:var(--warn);font-family:Space Mono,monospace;"
            "text-transform:uppercase'>"
            "⚠️ %d unlinked fault(s) — attach them when closing a run"
            "</span></div>" % unlinked_ct,
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # ══════════════════════════════════════════════════════════════════════════
    # ACTIVE RUNS
    # ══════════════════════════════════════════════════════════════════════════
    if not open_.empty:
        section_header("▶ Active Runs")
        for ln in LINES:
            lp_open = open_[open_["line_number"] == ln]
            if lp_open.empty:
                continue
            for _, row in lp_open.iterrows():
                run_date   = _s(row.get("record_date"))[:10]
                is_carry   = run_date and run_date != str(date.today())
                carry_html = (
                    "<span style='font-size:.65rem;color:var(--manager);"
                    "background:#7c6ff720;border:1px solid var(--manager);"
                    "border-radius:4px;padding:1px 7px;margin-left:6px'>"
                    "🔄 Carried over from %s</span>" % run_date
                ) if is_carry else ""
                try:
                    elapsed = (datetime.now() - datetime.strptime(
                        _s(row.get("run_start"))[:19], "%Y-%m-%d %H:%M:%S"
                    )).total_seconds() / 3600
                    elapsed_str = "%.1fh elapsed" % elapsed
                except Exception:
                    elapsed     = 0.0
                    elapsed_str = ""

                # Live estimated target based on elapsed time
                try:
                    cph = HOURLY_TARGETS[_s(row.get("product_name"))][_s(row.get("pack_size"))][_s(row.get("packaging"))]
                    live_target = "{:,}".format(max(1, round(cph * max(elapsed, 0.1))))
                    target_label = "Est. Target"
                except KeyError:
                    live_target  = "{:,}".format(_i(row.get("packs_target")))
                    target_label = "Target"

                st.markdown(
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
                    "<span>%s: %s cases</span>"
                    "<span>Operator: %s</span>"
                    "</div></div>" % (
                        _i(row.get("line_number")),
                        _s(row.get("product_name")), _s(row.get("flavor")),
                        _s(row.get("pack_size")),    _s(row.get("packaging")),
                        carry_html,
                        _s(row.get("shift")).split("(")[0].strip(),
                        _s(row.get("run_start"))[:16],
                        elapsed_str,
                        target_label, live_target,
                        _s(row.get("operator_name")) or "—",
                    ),
                    unsafe_allow_html=True,
                )

    # ══════════════════════════════════════════════════════════════════════════
    # COMPLETED RUNS — grouped by line
    # ══════════════════════════════════════════════════════════════════════════
    if not closed.empty:
        section_header("✅ Completed Lines")

        for ln in LINES:
            lp = closed[closed["line_number"] == ln]
            if lp.empty:
                continue

            # ── Line-level aggregates ─────────────────────────────────────────
            ln_produced = int(lp["packs_produced"].sum())
            ln_target   = int(lp["packs_target"].sum())
            ln_eff      = efficiency(ln_produced, ln_target)
            ln_col      = eff_color(ln_eff)

            # Faults across all runs on this line
            ln_run_ids  = lp["id"].tolist()
            lf_all      = fault_df[fault_df["production_run_id"].isin(ln_run_ids)] if not fault_df.empty else pd.DataFrame()
            ln_fdt      = int(lf_all["downtime_minutes"].sum()) if not lf_all.empty else 0
            ln_fc       = len(lf_all)

            # OEE aggregated across runs
            ln_plan_hrs   = sum(_f(r.get("plan_time_hrs"), 8.0) for _, r in lp.iterrows())
            ln_actual_hrs = sum(_f(r.get("actual_time_hrs"), 0.0) for _, r in lp.iterrows())
            ln_rejected   = sum(_i(r.get("packs_rejected")) for _, r in lp.iterrows())
            ln_oee        = calc_oee(ln_plan_hrs, ln_actual_hrs, ln_produced, ln_target, ln_rejected, ln_fdt / 60.0)

            fdt_col = "var(--red)" if ln_fdt > 30 else ("var(--warn)" if ln_fdt > 0 else "var(--accent)")
            fc_col  = "var(--red)" if ln_fc > 5   else ("var(--warn)" if ln_fc > 0 else "var(--accent)")
            n_runs  = len(lp)

            # ── Line summary card ─────────────────────────────────────────────
            st.markdown(
                "<div style='background:var(--surface);border:1px solid var(--border);"
                "border-radius:12px;padding:16px 20px;margin-bottom:4px;"
                "position:relative;overflow:hidden'>"
                "<div style='position:absolute;top:0;left:0;width:4px;height:100%%;"
                "background:%s'></div>"
                "<div style='display:flex;align-items:center;gap:12px;margin-bottom:12px'>"
                "<span class='line-badge'>LINE %d</span>"
                "<span style='font-size:.78rem;color:var(--muted)'>%d run(s) completed</span>"
                "</div>"
                "<div style='display:flex;gap:24px;flex-wrap:wrap;margin-bottom:10px'>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.4rem;color:%s'>%s%%</div>"
                "<div style='font-size:.62rem;color:var(--muted);text-transform:uppercase'>Line Efficiency</div></div>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.4rem;color:var(--text)'>%s</div>"
                "<div style='font-size:.62rem;color:var(--muted);text-transform:uppercase'>Total Produced</div></div>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.4rem;color:var(--muted)'>%s</div>"
                "<div style='font-size:.62rem;color:var(--muted);text-transform:uppercase'>Total Target</div></div>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.4rem;color:%s'>%d min</div>"
                "<div style='font-size:.62rem;color:var(--muted);text-transform:uppercase'>Total Downtime</div></div>"
                "<div><div style='font-family:Space Mono,monospace;font-size:1.4rem;color:%s'>%d</div>"
                "<div style='font-size:.62rem;color:var(--muted);text-transform:uppercase'>Total Faults</div></div>"
                "</div>"
                "<div style='height:6px;background:var(--border);border-radius:3px'>"
                "<div style='height:6px;background:%s;border-radius:3px;width:%d%%'></div></div>"
                "</div>" % (
                    ln_col,
                    ln, n_runs,
                    ln_col, ln_eff,
                    "{:,}".format(ln_produced),
                    "{:,}".format(ln_target),
                    fdt_col, ln_fdt,
                    fc_col,  ln_fc,
                    ln_col,  min(ln_eff, 100),
                ),
                unsafe_allow_html=True,
            )

            # OEE badge for the line
            st.markdown(oee_badge(ln_oee), unsafe_allow_html=True)

            # ── Per-run expanders ─────────────────────────────────────────────
            for _, row in lp.iterrows():
                rid          = row.get("id")
                prod_name    = _s(row.get("product_name"))
                flavor_s     = _s(row.get("flavor"))
                pack_s       = _s(row.get("pack_size"))
                pkg_s        = _s(row.get("packaging"))
                shift_disp   = _s(row.get("shift")).split("(")[0].strip()
                run_start_s  = _s(row.get("run_start"))[:16]
                run_end_s    = _s(row.get("run_end"))[:16]
                produced     = _i(row.get("packs_produced"))
                target       = _i(row.get("packs_target"))
                actual_hrs   = _f(row.get("actual_time_hrs"))
                plan_hrs_r   = _f(row.get("plan_time_hrs"), 8.0)
                rejected_r   = _i(row.get("packs_rejected"))
                handover     = _s(row.get("handover_note"))
                e            = efficiency(produced, target)
                col          = eff_color(e)
                oee_r        = calc_oee(plan_hrs_r, actual_hrs, produced, target, rejected_r, fdt / 60.0)

                # Faults for this specific run
                lf = fault_df[fault_df["production_run_id"] == rid] if (rid is not None and not fault_df.empty) else pd.DataFrame()
                fdt = int(lf["downtime_minutes"].sum()) if not lf.empty else 0
                fc2 = len(lf)

                closed_shift = _s(row.get("closed_shift")).split("(")[0].strip()
                cross_tag = ""
                if closed_shift and closed_shift != shift_disp:
                    cross_tag = " 🔄 %s→%s" % (shift_disp, closed_shift)

                expander_label = (
                    "%s %s · %s %s · %s%s | %s%% | %s cases | %s→%s"
                ) % (
                    prod_name, flavor_s, pack_s, pkg_s,
                    shift_disp, cross_tag,
                    e,
                    "{:,}".format(produced),
                    run_start_s, run_end_s,
                )

                with st.expander(expander_label):
                    # Run stats row
                    fdt_col2 = "var(--red)" if fdt > 30 else ("var(--warn)" if fdt > 0 else "var(--accent)")
                    fc2_col  = "var(--red)" if fc2 > 2  else ("var(--warn)" if fc2 > 0 else "var(--accent)")
                    st.markdown(
                        "<div style='display:flex;gap:20px;flex-wrap:wrap;margin-bottom:10px'>"
                        "<div><div style='font-family:Space Mono,monospace;font-size:1.1rem;color:%s'>%s%%</div>"
                        "<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase'>Efficiency</div></div>"
                        "<div><div style='font-family:Space Mono,monospace;font-size:1.1rem;color:var(--text)'>%s</div>"
                        "<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase'>Produced</div></div>"
                        "<div><div style='font-family:Space Mono,monospace;font-size:1.1rem;color:var(--muted)'>%s</div>"
                        "<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase'>Target</div></div>"
                        "<div><div style='font-family:Space Mono,monospace;font-size:1.1rem;color:var(--text)'>%.2fh</div>"
                        "<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase'>Run Time</div></div>"
                        "<div><div style='font-family:Space Mono,monospace;font-size:1.1rem;color:%s'>%d min</div>"
                        "<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase'>Downtime</div></div>"
                        "<div><div style='font-family:Space Mono,monospace;font-size:1.1rem;color:%s'>%d</div>"
                        "<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase'>Faults</div></div>"
                        "</div>" % (
                            col, e,
                            "{:,}".format(produced),
                            "{:,}".format(target),
                            actual_hrs,
                            fdt_col2, fdt,
                            fc2_col,  fc2,
                        ),
                        unsafe_allow_html=True,
                    )
                    st.markdown(oee_badge(oee_r), unsafe_allow_html=True)

                    if handover:
                        st.markdown(
                            "<div style='font-size:.78rem;color:var(--muted);margin-top:8px'>"
                            "<b style='color:var(--text)'>Handover:</b> %s</div>" % handover,
                            unsafe_allow_html=True,
                        )

                    # Fault table
                    if not lf.empty:
                        st.markdown(
                            "<div style='font-size:.72rem;color:var(--muted);"
                            "text-transform:uppercase;letter-spacing:1px;margin-top:12px;"
                            "margin-bottom:6px'>Faults</div>",
                            unsafe_allow_html=True,
                        )
                        cols_lf = [c for c in ["fault_time","fault_machine","fault_detail",
                                               "downtime_minutes","reported_by"] if c in lf.columns]
                        st.dataframe(
                            lf[cols_lf].rename(columns={
                                "fault_time":"Time", "fault_machine":"Machine",
                                "fault_detail":"Detail", "downtime_minutes":"Downtime (min)",
                                "reported_by":"Reported By",
                            }), use_container_width=True, hide_index=True,
                        )
                    else:
                        st.caption("No faults logged for this run.")

            st.markdown("<div style='margin-bottom:16px'></div>", unsafe_allow_html=True)

    # ── Unlinked faults ───────────────────────────────────────────────────────
    unlinked = fault_df[fault_df["production_run_id"].isna()] if not fault_df.empty else pd.DataFrame()
    if not unlinked.empty:
        st.markdown("---")
        section_header("⚠️ Unlinked Faults — not yet attached to a run")
        cols_ul = [c for c in ["line_number","fault_time","fault_machine",
                               "fault_detail","downtime_minutes","reported_by"] if c in unlinked.columns]
        st.dataframe(
            unlinked[cols_ul].rename(columns={
                "line_number":"Line", "fault_time":"Time",
                "fault_machine":"Machine", "fault_detail":"Detail",
                "downtime_minutes":"Downtime (min)", "reported_by":"Reported By",
            }), use_container_width=True, hide_index=True,
        )