"""
app.py — Ritefoods Limited Production Management System
Run with: streamlit run app.py
"""

import streamlit as st

st.set_page_config(
    page_title="Ritefoods Limited — Production",
    page_icon="🏭",
    layout="wide",
    initial_sidebar_state="expanded",
)

import views.log_production   as log_production
import views.log_fault        as log_fault
import views.shift_dashboard  as shift_dashboard
import views.shift_handover   as shift_handover
import views.records          as records
import views.manager_overview as manager_overview
import views.user_management  as user_management
import views.engineer_faults  as engineer_faults


from db    import init_db
from auth  import authenticate, require_login, current_user, logout
from auth import production_day, current_shift
from config import read_sql
from components.ui import inject_css, kpi_mini, efficiency, theme_toggle


# ── Init ──────────────────────────────────────────────────────────────────────
inject_css()
init_db()

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN
# ══════════════════════════════════════════════════════════════════════════════
if not require_login():
    st.markdown("""
    <style>
    #MainMenu, footer, header        { display: none !important; }
    [data-testid="stSidebar"]        { display: none !important; }
    [data-testid="stAppViewContainer"] > .main > .block-container {
        padding: 0 !important; max-width: 100% !important;
    }
    .stApp { overflow: hidden; }
    .lp-shell {
        position: fixed; inset: 0; display: flex; z-index: 0;
        background: #0d0f14; font-family: 'DM Sans', sans-serif;
    }
    .lp-left { flex: 0 0 58%; position: relative; overflow: hidden; }
    .lp-left img {
        width: 100%; height: 100%; object-fit: cover; display: block;
        filter: brightness(0.45) saturate(0.8);
    }
    .lp-left-overlay {
        position: absolute; inset: 0;
        background: linear-gradient(140deg,#0d0f14ee 0%,#0d0f1480 55%,transparent 100%);
        display: flex; flex-direction: column;
        justify-content: space-between; padding: 52px 56px;
    }
    .lp-eyebrow {
        font-family:'Space Mono',monospace; font-size:0.68rem; font-weight:700;
        color:#00e5a0; text-transform:uppercase; letter-spacing:3px; margin-bottom:18px;
    }
    .lp-headline {
        font-family:'Space Mono',monospace; font-size:2.7rem; font-weight:700;
        color:#fff; line-height:1.15; margin-bottom:14px;
    }
    .lp-headline span { color:#00e5a0; }
    .lp-sub { font-size:0.92rem; color:#ffffffaa; max-width:380px; line-height:1.75; margin-bottom:38px; }
    .lp-stats { display:flex; gap:40px; padding-top:26px; border-top:1px solid #ffffff15; }
    .lp-stat-val { font-family:'Space Mono',monospace; font-size:1.6rem; font-weight:700; color:#00e5a0; line-height:1; }
    .lp-stat-lbl { font-size:0.63rem; color:#ffffff55; text-transform:uppercase; letter-spacing:1.2px; margin-top:5px; }
    .lp-right { flex: 0 0 42%; background: #161922; border-left: 1px solid #252a35; }
    </style>
    <div class="lp-shell">
      <div class="lp-left">
        <img src="https://images.unsplash.com/photo-1565514158740-064f34bd6cfd?w=1400&q=80"
             alt="Bottling production line"/>
        <div class="lp-left-overlay">
          <div>
            <div class="lp-eyebrow">🏭 Ritefoods Limited</div>
            <div style="font-size:0.78rem;color:#ffffffaa;max-width:300px;line-height:1.6;">
              Production Management System
            </div>
          </div>
          <div>
            <div class="lp-headline">Real-time<br>Production<br><span>Intelligence</span></div>
            <div class="lp-sub">
              Monitor every line, track every fault, and hit your targets —
              shift by shift, line by line.
            </div>
          </div>
          <div class="lp-stats">
            <div><div class="lp-stat-val">8</div><div class="lp-stat-lbl">Production Lines</div></div>
            <div><div class="lp-stat-val">3</div><div class="lp-stat-lbl">Shifts / Day</div></div>
            <div><div class="lp-stat-val">Live</div><div class="lp-stat-lbl">Efficiency Tracking</div></div>
          </div>
        </div>
      </div>
      <div class="lp-right"></div>
    </div>
    """, unsafe_allow_html=True)

    _, right_col = st.columns([65, 35])
    with right_col:
        st.markdown("""
        <div style="margin-top:-96vh; height:100vh; display:flex; flex-direction:column;
                    justify-content:center; padding:0 60px;">
          <div style="font-family:'Space Mono',monospace; font-size:1.3rem; font-weight:700;
                      color:#00e5a0; margin-bottom:4px;">🏭 Ritefoods Limited</div>
          <div style="font-size:0.76rem; color:#6b7280; margin-bottom:40px;">
              Production Management System
          </div>
          <div style="font-family:'Space Mono',monospace; font-size:1.2rem; font-weight:700;
                      color:#e8eaf0; margin-bottom:24px;">Sign In</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<div style='padding:0 60px; margin-top:-300px;'>", unsafe_allow_html=True)
        username = st.text_input("Username", placeholder="e.g. lead1", key="login_user")
        password = st.text_input("Password", type="password",           key="login_pass")
        if st.button("🔓  Login", use_container_width=True, key="login_btn"):
            user = authenticate(username, password)
            if user:
                st.session_state["user"] = user
                st.rerun()
            else:
                st.error("Invalid username or password.")
        st.markdown("""
        <div style="margin-top:20px; padding:14px 16px; background:#1c2030;
                    border:1px solid #252a35; border-radius:8px;
                    font-size:0.74rem; color:#6b7280; line-height:2;">
            <b style="color:#e8eaf0;">Default accounts</b><br>
            Admin &#8594; <code>admin</code> / <code>admin123</code><br>
            Manager &#8594; <code>manager1</code> / <code>manager123</code><br>
            Shift Lead &#8594; <code>lead1</code> or <code>lead2</code> / <code>lead123</code><br>
            Engineer &#8594; create via User Management
        </div></div>
        """, unsafe_allow_html=True)
    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
user  = current_user()
role  = user["role"]
uname = user["username"]
fname = user["full_name"]

with st.sidebar:
    st.markdown("## 🏭 Ritefoods Limited")
    st.markdown(
        f"<div style='margin-bottom:16px'>"
        f"<div style='font-weight:600;font-size:0.95rem;color:var(--text)'>{fname}</div>"
        f"<span class='role-badge role-{role}'>{role.replace('_',' ')}</span>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div class='section-header'>Navigation</div>", unsafe_allow_html=True)

    lead_pages  = ["📋 Log Production", "⚠️ Log Fault", "📊 Shift Dashboard", "🔄 Shift Handover"] if role in ("shift_lead", "admin") else []
    mgr_pages   = ["🏭 Manager Overview"] if role in ("manager", "admin") else []
    eng_pages   = ["🔧 Fault Dashboard"]  if role in ("engineer", "admin") else []
    admin_pages = ["👤 User Management"]  if role == "admin" else []
    records_page = ["📁 Records"]
    all_pages = lead_pages + mgr_pages + eng_pages + records_page + admin_pages
    page = st.radio("", all_pages, label_visibility="collapsed", key="nav_radio")

    st.markdown("---")
    st.markdown("<div class='section-header'>Today at a glance</div>", unsafe_allow_html=True)

    @st.cache_data(ttl=60)
    def _sidebar_stats(day: str, _hour: int):  # _hour busts cache at shift boundaries
        _tp = read_sql("SELECT SUM(packs_produced) as p, SUM(packs_target) as t FROM production_runs WHERE status='closed' AND record_date=?", params=[day])
        _tf = read_sql("SELECT COUNT(*) as cnt, SUM(COALESCE(actual_downtime_minutes, downtime_minutes)) as dt FROM fault_records WHERE record_date=?", params=[day])
        _or = read_sql("SELECT COUNT(*) as cnt FROM production_runs WHERE status='open' AND record_date=?", params=[day])
        _ul = read_sql("SELECT COUNT(*) as cnt FROM fault_records WHERE production_run_id IS NULL AND record_date=?", params=[day])
        return _tp, _tf, _or, _ul

    from datetime import datetime as _dt
    _tp, _tf, _or, _ul = _sidebar_stats(str(production_day()), _dt.now().hour)

    _packs    = int(_tp["p"].iloc[0])   if _tp["p"].iloc[0]   else 0
    _tgt      = int(_tp["t"].iloc[0])   if _tp["t"].iloc[0]   else 0
    _eff      = efficiency(_packs, _tgt)
    _fc       = int(_tf["cnt"].iloc[0]) if _tf["cnt"].iloc[0] else 0
    _dt       = int(_tf["dt"].iloc[0])  if _tf["dt"].iloc[0]  else 0
    _open_ct  = int(_or["cnt"].iloc[0]) if _or["cnt"].iloc[0] else 0
    _unlinked = int(_ul["cnt"].iloc[0]) if _ul["cnt"].iloc[0] else 0

    kpi_mini(f"{_packs:,}", "Cases today",
             "warn" if (_tgt > 0 and _eff < 85) else "")
    kpi_mini(f"{_eff}%",    "Efficiency",
             "danger" if _eff < 70 else "warn" if _eff < 85 else "")

    kpi_mini(f"{_open_ct}", "Open runs", "warn" if _open_ct > 0 else "")
    kpi_mini(f"{_fc}", "Faults", "danger" if _fc >= 10 else "warn" if _fc > 0 else "")
    kpi_mini(f"{_dt}m", "Downtime", "danger" if _dt > 120 else "warn" if _dt > 60 else "")
    kpi_mini(f"{_unlinked}", "Unlinked faults", "warn" if _unlinked > 0 else "")

    st.markdown("---")
    st.markdown("<div style='margin-top:12px'></div>", unsafe_allow_html=True)
    st.markdown("<div class='logout-btn'>", unsafe_allow_html=True)
    if st.button("🚪  Logout", use_container_width=True, key='logout-btn'):
        logout()
    st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE ROUTING
# ══════════════════════════════════════════════════════════════════════════════
if   page == "📋 Log Production":   log_production.render(uname)
elif page == "⚠️ Log Fault":        log_fault.render(uname, fname)
elif page == "📊 Shift Dashboard":  shift_dashboard.render()
elif page == "🔄 Shift Handover":   shift_handover.render(uname, fname)
elif page == "📁 Records":          records.render()
elif page == "🏭 Manager Overview": manager_overview.render()
elif page == "🔧 Fault Dashboard":  engineer_faults.render()
elif page == "👤 User Management":  user_management.render()
