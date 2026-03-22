"""
views/manager_overview.py — Manager Overview (5 tabs)
All data loaded defensively — every column access is guarded.
Auto-refresh every 60 seconds on the main summary.
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta

from config import read_sql
from data.reference import LINES, SHIFTS, FAULT_MACHINES
from components.ui import efficiency, eff_color, kpi_card, alert_banner, build_report, section_header, calc_oee, oee_badge, oee_color


def _safe(row, col, default=""):
    """Safely get a column value from a Series row."""
    try:
        val = row[col]
        return val if (val is not None and pd.notna(val)) else default
    except (KeyError, TypeError):
        return default


def _safe_int(row, col, default=0):
    try:
        val = row[col]
        if val is None: return default
        import math
        if isinstance(val, float) and math.isnan(val): return default
        return int(val)
    except (KeyError, TypeError, ValueError):
        return default


def _safe_float(row, col, default=0.0):
    try:
        val = row[col]
        if val is None: return default
        import math
        if isinstance(val, float) and math.isnan(val): return default
        return float(val)
    except (KeyError, TypeError, ValueError):
        return default


def render():
    st.markdown("# 🏭 Production Manager Overview")
    section_header("Plant-wide visibility \u2022 alerts \u2022 trends \u2022 reports")

    # ── Auto-refresh control ──────────────────────────────────────────────────
    col_r1, col_r2 = st.columns([3, 1])
    with col_r2:
        auto_refresh = st.toggle("Auto-refresh (60s)", value=False, key="mgr_refresh")
    if auto_refresh:
        import time
        refresh_placeholder = st.empty()
        refresh_placeholder.markdown(
            "<div style='font-size:.72rem;color:var(--muted);text-align:right'>"
            f"Last updated: {datetime.now().strftime('%H:%M:%S')}</div>",
            unsafe_allow_html=True,
        )
        time.sleep(60)
        st.rerun()

    # ── Load all data ─────────────────────────────────────────────────────────
    all_prod   = read_sql("SELECT * FROM production_runs")
    all_faults = read_sql("SELECT * FROM fault_records")

    if all_prod.empty and all_faults.empty:
        st.warning("No production data available yet.")
        return

    if not all_prod.empty:
        all_prod["record_date"] = pd.to_datetime(all_prod["record_date"])
    if not all_faults.empty:
        all_faults["record_date"] = pd.to_datetime(all_faults["record_date"])

    today_str   = str(date.today())
    closed_prod = all_prod[all_prod["status"] == "closed"].copy() if not all_prod.empty else pd.DataFrame()
    open_prod   = all_prod[all_prod["status"] == "open"].copy()   if not all_prod.empty else pd.DataFrame()

    if not closed_prod.empty:
        closed_prod["efficiency"] = closed_prod.apply(
            lambda r: efficiency(_safe_int(r, "packs_produced"), _safe_int(r, "packs_target")), axis=1
        )

    # ── Open runs banner ──────────────────────────────────────────────────────
    open_today = open_prod[open_prod["record_date"] == today_str] if not open_prod.empty else pd.DataFrame()
    if not open_today.empty:
        st.markdown("### \u25b6\ufe0f Currently Running")
        cols = st.columns(min(len(open_today), 4))
        for i, (_, r) in enumerate(open_today.iterrows()):
            try:
                elapsed = (datetime.now() - datetime.strptime(str(r.get("run_start",""))[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
                elapsed_str = f"{elapsed:.1f}h"
            except Exception:
                elapsed_str = "—"
            line_no    = _safe_int(r, "line_number")
            prod_name  = _safe(r, "product_name")
            flavor     = _safe(r, "flavor")
            shift_disp = str(_safe(r, "shift")).split("(")[0].strip()
            with cols[i % 4]:
                st.markdown(
                    f"<div style='background:#00e5a012;border:1px solid var(--accent);"
                    f"border-radius:8px;padding:10px 14px;margin-bottom:8px'>"
                    f"<div style='font-family:Space Mono,monospace;font-size:.7rem;color:var(--accent)'>"
                    f"&#9654; LINE {line_no}</div>"
                    f"<div style='font-size:.85rem;font-weight:500;margin-top:4px'>"
                    f"{prod_name} {flavor}</div>"
                    f"<div style='font-size:.7rem;color:var(--muted);margin-top:4px'>"
                    f"{shift_disp} &middot; {elapsed_str} elapsed</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # ── Low efficiency alerts ─────────────────────────────────────────────────
    today_closed = closed_prod[closed_prod["record_date"] == today_str] if not closed_prod.empty else pd.DataFrame()
    if not today_closed.empty:
        low_eff = today_closed[today_closed["efficiency"] < 70]
        if not low_eff.empty:
            st.markdown("### \U0001f6a8 Low Efficiency Alerts \u2014 Today")
            for _, r in low_eff.iterrows():
                alert_banner(
                    _safe_int(r, "line_number"),
                    f"{_safe(r,'product_name')} {_safe(r,'flavor')} {_safe(r,'pack_size')} \u2014 "
                    f"Efficiency <b style='color:var(--red)'>{_safe(r,'efficiency')}%</b> | "
                    f"{_safe_int(r,'packs_produced'):,} of {_safe_int(r,'packs_target'):,} cases | "
                    f"{str(_safe(r,'shift')).split('(')[0].strip()}",
                )

    # ── Today KPIs ────────────────────────────────────────────────────────────
    st.markdown("### Today's Plant Summary")
    tp  = int(today_closed["packs_produced"].sum()) if not today_closed.empty else 0
    tt  = int(today_closed["packs_target"].sum())   if not today_closed.empty else 0
    te  = efficiency(tp, tt)

    faults_today = all_faults[all_faults["record_date"] == today_str] if not all_faults.empty else pd.DataFrame()
    tdt = int(faults_today["downtime_minutes"].sum()) if not faults_today.empty else 0
    tfc = len(faults_today)
    unlinked_cnt = int(faults_today["production_run_id"].isna().sum()) if not faults_today.empty else 0

    # Plant-wide OEE for today (aggregate across all closed runs)
    if not today_closed.empty:
        _plan  = float(today_closed["plan_time_hrs"].fillna(8).sum())
        _act   = float(today_closed["actual_time_hrs"].fillna(0).sum())
        _prod  = int(today_closed["packs_produced"].fillna(0).sum())
        _tgt   = int(today_closed["packs_target"].fillna(0).sum())
        _rej   = int(today_closed["packs_rejected"].fillna(0).sum()) if "packs_rejected" in today_closed.columns else 0
        plant_oee = calc_oee(_plan, _act, _prod, _tgt, _rej)
    else:
        plant_oee = dict(oee=0.0, availability=0.0, performance=0.0, quality=0.0)

    lines_done = len(today_closed["line_number"].unique()) if not today_closed.empty else 0
    _kpis = [
        (f"{len(open_today)}/8",  "Lines Running",   "var(--accent)"),
        (f"{lines_done}/8",       "Lines Done",      "var(--manager)"),
        (f"{tp:,}",               "Cases Produced",  "var(--accent)" if te >= 85 else "var(--warn)"),
        (f"{te}%",                "Plant Efficiency","var(--accent)" if te >= 85 else ("var(--warn)" if te >= 70 else "var(--red)")),
        (str(tfc),                "Faults Today",    "var(--red)" if tfc > 5 else ("var(--warn)" if tfc > 2 else "var(--accent)")),
        (str(unlinked_cnt),       "Unlinked Faults", "var(--warn)" if unlinked_cnt > 0 else "var(--accent)"),
    ]
    kpi_cols = st.columns(6)
    for col, (val, label, color) in zip(kpi_cols, _kpis):
        with col:
            st.markdown(
                f"<div style='background:var(--surface);border:1px solid var(--border);"
                f"border-radius:10px;padding:14px 16px;text-align:center;min-height:80px;"
                f"display:flex;flex-direction:column;justify-content:center'>"
                f"<div style='font-family:Space Mono,monospace;font-size:1.3rem;font-weight:700;"
                f"color:{color};line-height:1.1;word-break:break-all'>{val}</div>"
                f"<div style='font-size:0.62rem;color:var(--muted);text-transform:uppercase;"
                f"letter-spacing:.8px;margin-top:5px'>{label}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # Plant OEE summary bar
    if plant_oee["oee"] > 0:
        oee_col = oee_color(plant_oee["oee"])
        oee_bar = (
            "<br> <div style='background:var(--surface);border:1px solid var(--border);"
            "border-radius:10px;padding:14px 20px;margin-bottom:16px;"
            "display:flex;gap:32px;align-items:center;flex-wrap:wrap'>"
            "<div style='font-family:Space Mono,monospace;font-size:.65rem;"
            "color:var(--muted);text-transform:uppercase;letter-spacing:1px;"
            "margin-right:8px'>Plant OEE — Today</div>"
            "<div style='text-align:center'>"
            "<div style='font-family:Space Mono,monospace;font-size:1.6rem;"
            "font-weight:700;color:%s'>%s%%</div>"
            "<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase'>OEE</div></div>"
            "<div style='text-align:center'>"
            "<div style='font-family:Space Mono,monospace;font-size:1rem;color:var(--text)'>%s%%</div>"
            "<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase'>Availability</div></div>"
            "<div style='text-align:center'>"
            "<div style='font-family:Space Mono,monospace;font-size:1rem;color:var(--text)'>%s%%</div>"
            "<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase'>Performance</div></div>"
            "<div style='text-align:center'>"
            "<div style='font-family:Space Mono,monospace;font-size:1rem;color:var(--text)'>%s%%</div>"
            "<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase'>Quality</div></div>"
            "</div>"
        ) % (
            oee_col, plant_oee["oee"],
            plant_oee["availability"], plant_oee["performance"], plant_oee["quality"],
        )
        st.markdown(oee_bar, unsafe_allow_html=True)

    st.markdown("---")
    t1, t2, t3, t4, t5 = st.tabs([
        "\U0001f4e1 All Lines", "\U0001f504 Shift Comparison",
        "\U0001f4c8 Weekly Trends", "\U0001f527 Fault Analysis", "\U0001f4cb Production Report",
    ])

    # ── Tab 1: All Lines ──────────────────────────────────────────────────────
    with t1:
        st.markdown("#### All Lines \u2014 Live & Completed")
        filter_date = st.date_input("Date", value=date.today(), key="mgr_date")
        date_str    = str(filter_date)

        all_runs_day = read_sql(
            "SELECT * FROM production_runs WHERE record_date=? ORDER BY line_number, run_start",
            params=[date_str],
        )
        df_f = all_faults[all_faults["record_date"] == date_str].copy() if not all_faults.empty else pd.DataFrame()

        unlinked_day = read_sql(
            "SELECT line_number, fault_time, fault_machine, fault_detail, "
            "downtime_minutes, reported_by "
            "FROM fault_records "
            "WHERE record_date=? AND production_run_id IS NULL "
            "ORDER BY line_number, fault_time",
            params=[date_str],
        )

        for ln in LINES:
            lp          = all_runs_day[all_runs_day["line_number"] == ln] if not all_runs_day.empty else pd.DataFrame()
            lf_unlinked = unlinked_day[unlinked_day["line_number"] == ln] if not unlinked_day.empty else pd.DataFrame()

            # Active runs on this line
            lp_open   = lp[lp["status"] == "open"]   if not lp.empty else pd.DataFrame()
            lp_closed = lp[lp["status"] == "closed"] if not lp.empty else pd.DataFrame()

            if lp.empty and lf_unlinked.empty:
                st.markdown(
                    "<div class='metric-card' style='padding:12px 20px;opacity:.3'>"
                    "<span class='line-badge'>LINE %d</span>"
                    "<span style='color:var(--muted);font-size:.82rem;margin-left:12px'>No activity</span>"
                    "</div>" % ln,
                    unsafe_allow_html=True,
                )
                continue

            # ── Active run cards (no grouping — show directly) ────────────────
            for _, row in lp_open.iterrows():
                opened_shift = str(row.get("shift", "")).split("(")[0].strip()
                run_start_s  = str(row.get("run_start", ""))[:16]
                prod_name_s  = _safe(row, "product_name")
                flavor_s     = _safe(row, "flavor")
                pack_s       = _safe(row, "pack_size")
                pkg_s        = _safe(row, "packaging")
                tgt          = _safe_int(row, "packs_target")
                try:
                    elapsed = (datetime.now() - datetime.strptime(run_start_s, "%Y-%m-%d %H:%M")).total_seconds() / 3600
                    elapsed_str = "%.1fh elapsed" % elapsed
                except Exception:
                    elapsed_str = "\u2014"
                st.markdown(
                    "<div style='background:#00e5a012;border:1px solid var(--accent);"
                    "border-radius:12px;padding:14px 20px;margin-bottom:8px;"
                    "position:relative;overflow:hidden'>"
                    "<div style='position:absolute;top:0;left:0;width:4px;height:100%%;background:var(--accent)'></div>"
                    "<div style='display:flex;align-items:center;gap:10px;margin-bottom:6px;flex-wrap:wrap'>"
                    "<span class='line-badge'>LINE %d</span>"
                    "<span style='font-size:.9rem;font-weight:500'>%s %s &middot; %s %s</span>"
                    "<span style='color:var(--muted);font-size:.75rem'>%s</span>"
                    "<span style='margin-left:auto;font-family:Space Mono,monospace;"
                    "font-size:.72rem;font-weight:700;color:var(--accent)'>\u25b6 RUNNING</span>"
                    "</div>"
                    "<div style='display:flex;gap:20px;font-size:.78rem;color:var(--muted);flex-wrap:wrap'>"
                    "<span>Started: %s</span>"
                    "<span style='color:var(--accent)'>%s</span>"
                    "<span>Target: %s cases</span>"
                    "</div></div>" % (
                        ln, prod_name_s, flavor_s, pack_s, pkg_s,
                        opened_shift, run_start_s, elapsed_str,
                        "{:,}".format(tgt),
                    ),
                    unsafe_allow_html=True,
                )

            # ── Closed runs — line summary + per-run expanders ────────────────
            if not lp_closed.empty:
                ln_produced   = int(lp_closed["packs_produced"].sum())
                ln_target     = int(lp_closed["packs_target"].sum())
                ln_eff        = efficiency(ln_produced, ln_target)
                ln_col        = eff_color(ln_eff)
                ln_run_ids    = lp_closed["id"].tolist()
                lf_all        = df_f[df_f["production_run_id"].isin(ln_run_ids)] if not df_f.empty and "production_run_id" in df_f.columns else pd.DataFrame()
                ln_fdt        = int(lf_all["downtime_minutes"].sum()) if not lf_all.empty else 0
                ln_fc         = len(lf_all)
                ln_run_hrs    = sum(_safe_float(r, "actual_time_hrs") for _, r in lp_closed.iterrows())
                ln_plan_hrs   = sum(_safe_float(r, "plan_time_hrs") or 8.0 for _, r in lp_closed.iterrows())
                ln_rejected   = sum(_safe_int(r, "packs_rejected") for _, r in lp_closed.iterrows())
                ln_oee        = calc_oee(ln_plan_hrs, ln_run_hrs, ln_produced, ln_target, ln_rejected)
                n_runs        = len(lp_closed)
                fdt_col       = "var(--red)" if ln_fdt > 30 else ("var(--warn)" if ln_fdt > 0 else "var(--accent)")
                fc_col        = "var(--red)" if ln_fc > 5   else ("var(--warn)" if ln_fc > 0 else "var(--accent)")
                ln_run_str    = "%.2fh" % ln_run_hrs if ln_run_hrs > 0 else "\u2014"

                # Line summary card
                st.markdown(
                    "<div style='background:var(--surface);border:1px solid var(--border);"
                    "border-radius:12px;padding:16px 20px;margin-bottom:4px;"
                    "position:relative;overflow:hidden'>"
                    "<div style='position:absolute;top:0;left:0;width:4px;height:100%%;background:%s'></div>"
                    "<div style='display:flex;align-items:center;gap:12px;margin-bottom:12px'>"
                    "<span class='line-badge'>LINE %d</span>"
                    "<span style='font-size:.78rem;color:var(--muted)'>%d run(s) completed%s</span>"
                    "</div>"
                    "<div style='display:flex;gap:24px;flex-wrap:wrap;margin-bottom:10px'>"
                    "<div><div style='font-family:Space Mono,monospace;font-size:1.4rem;color:%s'>%s%%</div>"
                    "<div style='font-size:.62rem;color:var(--muted);text-transform:uppercase'>Line Efficiency</div></div>"
                    "<div><div style='font-family:Space Mono,monospace;font-size:1.4rem;color:var(--text)'>%s</div>"
                    "<div style='font-size:.62rem;color:var(--muted);text-transform:uppercase'>Total Produced</div></div>"
                    "<div><div style='font-family:Space Mono,monospace;font-size:1.4rem;color:var(--muted)'>%s</div>"
                    "<div style='font-size:.62rem;color:var(--muted);text-transform:uppercase'>Total Target</div></div>"
                    "<div><div style='font-family:Space Mono,monospace;font-size:1.4rem;color:var(--text)'>%s</div>"
                    "<div style='font-size:.62rem;color:var(--muted);text-transform:uppercase'>Total Run Time</div></div>"
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
                        " (+ 1 running)" if not lp_open.empty else "",
                        ln_col, ln_eff,
                        "{:,}".format(ln_produced),
                        "{:,}".format(ln_target),
                        ln_run_str,
                        fdt_col, ln_fdt,
                        fc_col,  ln_fc,
                        ln_col,  min(ln_eff, 100),
                    ),
                    unsafe_allow_html=True,
                )
                st.markdown(oee_badge(ln_oee), unsafe_allow_html=True)

                # Per-run expanders
                for _, row in lp_closed.iterrows():
                    rid          = row.get("id")
                    prod_name_s  = _safe(row, "product_name")
                    flavor_s     = _safe(row, "flavor")
                    pack_s       = _safe(row, "pack_size")
                    pkg_s        = _safe(row, "packaging")
                    opened_shift = str(row.get("shift", "")).split("(")[0].strip()
                    closed_shift = str(row.get("closed_shift", "") or "").split("(")[0].strip()
                    cross_tag    = " \U0001f504 %s\u2192%s" % (opened_shift, closed_shift) if (closed_shift and closed_shift != opened_shift) else ""
                    run_start_s  = str(row.get("run_start", ""))[:16]
                    run_end_s    = str(row.get("run_end",   ""))[:16]
                    produced     = _safe_int(row, "packs_produced")
                    target       = _safe_int(row, "packs_target")
                    actual_hrs   = _safe_float(row, "actual_time_hrs")
                    plan_hrs_m   = _safe_float(row, "plan_time_hrs") or 8.0
                    rejected_m   = _safe_int(row, "packs_rejected")
                    handover     = _safe(row, "handover_note")
                    e            = efficiency(produced, target)
                    col          = eff_color(e)
                    oee_m        = calc_oee(plan_hrs_m, actual_hrs, produced, target, rejected_m)

                    rf  = df_f[df_f["production_run_id"] == rid] if (rid is not None and not df_f.empty and "production_run_id" in df_f.columns) else pd.DataFrame()
                    fdt = int(rf["downtime_minutes"].sum()) if not rf.empty else 0
                    fc2 = len(rf)

                    exp_label = "%s %s · %s %s · %s%s | %s%% | %s cases | %s\u2192%s" % (
                        prod_name_s, flavor_s, pack_s, pkg_s,
                        opened_shift, cross_tag, e,
                        "{:,}".format(produced),
                        run_start_s, run_end_s,
                    )
                    with st.expander(exp_label):
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
                        st.markdown(oee_badge(oee_m), unsafe_allow_html=True)
                        if handover:
                            st.markdown(
                                "<div style='font-size:.78rem;color:var(--muted);margin-top:6px'>"
                                "<b style='color:var(--text)'>Handover:</b> %s</div>" % handover,
                                unsafe_allow_html=True,
                            )
                        if not rf.empty:
                            cols_rf = [c for c in ["fault_time","fault_machine","fault_detail","downtime_minutes","reported_by"] if c in rf.columns]
                            st.dataframe(rf[cols_rf].rename(columns={
                                "fault_time":"Time","fault_machine":"Machine",
                                "fault_detail":"Detail","downtime_minutes":"Downtime (min)",
                                "reported_by":"Reported By",
                            }), use_container_width=True, hide_index=True)
                        else:
                            st.caption("No faults logged for this run.")

            # Unlinked faults for this line
            if not lf_unlinked.empty:
                ul_dt = int(lf_unlinked["downtime_minutes"].sum())
                with st.expander("  \u26a0\ufe0f Line %d \u2014 %d unlinked fault(s) \u00b7 %d min" % (ln, len(lf_unlinked), ul_dt)):
                    st.dataframe(
                        lf_unlinked.drop(columns=["line_number"], errors="ignore").rename(columns={
                            "fault_time":"Time","fault_machine":"Machine",
                            "fault_detail":"Detail","downtime_minutes":"Downtime (min)",
                            "reported_by":"Reported By",
                        }), use_container_width=True, hide_index=True,
                    )
            st.markdown("<div style='margin-bottom:8px'></div>", unsafe_allow_html=True)

        if not unlinked_day.empty:
            st.markdown("---")
            section_header("\u26a0\ufe0f Unlinked Faults \u2014 not attached to any run")
            st.dataframe(
                unlinked_day.rename(columns={
                    "line_number":"Line","fault_time":"Time","fault_machine":"Machine",
                    "fault_detail":"Detail","downtime_minutes":"Downtime (min)","reported_by":"Reported By",
                }), use_container_width=True, hide_index=True,
            )

    # ── Tab 2: Shift Comparison ───────────────────────────────────────────────
    with t2:
        st.markdown("#### Shift Comparison")
        sc1, sc2 = st.columns(2)
        with sc1: s_from = st.date_input("From", value=date.today()-timedelta(days=7), key="sc_from")
        with sc2: s_to   = st.date_input("To",   value=date.today(),                   key="sc_to")

        if closed_prod.empty:
            st.info("No closed runs yet.")
        else:
            mask = (closed_prod["record_date"] >= str(s_from)) & (closed_prod["record_date"] <= str(s_to))
            sp   = closed_prod[mask].copy()
            if sp.empty:
                st.info("No data in this range.")
            else:
                sp["shift_short"] = sp["shift"].str.split("(").str[0].str.strip()
                grp = sp.groupby("shift_short").agg(
                    total_packs=("packs_produced","sum"),
                    total_target=("packs_target","sum"),
                    records=("id","count"),
                ).reset_index()
                grp["efficiency"] = grp.apply(
                    lambda r: efficiency(int(r.total_packs or 0), int(r.total_target or 0)), axis=1
                )
                for _, r in grp.iterrows():
                    col = eff_color(r["efficiency"])
                    st.markdown(f"""
                    <div class='metric-card' style='padding:16px 20px;margin-bottom:10px'>
                        <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px'>
                            <span style='font-family:Space Mono,monospace;font-weight:700'>{r["shift_short"]}</span>
                            <span style='font-family:Space Mono,monospace;font-size:1.3rem;color:{col}'>{r["efficiency"]}%</span>
                        </div>
                        <div style='display:flex;gap:28px;margin-bottom:10px'>
                            <div><div style='font-size:1.1rem;font-weight:600;color:var(--text)'>{int(r["total_packs"] or 0):,}</div>
                                 <div style='font-size:.7rem;color:var(--muted);text-transform:uppercase'>Cases</div></div>
                            <div><div style='font-size:1.1rem;font-weight:600;color:var(--muted)'>{int(r["total_target"] or 0):,}</div>
                                 <div style='font-size:.7rem;color:var(--muted);text-transform:uppercase'>Target</div></div>
                            <div><div style='font-size:1.1rem;font-weight:600;color:var(--text)'>{int(r["records"])}</div>
                                 <div style='font-size:.7rem;color:var(--muted);text-transform:uppercase'>Runs</div></div>
                        </div>
                        <div style='height:6px;background:var(--border);border-radius:3px'>
                            <div style='height:6px;background:{col};border-radius:3px;width:{min(r["efficiency"],100)}%'></div>
                        </div>
                    </div>""", unsafe_allow_html=True)

                if not all_faults.empty:
                    fmask = (all_faults["record_date"] >= str(s_from)) & (all_faults["record_date"] <= str(s_to))
                    sf2   = all_faults[fmask].copy()
                    if not sf2.empty and "shift" in sf2.columns:
                        sf2["shift_short"] = sf2["shift"].str.split("(").str[0].str.strip()
                        fgrp = sf2.groupby("shift_short").agg(
                            faults=("id","count"), downtime=("downtime_minutes","sum")
                        ).reset_index()
                        st.markdown("**Fault & Downtime by Shift**")
                        st.dataframe(fgrp.rename(columns={
                            "shift_short":"Shift","faults":"Faults","downtime":"Total Downtime (min)"
                        }), use_container_width=True, hide_index=True)

    # ── Tab 3: Weekly Trends ──────────────────────────────────────────────────
    with t3:
        st.markdown("#### Weekly Production Trend (last 14 days)")
        if closed_prod.empty:
            st.info("No closed runs yet.")
        else:
            cutoff = pd.Timestamp(date.today()) - pd.Timedelta(days=14)
            wp     = closed_prod[closed_prod["record_date"] >= cutoff].copy()
            if wp.empty:
                st.info("Not enough data yet.")
            else:
                daily = wp.groupby("record_date").agg(
                    packs=("packs_produced","sum"), target=("packs_target","sum")
                ).reset_index()
                daily["eff"]      = daily.apply(lambda r: efficiency(int(r.packs or 0), int(r.target or 0)), axis=1)
                daily["date_str"] = daily["record_date"].dt.strftime("%b %d")
                max_packs = int(daily["packs"].max()) or 1

                st.markdown("<div class='chart-card'><div class='chart-title'>Daily Cases Produced</div>", unsafe_allow_html=True)
                bars = "<div style='display:flex;align-items:flex-end;gap:6px;height:120px'>"
                for _, r in daily.iterrows():
                    h = int((r["packs"] / max_packs) * 100)
                    c = eff_color(r["eff"])
                    bars += (
                        f"<div style='display:flex;flex-direction:column;align-items:center;flex:1'>"
                        f"<div style='font-size:.6rem;color:var(--muted);margin-bottom:4px'>{int(r['packs'])//1000}k</div>"
                        f"<div style='background:{c};width:100%;height:{h}%;border-radius:3px 3px 0 0;min-height:4px'></div>"
                        f"<div style='font-size:.58rem;color:var(--muted);margin-top:4px;"
                        f"writing-mode:vertical-lr;transform:rotate(180deg)'>{r['date_str']}</div></div>"
                    )
                bars += "</div></div>"
                st.markdown(bars, unsafe_allow_html=True)

                st.markdown("<br><div class='chart-card'><div class='chart-title'>Daily Efficiency %</div>", unsafe_allow_html=True)
                eb = "<div style='display:flex;align-items:flex-end;gap:6px;height:120px'>"
                for _, r in daily.iterrows():
                    c = eff_color(r["eff"])
                    eb += (
                        f"<div style='display:flex;flex-direction:column;align-items:center;flex:1'>"
                        f"<div style='font-size:.6rem;color:var(--muted);margin-bottom:4px'>{int(r['eff'])}%</div>"
                        f"<div style='background:{c};width:100%;height:{int(r['eff'])}%;"
                        f"border-radius:3px 3px 0 0;min-height:4px'></div>"
                        f"<div style='font-size:.58rem;color:var(--muted);margin-top:4px;"
                        f"writing-mode:vertical-lr;transform:rotate(180deg)'>{r['date_str']}</div></div>"
                    )
                eb += "</div></div>"
                st.markdown(eb, unsafe_allow_html=True)
                st.dataframe(
                    daily[["date_str","packs","target","eff"]].rename(columns={
                        "date_str":"Date","packs":"Cases","target":"Target","eff":"Efficiency %"
                    }), use_container_width=True, hide_index=True,
                )

    # ── Tab 4: Fault Analysis ─────────────────────────────────────────────────
    with t4:
        st.markdown("#### Fault Analysis")
        if all_faults.empty:
            st.info("No fault data yet.")
        else:
            fa1, fa2 = st.columns(2)
            with fa1: fa_from = st.date_input("From", value=date.today()-timedelta(days=30), key="fa_from")
            with fa2: fa_to   = st.date_input("To",   value=date.today(),                    key="fa_to")

            fmask2 = (all_faults["record_date"] >= str(fa_from)) & (all_faults["record_date"] <= str(fa_to))
            fa_df  = all_faults[fmask2].copy()

            if fa_df.empty:
                st.info("No fault data in this range.")
            else:
                linked_ct   = int(fa_df["production_run_id"].notna().sum()) if "production_run_id" in fa_df.columns else 0
                unlinked_ct = len(fa_df) - linked_ct
                lc1, lc2 = st.columns(2)
                with lc1:
                    st.markdown(f"""<div class='metric-card' style='padding:14px 20px'>
                        <div class='metric-value' style='color:var(--accent)'>{linked_ct}</div>
                        <div class='metric-label'>Faults linked to a run</div></div>""",
                        unsafe_allow_html=True)
                with lc2:
                    st.markdown(f"""<div class='metric-card {"warn" if unlinked_ct > 0 else ""}' style='padding:14px 20px'>
                        <div class='metric-value' style='color:{"var(--warn)" if unlinked_ct > 0 else "var(--accent)"}'>{unlinked_ct}</div>
                        <div class='metric-label'>Unlinked faults</div></div>""",
                        unsafe_allow_html=True)

                if "fault_machine" in fa_df.columns:
                    st.markdown("**Top Fault Areas**")
                    ft_grp = fa_df.groupby("fault_machine").agg(
                        count=("id","count"), total_dt=("downtime_minutes","sum")
                    ).sort_values("count", ascending=False).reset_index()
                    max_fc = int(ft_grp["count"].max()) or 1
                    for _, r in ft_grp.iterrows():
                        bw = int((r["count"] / max_fc) * 100)
                        st.markdown(f"""
                        <div style='margin-bottom:10px'>
                            <div style='display:flex;justify-content:space-between;margin-bottom:4px'>
                                <span style='font-size:.85rem'>{r["fault_machine"]}</span>
                                <span style='font-family:Space Mono,monospace;font-size:.8rem;color:var(--accent2)'>
                                    {int(r["count"])} faults | {int(r["total_dt"])} min
                                </span>
                            </div>
                            <div style='height:5px;background:var(--border);border-radius:3px'>
                                <div style='height:5px;background:var(--accent2);border-radius:3px;width:{bw}%'></div>
                            </div>
                        </div>""", unsafe_allow_html=True)

                if "line_number" in fa_df.columns:
                    st.markdown("<br>**Faults by Line**")
                    fl_grp = fa_df.groupby("line_number").agg(
                        count=("id","count"), total_dt=("downtime_minutes","sum")
                    ).reset_index()
                    fl_grp["line_number"] = fl_grp["line_number"].apply(lambda x: f"Line {x}")
                    st.dataframe(fl_grp.rename(columns={
                        "line_number":"Line","count":"Faults","total_dt":"Downtime (min)"
                    }), use_container_width=True, hide_index=True)

                st.download_button(
                    "\u2b07\ufe0f Export Fault Data",
                    fa_df.to_csv(index=False).encode(),
                    "fault_analysis.csv", "text/csv",
                )

    # ── Tab 5: Production Report ──────────────────────────────────────────────
    with t5:
        st.markdown("#### Production Report")
        section_header("Line efficiency summary \u2014 matches plant report format")

        rp1, rp2, rp3 = st.columns(3)
        with rp1: r_from  = st.date_input("From",  value=date.today(), key="r_from")
        with rp2: r_to    = st.date_input("To",    value=date.today(), key="r_to")
        with rp3: r_shift = st.selectbox("Shift", ["All Shifts"] + SHIFTS, key="r_shift")

        if closed_prod.empty:
            st.info("No closed runs to report on yet.")
        else:
            pmask   = (closed_prod["record_date"] >= str(r_from)) & (closed_prod["record_date"] <= str(r_to))
            r_prod  = closed_prod[pmask].copy()

            r_faults = pd.DataFrame()
            if not all_faults.empty:
                fmaskr   = (all_faults["record_date"] >= str(r_from)) & (all_faults["record_date"] <= str(r_to))
                r_faults = all_faults[fmaskr].copy()

            if r_shift != "All Shifts":
                r_prod   = r_prod[r_prod["shift"] == r_shift]
                if not r_faults.empty and "shift" in r_faults.columns:
                    r_faults = r_faults[r_faults["shift"] == r_shift]

            period_lbl = f"{r_from} to {r_to}" if r_from != r_to else str(r_from)
            shift_lbl  = r_shift if r_shift != "All Shifts" else "All Shifts"
            build_report(r_prod, r_faults, title=f"Production Report \u00b7 {period_lbl} \u00b7 {shift_lbl}")