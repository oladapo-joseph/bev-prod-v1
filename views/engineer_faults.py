"""
views/engineer_faults.py — Engineer Fault Tracking Dashboard

Dedicated to maintenance engineers: live fault feed, Pareto analysis,
14-day downtime trends, and MTTR per machine.
"""

import streamlit as st
import pandas as pd
from datetime import timedelta
from config import read_sql
from auth import production_day, current_shift
from data.reference import LINES, SHIFTS, FAULT_MACHINES
from components.ui import kpi_card, section_header


# ── Data loaders ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def _load_today(day: str) -> pd.DataFrame:
    return read_sql(
        "SELECT * FROM fault_records WHERE record_date = ? ORDER BY fault_time DESC",
        params=[day],
    )


@st.cache_data(ttl=30)
def _load_range(date_from: str, date_to: str) -> pd.DataFrame:
    return read_sql(
        "SELECT * FROM fault_records "
        "WHERE record_date >= ? AND record_date <= ? "
        "ORDER BY record_date DESC, fault_time DESC",
        params=[date_from, date_to],
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _severity(minutes: float) -> tuple[str, str]:
    """Return (label, css-colour-var) based on downtime duration."""
    if minutes >= 60:
        return "Critical", "var(--red)"
    if minutes >= 30:
        return "High", "var(--accent2)"
    if minutes >= 10:
        return "Medium", "var(--warn)"
    return "Low", "var(--accent)"


def _short_shift(full: str) -> str:
    for s in ("Morning", "Afternoon", "Night"):
        if s.lower() in full.lower():
            return s
    return full


# ── Main render ───────────────────────────────────────────────────────────────

def render():
    st.markdown("# 🔧 Fault Dashboard")

    day = str(production_day())
    today = _load_today(day)

    # ── KPI strip ─────────────────────────────────────────────────────────────
    total_faults   = len(today)
    total_down     = int(today["downtime_minutes"].sum())     if not today.empty else 0
    lines_hit      = today["line_number"].nunique()           if not today.empty else 0
    unlinked       = int(today["production_run_id"].isna().sum()) if not today.empty else 0
    avg_mttr       = round(float(today["downtime_minutes"].mean()), 1) if not today.empty else 0.0

    # Recurring: same (line, machine) pair with more than one fault today
    if not today.empty:
        _rec = today.groupby(["line_number", "fault_machine"]).size()
        recurring_count = int((_rec > 1).sum())
    else:
        recurring_count = 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1: kpi_card(total_faults,   "Faults Today",     "danger" if total_faults >= 10 else ("warn" if total_faults > 0 else ""))
    with c2: kpi_card(f"{total_down}m", "Total Downtime",  "danger" if total_down > 120 else ("warn" if total_down > 60 else ""))
    with c3: kpi_card(lines_hit,       "Lines Affected",   "warn"   if lines_hit > 4 else "")
    with c4: kpi_card(f"{avg_mttr}m",  "Avg MTTR",         "danger" if avg_mttr > 30 else ("warn" if avg_mttr > 15 else ""))
    with c5: kpi_card(recurring_count, "Recurring Faults", "danger" if recurring_count > 0 else "")
    with c6: kpi_card(unlinked,        "Unlinked",         "warn"   if unlinked > 0 else "")

    st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

    tab_feed, tab_pareto, tab_trends, tab_mttr = st.tabs([
        "📋 Live Feed", "📊 Pareto", "📈 Trends", "⏱️ MTTR"
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 1 — LIVE FEED
    # ══════════════════════════════════════════════════════════════════════════
    with tab_feed:
        section_header(f"Today's faults — production day {day}")

        # Recurring fault alert banner
        if recurring_count > 0 and not today.empty:
            _rec_df = today.groupby(["line_number", "fault_machine"]).size().reset_index(name="count")
            _rec_df = _rec_df[_rec_df["count"] > 1].sort_values("count", ascending=False)
            parts = [f"Line {int(r.line_number)} → {r.fault_machine} ({r['count']}×)"
                     for r in _rec_df.itertuples()]
            st.markdown(
                f"<div style='background:#ff475712;border:1px solid var(--red);"
                f"border-radius:8px;padding:10px 16px;margin-bottom:14px;"
                f"font-size:0.84rem;color:var(--red);'>"
                f"⚠️ <b>Recurring faults detected:</b> {' &nbsp;|&nbsp; '.join(parts)}"
                f"</div>",
                unsafe_allow_html=True,
            )

        if today.empty:
            st.info("No faults logged for today's production day.")
        else:
            # Filters
            f1, f2, f3 = st.columns(3)
            with f1:
                fl = st.selectbox("Line", ["All Lines"] + [f"Line {i}" for i in LINES], key="ef_line")
            with f2:
                fm = st.selectbox("Machine", ["All Machines"] + FAULT_MACHINES, key="ef_machine")
            with f3:
                fs = st.selectbox("Shift", ["All Shifts", "Morning", "Afternoon", "Night"], key="ef_shift")

            df = today.copy()
            if fl != "All Lines":    df = df[df["line_number"] == int(fl.split(" ")[1])]
            if fm != "All Machines": df = df[df["fault_machine"] == fm]
            if fs != "All Shifts":   df = df[df["shift"].str.contains(fs, na=False)]

            st.caption(f"{len(df)} fault{'s' if len(df) != 1 else ''} shown")

            for _, row in df.iterrows():
                mins      = float(row.get("downtime_minutes") or 0)
                sev_lbl, sev_col = _severity(mins)
                linked    = bool(row.get("production_run_id"))
                link_txt  = f"Run #{int(row['production_run_id'])}" if linked else "Unlinked"
                link_col  = "var(--muted)" if linked else "var(--warn)"
                machine   = row.get("fault_machine") or "—"
                detail    = row.get("fault_detail")  or "—"
                reporter  = row.get("reported_by")   or "—"
                shift_lbl = _short_shift(str(row.get("shift") or ""))
                fault_t   = str(row.get("fault_time") or "")[:5]
                notes     = row.get("notes") or ""

                with st.expander(
                    f"Line {int(row['line_number'])}  ·  {machine}  ·  {detail[:50]}  "
                    f"·  {mins:.0f} min  ·  {fault_t}",
                    expanded=False,
                ):
                    r1, r2, r3, r4 = st.columns(4)
                    r1.markdown(
                        f"<div style='font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.8px'>Severity</div>"
                        f"<div style='font-family:Space Mono,monospace;font-weight:700;color:{sev_col}'>{sev_lbl}</div>",
                        unsafe_allow_html=True,
                    )
                    r2.markdown(
                        f"<div style='font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.8px'>Downtime</div>"
                        f"<div style='font-family:Space Mono,monospace;font-weight:700;color:var(--text)'>{mins:.0f} min</div>",
                        unsafe_allow_html=True,
                    )
                    r3.markdown(
                        f"<div style='font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.8px'>Shift</div>"
                        f"<div style='font-family:Space Mono,monospace;color:var(--text)'>{shift_lbl}</div>",
                        unsafe_allow_html=True,
                    )
                    r4.markdown(
                        f"<div style='font-size:.72rem;color:var(--muted);text-transform:uppercase;letter-spacing:.8px'>Run Link</div>"
                        f"<div style='font-family:Space Mono,monospace;color:{link_col}'>{link_txt}</div>",
                        unsafe_allow_html=True,
                    )
                    notes_html = f"&nbsp;·&nbsp;<b style=\"color:var(--text)\">Notes:</b> {notes}" if notes else ""
                    st.markdown(
                        f"<div style='margin-top:10px;font-size:.83rem;color:var(--muted)'>"
                        f"<b style='color:var(--text)'>Detail:</b> {detail} &nbsp;·&nbsp; "
                        f"<b style='color:var(--text)'>Reporter:</b> {reporter}"
                        f"{notes_html}"
                        f"</div>",
                        unsafe_allow_html=True,
                    )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 2 — PARETO
    # ══════════════════════════════════════════════════════════════════════════
    with tab_pareto:
        section_header("Top machines by total downtime")

        pa1, pa2 = st.columns([2, 1])
        with pa1:
            p_days = st.selectbox("Period", ["Today", "Last 7 days", "Last 30 days"], key="p_period")
        with pa2:
            p_line = st.selectbox("Line", ["All Lines"] + [f"Line {i}" for i in LINES], key="p_line")

        if p_days == "Today":
            pdf = today.copy()
        elif p_days == "Last 7 days":
            d0 = str(production_day() - timedelta(days=6))
            pdf = _load_range(d0, day)
        else:
            d0 = str(production_day() - timedelta(days=29))
            pdf = _load_range(d0, day)

        if p_line != "All Lines":
            pdf = pdf[pdf["line_number"] == int(p_line.split(" ")[1])]

        if pdf.empty:
            st.info("No fault data for the selected period.")
        else:
            pareto = (
                pdf.groupby("fault_machine")["downtime_minutes"]
                .sum()
                .reset_index()
                .rename(columns={"downtime_minutes": "Total Downtime (min)"})
                .sort_values("Total Downtime (min)", ascending=False)
            )
            pareto["Fault Count"]    = pdf.groupby("fault_machine").size().reindex(pareto["fault_machine"]).values
            pareto["Share %"]        = (pareto["Total Downtime (min)"] / pareto["Total Downtime (min)"].sum() * 100).round(1)
            pareto["Cumulative %"]   = pareto["Share %"].cumsum().round(1)
            pareto = pareto.reset_index(drop=True)

            # Bar chart
            chart_df = pareto.set_index("fault_machine")[["Total Downtime (min)"]].head(12)
            st.bar_chart(chart_df, height=280)

            # Table
            st.dataframe(
                pareto[["fault_machine", "Fault Count", "Total Downtime (min)", "Share %", "Cumulative %"]]
                .rename(columns={"fault_machine": "Machine / Area"}),
                use_container_width=True,
                hide_index=True,
            )

            total_min = int(pareto["Total Downtime (min)"].sum())
            top3_share = round(pareto["Share %"].head(3).sum(), 1)
            st.caption(
                f"Total downtime: **{total_min} min** ({total_min / 60:.1f} hrs)  ·  "
                f"Top 3 machines account for **{top3_share}%** of all downtime"
            )

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 3 — TRENDS
    # ══════════════════════════════════════════════════════════════════════════
    with tab_trends:
        section_header("Daily downtime trends")

        tf1, tf2 = st.columns(2)
        with tf1: t_from_dt = st.date_input("From", value=production_day() - timedelta(days=13), key="t_from_dt")
        with tf2: t_to_dt   = st.date_input("To",   value=production_day(),                       key="t_to_dt")

        t3a, t3b = st.columns([2, 1])
        with t3a:
            t_machine = st.selectbox(
                "Machine / Area", ["All Machines"] + FAULT_MACHINES, key="t_machine"
            )
        with t3b:
            t_line = st.selectbox("Line", ["All Lines"] + [f"Line {i}" for i in LINES], key="t_line")

        d_from = str(t_from_dt)
        d_to   = str(t_to_dt)
        tdf = _load_range(d_from, d_to)

        if t_line != "All Lines":
            tdf = tdf[tdf["line_number"] == int(t_line.split(" ")[1])]
        if t_machine != "All Machines":
            tdf = tdf[tdf["fault_machine"] == t_machine]

        if tdf.empty:
            st.info("No fault data in the last 14 days.")
        else:
            daily = (
                tdf.groupby("record_date")["downtime_minutes"]
                .sum()
                .reset_index()
                .rename(columns={"record_date": "Date", "downtime_minutes": "Downtime (min)"})
                .sort_values("Date")
            )
            daily["Fault Count"] = (
                tdf.groupby("record_date").size().reindex(daily["Date"]).values
            )
            daily = daily.set_index("Date")

            st.bar_chart(daily[["Downtime (min)"]], height=260)

            # Secondary: fault count trend
            st.markdown(
                "<div class='section-header' style='margin-top:20px'>Fault count per day</div>",
                unsafe_allow_html=True,
            )
            st.bar_chart(daily[["Fault Count"]], height=200)

            # Summary stats
            s1, s2, s3 = st.columns(3)
            s1.metric("Peak Day Downtime",  f"{int(daily['Downtime (min)'].max())} min")
            s2.metric("Avg Daily Downtime", f"{daily['Downtime (min)'].mean():.0f} min")
            s3.metric("Worst Day",          str(daily["Downtime (min)"].idxmax()))

    # ══════════════════════════════════════════════════════════════════════════
    # TAB 4 — MTTR
    # ══════════════════════════════════════════════════════════════════════════
    with tab_mttr:
        section_header("Mean Time To Repair — by machine / area")

        mt1, mt2 = st.columns([2, 1])
        with mt1:
            m_period = st.selectbox("Period", ["Last 7 days", "Last 30 days", "All time"], key="m_period")
        with mt2:
            m_line = st.selectbox("Line", ["All Lines"] + [f"Line {i}" for i in LINES], key="m_line")

        if m_period == "Last 7 days":
            d0 = str(production_day() - timedelta(days=6))
            mdf = _load_range(d0, day)
        elif m_period == "Last 30 days":
            d0 = str(production_day() - timedelta(days=29))
            mdf = _load_range(d0, day)
        else:
            mdf = _load_range("2000-01-01", day)

        if m_line != "All Lines":
            mdf = mdf[mdf["line_number"] == int(m_line.split(" ")[1])]

        if mdf.empty:
            st.info("No fault data for the selected period.")
        else:
            mttr = (
                mdf.groupby("fault_machine")["downtime_minutes"]
                .agg(
                    Faults="count",
                    Total_min="sum",
                    MTTR_mean="mean",
                    MTTR_max="max",
                    MTTR_min="min",
                )
                .reset_index()
                .rename(columns={
                    "fault_machine": "Machine / Area",
                    "Total_min":    "Total Downtime (min)",
                    "MTTR_mean":    "Avg MTTR (min)",
                    "MTTR_max":     "Max MTTR (min)",
                    "MTTR_min":     "Min MTTR (min)",
                })
            )
            mttr["Avg MTTR (min)"] = mttr["Avg MTTR (min)"].round(1)
            mttr["Max MTTR (min)"] = mttr["Max MTTR (min)"].round(1)
            mttr["Min MTTR (min)"] = mttr["Min MTTR (min)"].round(1)
            mttr = mttr.sort_values("Avg MTTR (min)", ascending=False).reset_index(drop=True)

            st.dataframe(
                mttr[["Machine / Area", "Faults", "Total Downtime (min)",
                       "Avg MTTR (min)", "Min MTTR (min)", "Max MTTR (min)"]],
                use_container_width=True,
                hide_index=True,
            )

            # Highlight worst MTTR
            worst = mttr.iloc[0]
            st.markdown(
                f"<div style='background:var(--surface2);border:1px solid var(--border);"
                f"border-radius:8px;padding:12px 16px;margin-top:8px;font-size:.84rem;'>"
                f"Longest average repair: <b style='color:var(--red)'>{worst['Machine / Area']}</b> "
                f"at <b style='color:var(--red)'>{worst['Avg MTTR (min)']} min avg</b> "
                f"across <b>{int(worst['Faults'])}</b> fault{'s' if worst['Faults'] != 1 else ''}."
                f"</div>",
                unsafe_allow_html=True,
            )

            # Per-line breakdown for the worst machine
            st.markdown(
                "<div class='section-header' style='margin-top:20px'>Per-line breakdown</div>",
                unsafe_allow_html=True,
            )
            line_breakdown = (
                mdf.groupby(["line_number", "fault_machine"])["downtime_minutes"]
                .agg(Faults="count", Total="sum", Avg="mean")
                .reset_index()
                .rename(columns={
                    "line_number":   "Line",
                    "fault_machine": "Machine / Area",
                    "Total":         "Total (min)",
                    "Avg":           "Avg MTTR (min)",
                })
            )
            line_breakdown["Avg MTTR (min)"] = line_breakdown["Avg MTTR (min)"].round(1)
            line_breakdown = line_breakdown.sort_values(["Total (min)"], ascending=False).reset_index(drop=True)
            st.dataframe(line_breakdown, use_container_width=True, hide_index=True)

            st.download_button(
                "⬇️ Export MTTR CSV",
                mttr.to_csv(index=False).encode(),
                f"mttr_{m_period.replace(' ', '_')}.csv",
                "text/csv",
                key="mttr_dl",
            )
