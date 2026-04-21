"""
components/ui.py — Shared UI helpers, CSS injection, and reusable widgets
"""

import streamlit as st
from datetime import date
from data.reference import LINES


# ── Efficiency helpers ────────────────────────────────────────────────────────
def efficiency(produced: int, target: int) -> float:
    if target == 0:
        return 0.0
    return round((produced / target) * 100, 1)


def eff_color(e: float) -> str:
    if e >= 85:
        return "var(--accent)"
    if e >= 70:
        return "var(--warn)"
    return "var(--red)"


# ── OEE helpers ──────────────────────────────────────────────────────────────
def calc_oee(
    plan_hrs: float,
    actual_hrs: float,
    packs_produced: int,
    packs_target: int,
    packs_rejected: int,
    down_hrs: float = 0.0,
) -> dict:
    """
    OEE = Availability × Performance × Quality

    Availability = (actual_run_time - downtime) / actual_run_time
    Performance  = packs_produced / packs_target
    Quality      = good_packs / packs_produced
    """
    if actual_hrs <= 0 or packs_target <= 0:
        return dict(availability=100.0, performance=0.0, quality=0.0, oee=0.0)

    # Availability: net productive time as a fraction of total run time
    net_hrs      = max(actual_hrs - down_hrs, 0.0)
    availability = net_hrs / actual_hrs  # 0.0 – 1.0

    # Performance: output vs target for the run window
    performance = min(packs_produced / packs_target, 1.0)

    # Quality: fraction of non-rejected output
    good_packs = max(packs_produced - packs_rejected, 0)
    quality    = (good_packs / packs_produced) if packs_produced > 0 else 0.0

    oee = availability * performance * quality

    return dict(
        availability = round(availability * 100, 1),
        performance  = round(performance  * 100, 1),
        quality      = round(quality      * 100, 1),
        oee          = round(oee          * 100, 1),
    )


def oee_color(oee: float) -> str:
    """World-class OEE ≥ 85%, acceptable ≥ 65%."""
    if oee >= 85: return "var(--accent)"
    if oee >= 65: return "var(--warn)"
    return "var(--red)"


def oee_badge(oee_dict: dict) -> str:
    """Render OEE breakdown badge — OEE headline + Availability, Performance, Quality."""
    col      = oee_color(oee_dict["oee"])
    avail    = oee_dict["availability"]
    avail_col= "var(--accent)" if avail >= 90 else ("var(--warn)" if avail >= 75 else "var(--red)")
    perf_col = oee_color(oee_dict["performance"])
    qual_col = "var(--accent)" if oee_dict["quality"] >= 99 else ("var(--warn)" if oee_dict["quality"] >= 95 else "var(--red)")
    sep      = "<div style='width:1px;background:var(--border);align-self:stretch'></div>"
    def _cell(val, label, color):
        return (
            f"<div style='text-align:center'>"
            f"<div style='font-family:Space Mono,monospace;font-size:.95rem;color:{color}'>{val}%</div>"
            f"<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase;letter-spacing:.6px'>{label}</div>"
            f"</div>"
        )
    return (
        "<div style='display:flex;gap:20px;flex-wrap:wrap;align-items:center;"
        "background:var(--surface2);border:1px solid var(--border);"
        "border-radius:8px;padding:10px 16px;margin-top:8px'>"
        f"<div style='text-align:center'>"
        f"<div style='font-family:Space Mono,monospace;font-size:1.25rem;font-weight:700;color:{col}'>{oee_dict['oee']}%</div>"
        f"<div style='font-size:.6rem;color:var(--muted);text-transform:uppercase;letter-spacing:.8px'>OEE</div></div>"
        f"{sep}"
        f"{_cell(avail, 'Availability', avail_col)}"
        f"{_cell(oee_dict['performance'], 'Performance', perf_col)}"
        f"{_cell(oee_dict['quality'], 'Quality', qual_col)}"
        "</div>"
    )


# ── Card components ───────────────────────────────────────────────────────────
def kpi_card(value, label: str, cls: str = "", color: str = None):
    color = color or ("var(--red)" if cls == "danger" else "var(--warn)" if cls == "warn" else "var(--accent)")
    st.markdown(
        f"<div class='metric-card {cls}'>"
        f"<div class='metric-value' style='color:{color}'>{value}</div>"
        f"<div class='metric-label'>{label}</div></div>",
        unsafe_allow_html=True,
    )


def kpi_mini(value, label: str, cls: str = ""):
    color = (
        "var(--red)"    if cls == "danger" else
        "var(--warn)"   if cls == "warn"   else
        "var(--accent)"
    )
    st.markdown(
        f"<div class='kpi-mini'>"
        f"<span class='kpi-mini-label'>{label}</span>"
        f"<span style='font-family:Space Mono,monospace;font-size:.95rem;"
        f"font-weight:700;color:{color}'>{value}</span></div>",
        unsafe_allow_html=True,
    )


def line_badge(line_number: int) -> str:
    return f"<span class='line-badge'>LINE {line_number}</span>"


def section_header(text: str):
    st.markdown(f"<div class='section-header'>{text}</div>", unsafe_allow_html=True)


def alert_banner(line_number: int, message: str):
    st.markdown(
        f"<div class='alert-banner'>"
        f"<span class='ab-line'>LINE {line_number}</span>"
        f"<span class='ab-msg'>{message}</span></div>",
        unsafe_allow_html=True,
    )


# ── Production report table ───────────────────────────────────────────────────
def build_report(prod_df, fault_df, title: str = "Production Summary Report"):
    """
    Render the line efficiency summary table matching the plant report format.
    prod_df   : production_runs dataframe (closed runs only)
    fault_df  : fault_records dataframe (linked or all, for the same period)

    Time columns come from actual run timestamps (run_start / run_end) stored
    on each production_run row — not estimated from shift counts.
    Rows: Plan Time, Actual Time, Down Time, Plan Production,
          Actual Production, Production Loss, Line Efficiency.
    """
    import pandas as pd
    from data.reference import LINES

    st.markdown(
        f"<div class='chart-title' style='font-size:.9rem;margin-bottom:12px'>{title}</div>",
        unsafe_allow_html=True,
    )

    if prod_df.empty:
        st.info("No production data for this period.")
        return

    rows: dict = {}
    for ln in LINES:
        lp = prod_df[prod_df["line_number"] == ln]
        lf = fault_df[fault_df["line_number"] == ln] if not fault_df.empty else pd.DataFrame()

        plan_packs   = int(lp["packs_target"].sum())   if not lp.empty else 0
        actual_packs = int(lp["packs_produced"].sum()) if not lp.empty else 0
        loss_packs   = plan_packs - actual_packs

        # Use stored time values if available, otherwise fall back to shift estimate
        if not lp.empty and "plan_time_hrs" in lp.columns and lp["plan_time_hrs"].notna().any():
            plan_hrs   = round(float(lp["plan_time_hrs"].sum()), 2)
            actual_hrs = round(float(lp["actual_time_hrs"].fillna(0).sum()), 2)
            down_hrs   = round(float(lp["down_time_hrs"].fillna(0).sum()), 2)
        else:
            from data.reference import SHIFT_HOURS
            def _shift_hrs(shift_str):
                for k, v in SHIFT_HOURS.items():
                    if k.lower() in str(shift_str).lower():
                        return v
                return 8  # safe fallback if unknown
            plan_hrs   = round(sum(_shift_hrs(s) for s in (lp["shift"] if not lp.empty else [])), 2)
            down_hrs   = round(int(lf["downtime_minutes"].sum()) / 60, 2) if not lf.empty else 0.0
            actual_hrs = round(plan_hrs - down_hrs, 2)

        rej_packs = int(lp["packs_rejected"].fillna(0).sum()) \
            if not lp.empty and "packs_rejected" in lp.columns else 0
        oee_dict = calc_oee(plan_hrs, actual_hrs, actual_packs, plan_packs, rej_packs, down_hrs)
        rows[ln] = dict(
            plan_hrs=plan_hrs, actual_hrs=actual_hrs, down_hrs=down_hrs,
            plan_packs=plan_packs, actual_packs=actual_packs,
            loss_packs=loss_packs,
            eff=efficiency(actual_packs, plan_packs),
            oee=oee_dict["oee"],
            availability=oee_dict["availability"],
            performance=oee_dict["performance"],
            quality=oee_dict["quality"],
        )

    tot = {k: sum(rows[ln][k] for ln in LINES)
           for k in ["plan_hrs", "actual_hrs", "down_hrs", "plan_packs", "actual_packs", "loss_packs"]}
    tot["eff"] = efficiency(tot["actual_packs"], tot["plan_packs"])
    _tot_oee = calc_oee(
        tot["plan_hrs"], tot["actual_hrs"],
        tot["actual_packs"], tot["plan_packs"], 0, tot["down_hrs"],
    )
    tot["oee"]          = _tot_oee["oee"]
    tot["availability"] = _tot_oee["availability"]
    tot["performance"]  = _tot_oee["performance"]
    tot["quality"]      = _tot_oee["quality"]

    def _fmt(v, is_hrs=False, is_neg=False):
        if v == 0:
            return "—"
        if is_neg and v < 0:
            return f"({abs(v):,.2f})" if is_hrs else f"({abs(int(v)):,})"
        return f"{v:,.2f}" if is_hrs else f"{int(v):,}"

    def _eff_cls(e):
        return "eff-green" if e >= 85 else ("eff-warn" if e >= 70 else "eff-red")

    def _row(label, uom, key, is_hrs=False, is_neg=False):
        cells = ""
        for ln in LINES:
            v = rows[ln][key]
            neg = is_neg and v < 0
            neg_cls = " class='neg'" if neg else ""
            cells += f"<td{neg_cls}>{_fmt(v, is_hrs, is_neg)}</td>"
        tv = tot[key]
        tot_cls = "total neg" if is_neg and tv < 0 else "total"
        cells += f"<td class='{tot_cls}'>{_fmt(tv, is_hrs, is_neg)}</td>"
        return f"<tr><td class='label'>{label}</td><td class='uom'>{uom}</td>{cells}</tr>"

    def _pct_cells(key):
        cells = ""
        for ln in LINES:
            v = rows[ln][key]
            cls = _eff_cls(v)
            cells += f"<td class='{cls}'>{v}%</td>" if rows[ln]["plan_packs"] > 0 else "<td class='eff-red'>—</td>"
        tv = tot[key]
        cells += f"<td class='{_eff_cls(tv)} total'>{tv}%</td>"
        return cells

    eff_cells = _pct_cells("eff")
    oee_cells = _pct_cells("oee")
    avl_cells = _pct_cells("availability")
    prf_cells = _pct_cells("performance")
    qlt_cells = _pct_cells("quality")

    line_hdrs = "".join(f"<th>LINE #{ln}</th>" for ln in LINES)
    html = f"""
    <div style='overflow-x:auto;margin-bottom:20px'>
    <table class='report-table'>
      <thead><tr><th style='text-align:left'>Metric</th><th>UOM</th>{line_hdrs}<th>Total</th></tr></thead>
      <tbody>
        {_row("Plan Time",              "hrs",   "plan_hrs",   is_hrs=True)}
        {_row("Actual Time",            "hrs",   "actual_hrs", is_hrs=True)}
        {_row("Down Time",              "hrs",   "down_hrs",   is_hrs=True, is_neg=True)}
        {_row("Plan Production",        "Packs", "plan_packs")}
        {_row("Actual Production",      "Packs", "actual_packs")}
        {_row("Production Loss / Gain", "Packs", "loss_packs", is_neg=True)}
        <tr><td class='label'>Line Efficiency</td><td class='uom'>%</td>{eff_cells}</tr>
        <tr style='border-top:2px solid var(--border)'>
          <td class='label' style='font-weight:700;color:var(--accent)'>OEE</td>
          <td class='uom'>%</td>{oee_cells}
        </tr>
        <tr>
          <td class='label' style='padding-left:20px;font-size:.78rem;color:var(--muted)'>↳ Availability</td>
          <td class='uom' style='font-size:.78rem'>%</td>{avl_cells}
        </tr>
        <tr>
          <td class='label' style='padding-left:20px;font-size:.78rem;color:var(--muted)'>↳ Performance</td>
          <td class='uom' style='font-size:.78rem'>%</td>{prf_cells}
        </tr>
        <tr>
          <td class='label' style='padding-left:20px;font-size:.78rem;color:var(--muted)'>↳ Quality</td>
          <td class='uom' style='font-size:.78rem'>%</td>{qlt_cells}
        </tr>
      </tbody>
    </table></div>"""
    st.markdown(html, unsafe_allow_html=True)

    # CSV export
    metrics = [
        ("Plan Time (hrs)",            "plan_hrs"),
        ("Actual Time (hrs)",          "actual_hrs"),
        ("Down Time (hrs)",            "down_hrs"),
        ("Plan Production (Packs)",    "plan_packs"),
        ("Actual Production (Packs)",  "actual_packs"),
        ("Production Loss (Packs)",    "loss_packs"),
        ("Line Efficiency (%)",        "eff"),
        ("OEE (%)",                    "oee"),
        ("Availability (%)",           "availability"),
        ("Performance (%)",            "performance"),
        ("Quality (%)",                "quality"),
    ]
    export = []
    for label, key in metrics:
        r = {"Metric": label}
        for ln in LINES:
            r[f"Line {ln}"] = rows[ln][key]
        r["Total"] = tot[key]
        export.append(r)

    import pandas as pd
    st.download_button(
        "⬇️ Export Report CSV",
        pd.DataFrame(export).to_csv(index=False).encode(),
        "production_report.csv",
        "text/csv",
        key=f"rep_dl_{title[:12]}",
    )


# ── Theme tokens ─────────────────────────────────────────────────────────────
DARK_THEME = """
:root{
    --bg:#0d0f14; --surface:#161922; --surface2:#1c2030; --border:#252a35;
    --accent:#00e5a0; --accent2:#ff6b35; --manager:#7c6ff7;
    --warn:#ffcc00; --text:#e8eaf0; --muted:#6b7280; --red:#ff4757;
    --input-bg:#1e2230; --btn-text:#0d0f14;
    --report-row:#161922; --report-head:#1c2030;
}"""

LIGHT_THEME = """
:root{
    --bg:#f4f6f9; --surface:#ffffff; --surface2:#eef1f6; --border:#d1d9e6;
    --accent:#009e6e; --accent2:#d9531e; --manager:#5b52cc;
    --warn:#c49a00; --text:#1a1f2e; --muted:#6b7280; --red:#cc2233;
    --input-bg:#ffffff; --btn-text:#ffffff;
    --report-row:#f8fafc; --report-head:#eef1f6;
}"""

SHARED_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');

/* ── Base & Streamlit chrome ── */
/* Only set background + font on containers — NOT color, to avoid overriding inline styles */
html,body,[data-testid="stAppViewContainer"],
[data-testid="stApp"],
.main, .block-container,
[data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"]{
    background-color:var(--bg)!important;
    font-family:'DM Sans',sans-serif!important;
}
/* Set default text color only on the root — inline style= on children will win */
html, body { color:var(--text)!important; }
[data-testid="stSidebar"]{background-color:var(--surface)!important;border-right:1px solid var(--border)!important;}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] h1,[data-testid="stSidebar"] h2,[data-testid="stSidebar"] h3,[data-testid="stSidebar"] label,[data-testid="stSidebar"] [data-testid="stMarkdownContainer"],[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,[data-testid="stSidebar"] [data-testid="stRadio"] label,[data-testid="stSidebar"] [data-testid="stRadio"] p{color:var(--text)!important;}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"],[data-testid="stSidebar"] section{background-color:var(--surface)!important;}

/* ── Streamlit markdown text only — no generic div/span override ── */
[data-testid="stMarkdownContainer"] > p,
[data-testid="stMarkdownContainer"] > ul > li,
[data-testid="stMarkdownContainer"] > ol > li{
    color:var(--text)!important;
}

/* ── Headings ── */
h1,h2,h3,h4,h5,h6{
    font-family:'Space Mono',monospace!important;
    letter-spacing:-0.5px;
    color:var(--text)!important;
}

/* ── Radio & selectbox labels ── */
[data-testid="stRadio"] label,
[data-testid="stSelectbox"] label,
[data-testid="stNumberInput"] label,
[data-testid="stTextInput"] label,
[data-testid="stTextArea"] label,
[data-testid="stDateInput"] label,
[data-testid="stCheckbox"] label,
[data-testid="stTimeInput"] label,
[data-baseweb="select"] span,
.stRadio label, .stCheckbox label{
    color:var(--text)!important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [data-baseweb="tab"]{color:var(--muted)!important;}
[data-testid="stTabs"] [data-baseweb="tab"][aria-selected="true"]{color:var(--accent)!important;}
[data-testid="stTabs"] [data-baseweb="tab-list"]{background:var(--surface)!important;border-bottom:1px solid var(--border)!important;}

/* ── Expander ── */
[data-testid="stExpander"]{background:var(--surface)!important;border:1px solid var(--border)!important;border-radius:8px!important;}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary p{color:var(--text)!important;}

/* ── Info / warning / error boxes ── */
[data-testid="stAlert"]{border-radius:8px!important;}
[data-testid="stAlert"] p{color:inherit!important;}

/* ── Dataframe ── */
.stDataFrame, [data-testid="stDataFrame"]{border-radius:10px;overflow:hidden;}
[data-testid="stDataFrame"] th{background:var(--surface2)!important;color:var(--muted)!important;}
[data-testid="stDataFrame"] td{color:var(--text)!important;background:var(--surface)!important;}

/* ── Toggle (st.toggle) ── */
[data-testid="stToggle"] label,
[data-testid="stToggle"] span{color:var(--text)!important;}

.login-wrap{max-width:420px;margin:60px auto;background:var(--surface);border:1px solid var(--border);border-radius:16px;padding:40px 36px;box-shadow:0 8px 24px #00000018;}
.login-logo{font-family:'Space Mono',monospace;font-size:1.6rem;font-weight:700;color:var(--accent);margin-bottom:4px;}
.login-sub{color:var(--muted);font-size:0.85rem;margin-bottom:28px;}

.role-badge{display:inline-block;padding:3px 12px;border-radius:20px;font-family:'Space Mono',monospace;font-size:0.65rem;font-weight:700;text-transform:uppercase;letter-spacing:1px;}
.role-shift_lead{background:#00e5a015;border:1px solid var(--accent);color:var(--accent);}
.role-engineer{background:#ff6b3515;border:1px solid var(--accent2);color:var(--accent2);}
.role-manager{background:#7c6ff715;border:1px solid var(--manager);color:var(--manager);}
.role-admin{background:#ff475715;border:1px solid var(--red);color:var(--red);}

.kpi-mini{background:var(--surface2);border:1px solid var(--border);border-radius:8px;padding:8px 12px;margin-bottom:6px;display:flex;justify-content:space-between;align-items:center;}
.kpi-mini-val{font-family:'Space Mono',monospace;font-size:0.95rem;font-weight:700;color:var(--accent);}
.kpi-mini-val.warn{color:var(--warn);}
.kpi-mini-val.danger{color:var(--red);}
.kpi-mini-label{font-size:0.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.8px;}

.metric-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px 24px;margin-bottom:12px;position:relative;overflow:hidden;}
.metric-card::before{content:'';position:absolute;top:0;left:0;width:4px;height:100%;background:var(--accent);}
.metric-card.warn::before{background:var(--warn);}
.metric-card.danger::before{background:var(--red);}
.metric-card.manager::before{background:var(--manager);}
.metric-value{font-family:'Space Mono',monospace;font-size:2rem;font-weight:700;color:var(--accent);line-height:1;}
.metric-label{font-size:0.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin-top:4px;}

.line-badge{display:inline-block;background:#00e5a015;border:1px solid var(--accent);color:var(--accent);font-family:'Space Mono',monospace;font-size:0.7rem;padding:2px 10px;border-radius:20px;}
.section-header{font-family:'Space Mono',monospace;font-size:0.65rem;color:var(--muted);text-transform:uppercase;letter-spacing:2px;border-bottom:1px solid var(--border);padding-bottom:8px;margin-bottom:16px;}
.alert-banner{background:#ff475712;border:1px solid var(--red);border-radius:10px;padding:12px 18px;margin-bottom:10px;display:flex;align-items:center;gap:12px;}
.alert-banner .ab-line{font-family:'Space Mono',monospace;font-size:0.75rem;color:var(--red);font-weight:700;}
.alert-banner .ab-msg{font-size:0.85rem;color:var(--text);}
.target-preview{background:var(--surface2);border:1px solid var(--border);border-radius:10px;padding:14px 18px;margin-top:8px;font-family:'Space Mono',monospace;}

.report-table{width:100%;border-collapse:collapse;font-size:0.82rem;font-family:'DM Sans',sans-serif;}
.report-table th{background:var(--report-head);color:var(--muted);font-size:0.68rem;text-transform:uppercase;letter-spacing:.8px;padding:8px 12px;border:1px solid var(--border);text-align:center;}
.report-table td{padding:8px 12px;border:1px solid var(--border);text-align:center;color:var(--text);}
.report-table tr:nth-child(even) td{background:var(--report-row);}
.report-table td.label{text-align:left;font-weight:500;color:var(--muted);}
.report-table td.uom{color:var(--muted);font-size:0.75rem;}
.report-table td.total{font-family:'Space Mono',monospace;font-weight:700;color:var(--accent);background:#00e5a008!important;}
.report-table td.eff-green{color:var(--accent);font-family:'Space Mono',monospace;font-weight:700;}
.report-table td.eff-warn{color:var(--warn);font-family:'Space Mono',monospace;font-weight:700;}
.report-table td.eff-red{color:var(--red);font-family:'Space Mono',monospace;font-weight:700;}
.report-table td.neg{color:var(--accent);}

[data-testid="stTextInput"] input,[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] > div > div,[data-testid="stTextArea"] textarea{
    background-color:var(--input-bg)!important;border:1px solid var(--border)!important;
    border-radius:8px!important;color:var(--text)!important;font-family:'DM Sans',sans-serif!important;}
[data-testid="stSelectbox"] > div > div:hover,[data-testid="stTextInput"] input:focus{border-color:var(--accent)!important;}
.stButton>button{background:var(--accent)!important;color:var(--btn-text)!important;font-family:'Space Mono',monospace!important;font-weight:700!important;border:none!important;border-radius:8px!important;padding:10px 28px!important;font-size:0.85rem!important;letter-spacing:0.5px!important;transition:all 0.2s!important;}
.stButton>button:hover{opacity:0.85!important;}
.stButton>button:disabled,.stButton>button[disabled]{background:var(--border)!important;color:var(--muted)!important;cursor:not-allowed!important;opacity:1!important;}
.stDataFrame{border-radius:10px;overflow:hidden;}
.stAlert{border-radius:8px!important;}
div[data-testid="stTab"] button{font-family:'Space Mono',monospace!important;font-size:0.75rem!important;}
.chart-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:20px;margin-bottom:16px;}
.chart-title{font-family:'Space Mono',monospace;font-size:0.75rem;color:var(--muted);text-transform:uppercase;letter-spacing:1.5px;margin-bottom:14px;}

/* Logout button override */
.logout-btn > button{background:#ff475720!important;color:var(--red)!important;border:1px solid var(--red)!important;font-family:'Space Mono',monospace!important;font-size:0.78rem!important;font-weight:700!important;padding:6px 16px!important;border-radius:8px!important;width:100%!important;transition:all 0.2s!important;}
.logout-btn > button:hover{background:var(--red)!important;color:#fff!important;}
"""


# ── CSS injection ─────────────────────────────────────────────────────────────
def inject_css():
    """Inject theme + shared CSS. Reads theme from st.session_state['theme']."""
    theme_vars = LIGHT_THEME if st.session_state.get("theme") == "light" else DARK_THEME
    st.markdown(
        f"<style>{theme_vars}{SHARED_CSS}</style>",
        unsafe_allow_html=True,
    )


def theme_toggle():
    """
    Render a compact sun/moon toggle in the sidebar.
    Call this inside the sidebar block after navigation.
    """
    is_light = st.session_state.get("theme") == "light"
    label    = "☀️ Light Mode" if not is_light else "🌙 Dark Mode"
    if st.button(label, key="theme_toggle_btn", use_container_width=True):
        st.session_state["theme"] = "light" if not is_light else "dark"
        st.rerun()