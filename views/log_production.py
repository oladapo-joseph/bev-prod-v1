"""
views/log_production.py — Open a Run / Close a Run
----------------------------------------------------
Flow:
  1. Shift lead opens a run — selects line, shift, product, operator.
     Only ONE open run per line is allowed at a time.
  2. Open runs are visible as live cards.
  3. To close — pick the run, enter packs produced, handover note,
     pick unlinked faults to attach. Captures closed_shift so
     cross-shift runs are tracked correctly.
"""

import streamlit as st
from datetime import date, datetime

from auth import production_day, current_shift
from config import execute, read_sql
from data.reference import (LINES, SHIFTS, PRODUCTS, PRODUCT_NAMES, PRODUCT_NAME_TO_ID,
                             get_target, get_run_target, get_line_litres,
                             _cases_per_hour_from_litres, HOURLY_TARGETS)
from components.ui import efficiency, eff_color, section_header, calc_oee, oee_badge

_PH = (
    "— Select Shift —", "— Select Line —", "— Select Product —",
    "— Select Flavor —", "— Select Pack Size —", "— Select Packaging —",
    "— Select Product first —", None,
)

def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _hrs_between(start_str: str, end_str: str) -> float:
    fmt = "%Y-%m-%d %H:%M:%S"
    try:
        delta = datetime.strptime(end_str, fmt) - datetime.strptime(start_str, fmt)
        return round(delta.total_seconds() / 3600, 2)
    except Exception:
        return 0.0

# current_shift() imported from auth


def render(username: str):
    st.markdown("# 📋 Production Runs")
    tab_open, tab_close = st.tabs(["▶️  Open New Run", "✅  Close / Submit Run"])

    # ── TAB 1: OPEN A RUN ─────────────────────────────────────────────────────
    with tab_open:
        section_header("Start a new production run on a line")

        if "open_run_key" not in st.session_state:
            st.session_state["open_run_key"] = 0
        ok = st.session_state["open_run_key"]

        _cur_shift = current_shift()
        _shift_idx = SHIFTS.index(_cur_shift) + 1 if _cur_shift in SHIFTS else 0

        c1, c2, c3 = st.columns(3)
        with c1:
            st.text_input("Date", value=str(production_day()), disabled=True, key=f"or_date_{ok}")
        with c2:
            shift = st.selectbox("Shift", ["— Select Shift —"] + SHIFTS, index=_shift_idx, key=f"or_shift_{ok}")
        with c3:
            line = st.selectbox(
                "Line Number", ["— Select Line —"] + LINES,
                format_func=lambda x: f"Line {x}" if isinstance(x, int) else x,
                key=f"or_line_{ok}",
            )

        st.markdown("---")

        c4, c5, c6 = st.columns(3)
        with c4:
            product_name = st.selectbox("Product", ["— Select Product —"] + PRODUCT_NAMES, key=f"or_prod_{ok}")

        flavor = pack_size = packaging = None
        operator = ""

        if product_name not in _PH:
            pid_   = PRODUCT_NAME_TO_ID[product_name]
            pdata_ = PRODUCTS[pid_]
            with c5:
                flavor = st.selectbox("Flavor", ["— Select Flavor —"] + pdata_["flavors"], key=f"or_flav_{ok}")
            with c6:
                pack_size = st.selectbox("Pack Size", ["— Select Pack Size —"] + pdata_["packSizes"], key=f"or_size_{ok}")
            cA, cB = st.columns(2)
            with cA:
                packaging = st.selectbox("Packaging", ["— Select Packaging —"] + pdata_["packagings"], key=f"or_pkg_{ok}")
            with cB:
                operator = st.text_input("Operator / Supervisor", placeholder="Enter name", key=f"or_op_{ok}")
        else:
            with c5:
                st.selectbox("Flavor",    ["— Select Product first —"], disabled=True, key=f"or_flav_{ok}")
            with c6:
                st.selectbox("Pack Size", ["— Select Product first —"], disabled=True, key=f"or_size_{ok}")
            cA, cB = st.columns(2)
            with cA:
                st.selectbox("Packaging", ["— Select Product first —"], disabled=True, key=f"or_pkg_{ok}")
            with cB:
                operator = st.text_input("Operator / Supervisor", placeholder="Enter name", key=f"or_op_{ok}")

        # Hourly rate preview (target is calculated at close time based on actual run duration)
        auto_target  = 0
        hourly_rate  = 0.0
        if product_name not in _PH and pack_size not in _PH and packaging not in _PH:
            auto_target = get_target(product_name, pack_size, packaging)
            if isinstance(line, int):
                lph = get_line_litres(line)
                if lph > 0:
                    hourly_rate = _cases_per_hour_from_litres(lph, pack_size, packaging)
            if not hourly_rate:
                try:
                    hourly_rate = HOURLY_TARGETS[product_name][pack_size][packaging]
                except KeyError:
                    hourly_rate = 0.0

        if hourly_rate:
            st.markdown(f"""
            <div class='target-preview'>
                <span style='color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:1px'>
                    Ideal Rate
                </span>
                <span style='float:right;font-size:1.1rem;color:var(--accent)'>{hourly_rate:,.0f} cases / hr</span>
            </div>""", unsafe_allow_html=True)
            st.caption("Target cases will be calculated automatically when the run is closed based on actual run time.")
            st.markdown("")

        # ── Check if this line already has an open run ────────────────────────
        line_blocked   = False
        active_on_line = None
        if isinstance(line, int):
            check = read_sql(
                "SELECT id, product_name, flavor, pack_size, run_start "
                "FROM production_runs WHERE line_number=? AND status='open'",
                params=[line],
            )
            if not check.empty:
                line_blocked = True
                r = check.iloc[0]
                active_on_line = (
                    f"{r['product_name']} {r.get('flavor','') or ''} "
                    f"{r.get('pack_size','') or ''} — started {str(r['run_start'])[:16]}"
                )

        if line_blocked:
            st.error(
                f"⛔ Line {line} already has an open run: **{active_on_line}**  \n"
                f"Close that run first before opening a new one."
            )

        all_ok = (
            shift not in _PH and isinstance(line, int) and
            product_name not in _PH and flavor not in _PH and
            pack_size not in _PH and packaging not in _PH and
            operator.strip() != "" and auto_target > 0 and
            not line_blocked
        )

        if not all_ok and not line_blocked:
            missing = []
            if shift in _PH:               missing.append("Shift")
            if not isinstance(line, int):  missing.append("Line Number")
            if product_name in _PH:        missing.append("Product")
            if flavor in _PH:              missing.append("Flavor")
            if pack_size in _PH:           missing.append("Pack Size")
            if packaging in _PH:           missing.append("Packaging")
            if not operator.strip():       missing.append("Operator name")
            if missing:
                st.info(f"Required: {', '.join(missing)}")

        if st.button("\u25b6\ufe0f  Open Run", disabled=not all_ok, key=f"or_btn_{ok}"):
            recheck = read_sql(
                "SELECT COUNT(*) as cnt FROM production_runs WHERE line_number=? AND status='open'",
                params=[line],
            )
            if int(recheck["cnt"].iloc[0]) > 0:
                st.error(f"\u26d4 Line {line} just had a run opened. Refresh and check first.")
            else:
                execute(
                    "INSERT INTO production_runs "
                    "(record_date, shift, line_number, product_name, flavor, "
                    "pack_size, packaging, packs_target, run_start, status, "
                    "operator_name, logged_by) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (str(production_day()), shift, line, product_name, flavor,
                     pack_size, packaging, auto_target, _now_str(), "open",
                     operator.strip(), username),
                )
                st.success(
                    f"\u25b6\ufe0f Run opened \u2014 Line {line} | {product_name} {flavor} "
                    f"{pack_size} {packaging} | Target: {auto_target:,} cases"
                )
                st.session_state["open_run_key"] += 1
                st.rerun()

        # Show currently open runs
        st.markdown("---")
        section_header("Currently open runs — today")
        open_runs = read_sql(
            "SELECT id, line_number, shift, product_name, flavor, "
            "pack_size, packaging, packs_target, run_start, operator_name "
            "FROM production_runs "
            "WHERE record_date=? AND status='open' "
            "ORDER BY line_number, run_start",
            params=[str(production_day())],
        )
        if open_runs.empty:
            st.info("No open runs at the moment.")
        else:
            for _, r in open_runs.iterrows():
                try:
                    elapsed = (datetime.now() - datetime.strptime(str(r["run_start"])[:19], "%Y-%m-%d %H:%M:%S")).total_seconds() / 3600
                    elapsed_str = f"{elapsed:.1f}h elapsed"
                except Exception:
                    elapsed    = 0.0
                    elapsed_str = ""
                live_target = get_run_target(
                    r["product_name"], r.get("pack_size") or "", r.get("packaging") or "",
                    max(elapsed, 0.1), line_number=int(r["line_number"]),
                )
                lph = get_line_litres(int(r["line_number"]))
                if lph > 0:
                    cph = _cases_per_hour_from_litres(
                        lph, r.get("pack_size") or "", r.get("packaging") or ""
                    )
                else:
                    try:
                        cph = HOURLY_TARGETS[r["product_name"]][r.get("pack_size") or ""][r.get("packaging") or ""]
                    except KeyError:
                        cph = 0.0
                rate_str = f"{cph:,.0f} cases/hr" if cph else ""
                st.markdown(f"""
                <div class='metric-card' style='padding:14px 20px'>
                    <div style='display:flex;align-items:center;gap:10px;margin-bottom:6px'>
                        <span class='line-badge'>LINE {r["line_number"]}</span>
                        <span style='font-size:.9rem;font-weight:500'>
                            {r["product_name"]} {r.get("flavor","") or ""} \u00b7 {r.get("pack_size","") or ""} {r.get("packaging","") or ""}
                        </span>
                        <span style='margin-left:auto;font-family:Space Mono,monospace;font-size:.72rem;color:var(--accent)'>\u25b6 RUNNING</span>
                    </div>
                    <div style='display:flex;gap:24px;font-size:.78rem;color:var(--muted);flex-wrap:wrap'>
                        <span>Shift: {r["shift"].split("(")[0].strip()}</span>
                        <span>Started: {str(r["run_start"])[:16]}</span>
                        <span style='color:var(--accent)'>{elapsed_str}</span>
                        <span>Est. Target: {live_target:,} cases</span>
                        {f"<span>Rate: {rate_str}</span>" if rate_str else ""}
                        <span>Operator: {r.get("operator_name","—") or "—"}</span>
                    </div>
                </div>""", unsafe_allow_html=True)

    # ── TAB 2: CLOSE A RUN ────────────────────────────────────────────────────
    with tab_close:
        section_header("Close a run — enter final pack count and link faults")

        if "close_run_key" not in st.session_state:
            st.session_state["close_run_key"] = 0
        ck = st.session_state["close_run_key"]

        # Load ALL open runs (any date) so cross-shift/cross-day runs appear
        open_runs_all = read_sql(
            "SELECT id, line_number, shift, record_date, product_name, flavor, "
            "pack_size, packaging, packs_target, run_start, operator_name "
            "FROM production_runs "
            "WHERE status='open' "
            "ORDER BY line_number, run_start",
        )

        if open_runs_all.empty:
            st.info("No open runs to close.")
        else:
            run_map = {
                f"Line {r.line_number} \u2014 {r.product_name} {r.flavor or ''} "
                f"{r.pack_size or ''} {r.packaging or ''} | "
                f"Opened: {r.shift.split('(')[0].strip()} {str(r.record_date)[:10]} "
                f"@ {str(r.run_start)[:16]}": r
                for r in open_runs_all.itertuples()
            }
            selected_label = st.selectbox("Select Run to Close", list(run_map.keys()), key=f"cr_sel_{ck}")
            run = run_map[selected_label]

            # Detect cross-shift carryover
            cur_shift = current_shift()
            is_carryover = run.shift != cur_shift
            if is_carryover:
                st.markdown(
                    f"<div style='background:#7c6ff715;border:1px solid var(--manager);border-radius:8px;"
                    f"padding:10px 16px;margin-bottom:12px'>"
                    f"<span style='font-size:.78rem;color:var(--manager);font-family:Space Mono,monospace;"
                    f"text-transform:uppercase'>"
                    f"\U0001f504 Cross-shift run \u2014 opened during "
                    f"{run.shift.split('(')[0].strip()}, closing in {cur_shift.split('(')[0].strip()}"
                    f"</span></div>",
                    unsafe_allow_html=True,
                )

            st.markdown(f"""
            <div class='target-preview' style='margin-bottom:16px'>
                <div style='display:flex;justify-content:space-between;margin-bottom:8px'>
                    <span style='color:var(--muted);font-size:.7rem;text-transform:uppercase;letter-spacing:1px'>Run Summary</span>
                    <span style='font-family:Space Mono,monospace;font-size:.75rem;color:var(--accent)'>\u25b6 OPEN</span>
                </div>
                <div style='display:flex;gap:28px;flex-wrap:wrap'>
                    <div><div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Line</div>
                         <div style='font-family:Space Mono,monospace'>{run.line_number}</div></div>
                    <div><div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Product</div>
                         <div style='font-family:Space Mono,monospace'>{run.product_name} {run.flavor or ""}</div></div>
                    <div><div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Pack</div>
                         <div style='font-family:Space Mono,monospace'>{run.pack_size or ""} {run.packaging or ""}</div></div>
                    <div><div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Target</div>
                         <div style='font-family:Space Mono,monospace'>{int(run.packs_target):,}</div></div>
                    <div><div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Opened in shift</div>
                         <div style='font-family:Space Mono,monospace'>{run.shift.split("(")[0].strip()}</div></div>
                    <div><div style='font-size:.65rem;color:var(--muted);text-transform:uppercase'>Started</div>
                         <div style='font-family:Space Mono,monospace'>{str(run.run_start)[:16]}</div></div>
                </div>
            </div>""", unsafe_allow_html=True)

            cp1, cp2 = st.columns(2)
            with cp1:
                packs_produced = st.number_input(
                    "Packs Produced (cases)", min_value=0, step=1, value=0, key=f"cr_packs_{ck}"
                )
            with cp2:
                packs_rejected = st.number_input(
                    "Packs Rejected / Defective", min_value=0, step=1, value=0, key=f"cr_reject_{ck}",
                    help="Cases that failed quality checks and were not shipped"
                )

            if packs_produced > 0:
                import datetime as _dt
                try:
                    elapsed_hrs = (_dt.datetime.now() - _dt.datetime.strptime(
                        str(run.run_start)[:19], "%Y-%m-%d %H:%M:%S"
                    )).total_seconds() / 3600
                except Exception:
                    elapsed_hrs = 8.0
                plan_hrs_est  = max(elapsed_hrs, 0.1)
                live_target   = get_run_target(
                    run.product_name, run.pack_size or "", run.packaging or "",
                    plan_hrs_est, line_number=int(run.line_number),
                ) or int(run.packs_target)
                eff_ = efficiency(packs_produced, live_target)
                col_ = eff_color(eff_)
                oee_ = calc_oee(plan_hrs_est, plan_hrs_est, packs_produced,
                                live_target, packs_rejected)
                st.markdown(
                    "<div style='background:var(--surface2);border:1px solid var(--border);"
                    "border-radius:8px;padding:12px 16px;margin-bottom:12px'>"
                    "<div style='font-size:.65rem;color:var(--muted);text-transform:uppercase;"
                    "margin-bottom:6px'>Line Efficiency (simple)</div>"
                    "<div style='font-family:Space Mono,monospace;font-size:1.8rem;"
                    "font-weight:700;color:%s'>%s%%</div>"
                    "<div style='height:6px;background:var(--border);border-radius:3px;margin-top:8px'>"
                    "<div style='height:6px;background:%s;border-radius:3px;width:%d%%'></div></div>"
                    "</div>" % (col_, eff_, col_, min(eff_, 100)),
                    unsafe_allow_html=True,
                )
                st.markdown(oee_badge(oee_), unsafe_allow_html=True)

            handover = st.text_area(
                "Shift Handover Note (optional)", height=80,
                placeholder="Any issues, pending actions, or notes for the next shift\u2026",
                key=f"cr_handover_{ck}",
            )

            # Unlinked fault backfill — search by line only (not shift) to catch cross-shift faults
            st.markdown("---")
            section_header("Link unlinked faults to this run (optional)")

            unlinked = read_sql(
                "SELECT id, fault_time, fault_machine, fault_detail, shift, "
                "downtime_minutes, reported_by, created_at "
                "FROM fault_records "
                "WHERE line_number=? AND production_run_id IS NULL "
                "ORDER BY record_date, fault_time, created_at",
                params=[run.line_number],
            )

            selected_fault_ids = []
            if unlinked.empty:
                st.info("No unlinked faults for this line.")
            else:
                total_unlinked_dt = int(unlinked["downtime_minutes"].sum())
                st.markdown(
                    f"<div style='background:#ffcc0010;border:1px solid var(--warn);border-radius:8px;"
                    f"padding:10px 16px;margin-bottom:12px'>"
                    f"<span style='font-size:.75rem;color:var(--warn);font-family:Space Mono,monospace;"
                    f"text-transform:uppercase'>"
                    f"\u26a0\ufe0f {len(unlinked)} unlinked fault(s) on Line {run.line_number} \u2014 "
                    f"{total_unlinked_dt} min total downtime</span></div>",
                    unsafe_allow_html=True,
                )
                st.markdown("**Tick faults that occurred during this run:**")
                for _, f in unlinked.iterrows():
                    shift_tag   = f" [{f.get('shift','')[:3] if f.get('shift') else ''}]" if is_carryover else ""
                    fault_det   = f['fault_detail'] or "\u2014"
                    fault_time  = f['fault_time'] or str(f['created_at'])[:16]
                    label = (
                        f"[{fault_time}]{shift_tag} "
                        f"{f['fault_machine']} \u203a {fault_det} "
                        f"| {f['downtime_minutes']} min | {f['reported_by']}"
                    )
                    if st.checkbox(label, key=f"fault_link_{f['id']}_{ck}"):
                        selected_fault_ids.append(int(f["id"]))

            if packs_produced == 0:
                st.warning("⚠️ A run cannot be closed with zero cases produced. Enter the actual pack count before submitting.")
            if packs_rejected > packs_produced > 0:
                st.error("⛔ Packs rejected cannot exceed packs produced.")

            st.markdown("")
            close_ready = packs_produced > 0 and packs_rejected <= packs_produced

            confirmed = False
            if close_ready:
                st.markdown("---")
                with st.expander("📋 Review before submitting", expanded=True):
                    import datetime as _dt2
                    try:
                        _elapsed = (_dt2.datetime.now() - _dt2.datetime.strptime(
                            str(run.run_start)[:19], "%Y-%m-%d %H:%M:%S"
                        )).total_seconds() / 3600
                    except Exception:
                        _elapsed = 0.0
                    _preview_target = get_run_target(
                        run.product_name, run.pack_size or "", run.packaging or "",
                        max(_elapsed, 0.1), line_number=int(run.line_number),
                    ) or int(run.packs_target)
                    _prev_eff = efficiency(packs_produced, _preview_target)
                    _opening_target = int(run.packs_target)
                    _target_change  = f" _(was {_opening_target:,} at open)_" if _preview_target != _opening_target else ""
                    st.markdown(f"""
                    | Field | Value |
                    |---|---|
                    | **Line** | {run.line_number} |
                    | **Product** | {run.product_name} {run.flavor or ""} · {run.pack_size or ""} {run.packaging or ""} |
                    | **Packs Produced** | {packs_produced:,} cases |
                    | **Packs Rejected** | {packs_rejected:,} cases |
                    | **Target (run time)** | {_preview_target:,} cases{_target_change} |
                    | **Est. Efficiency** | {_prev_eff}% |
                    | **Faults to link** | {len(selected_fault_ids)} |
                    | **Handover note** | {handover.strip() or "—"} |
                    """)
                    confirmed = st.checkbox(
                        "I have reviewed the above and confirm this is correct",
                        key=f"cr_confirm_{ck}"
                    )

            if st.button("\u2705  Close & Submit Run", disabled=not (close_ready and confirmed), key=f"cr_btn_{ck}"):
                if packs_produced == 0:
                    st.error("Cannot close a run with zero cases produced.")
                    st.stop()
                run_end    = _now_str()
                actual_hrs = _hrs_between(str(run.run_start), run_end)

                already_linked = read_sql(
                    "SELECT SUM(downtime_minutes) as dt FROM fault_records WHERE production_run_id=?",
                    params=[int(run.id)],
                )
                already_dt = float(already_linked["dt"].iloc[0] or 0) if not already_linked.empty else 0.0

                newly_linked_dt = float(
                    unlinked[unlinked["id"].isin(selected_fault_ids)]["downtime_minutes"].sum()
                ) if selected_fault_ids and not unlinked.empty else 0.0

                down_hrs  = round((already_dt + newly_linked_dt) / 60, 2)
                plan_hrs  = round(actual_hrs, 2)

                # Recalculate target based on actual run duration
                run_target = get_run_target(
                    run.product_name,
                    run.pack_size or "",
                    run.packaging or "",
                    actual_hrs,
                    line_number=int(run.line_number),
                )

                execute(
                    "UPDATE production_runs SET "
                    "packs_produced=?, packs_rejected=?, packs_target=?, run_end=?, "
                    "status='closed', closed_shift=?, "
                    "actual_time_hrs=?, down_time_hrs=?, plan_time_hrs=?, handover_note=? "
                    "WHERE id=?",
                    (packs_produced, packs_rejected, run_target, run_end, cur_shift,
                     actual_hrs, down_hrs, plan_hrs, handover.strip() or None, int(run.id)),
                )

                for fid in selected_fault_ids:
                    execute(
                        "UPDATE fault_records SET production_run_id=? WHERE id=?",
                        (int(run.id), fid),
                    )

                eff_final = efficiency(packs_produced, run_target)
                cross_note = f" (cross-shift: {run.shift.split('(')[0].strip()} \u2192 {cur_shift.split('(')[0].strip()})" if is_carryover else ""
                st.success(
                    f"\u2705 Run closed{cross_note} \u2014 Line {run.line_number} | "
                    f"{run.product_name} {run.flavor or ''} | "
                    f"{packs_produced:,} / {run_target:,} cases target | {eff_final}% efficiency | "
                    f"{len(selected_fault_ids)} fault(s) linked"
                )
                st.session_state["close_run_key"] += 1
                st.rerun()