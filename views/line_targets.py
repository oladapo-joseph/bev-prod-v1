"""
views/line_targets.py — Line Production Targets
-------------------------------------------------
Managers and admins set a litres/hr volume throughput per line.
Cases target is derived automatically from volume ÷ bottle size ÷ bottles per case,
so the same line rate produces the correct case count for any SKU running on it.
The most recent entry (by effective_from date) is the active target.
"""

import streamlit as st
import pandas as pd
from datetime import date

from config import read_sql, execute
from data.reference import LINES, HOURLY_LITRES, HOURLY_TARGETS
from components.ui import section_header


@st.cache_data(ttl=30)
def _load_targets():
    return read_sql(
        "SELECT * FROM line_targets ORDER BY line_number, effective_from DESC, created_at DESC"
    )


def _active_for_line(all_targets: pd.DataFrame, line_number: int) -> dict | None:
    """Return the most-recent entry for this line, or None."""
    if all_targets.empty:
        return None
    df = all_targets[all_targets["line_number"] == line_number]
    return df.iloc[0].to_dict() if not df.empty else None


def render(username: str):
    st.markdown("# 🎯 Line Production Targets")
    section_header("Set volume throughput per line · cases target auto-derived per SKU")

    all_targets = _load_targets()

    # ═══════════════════════════════════════════════════════════════════════════
    # CURRENT EFFECTIVE RATES — 8 line cards
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    section_header("Active targets")
    st.caption(
        f"Custom L/hr overrides the global plant default ({HOURLY_LITRES:,} L/hr). "
        "Lines without a custom target use the global default."
    )

    cols = st.columns(4)
    for i, ln in enumerate(LINES):
        entry = _active_for_line(all_targets, ln)
        with cols[i % 4]:
            if entry:
                lph        = entry["litres_per_hour"]
                border_col = "var(--accent)"
                lbl_col    = "var(--accent)"
                num_col    = "var(--text)"
                status     = f"Since {str(entry.get('effective_from',''))[:10]}"
                sub        = f"Set by {entry.get('set_by','') or '—'}"
            else:
                lph        = HOURLY_LITRES
                border_col = "var(--border)"
                lbl_col    = "var(--muted)"
                num_col    = "var(--muted)"
                status     = "Global default"
                sub        = "No custom target"

            st.markdown(
                f"<div style='background:var(--surface2);border:1px solid {border_col};"
                f"border-radius:10px;padding:14px 16px;margin-bottom:12px;text-align:center;"
                f"min-height:140px;display:flex;flex-direction:column;justify-content:center'>"
                f"<div style='font-family:Space Mono,monospace;font-size:.65rem;color:{lbl_col};"
                f"text-transform:uppercase;letter-spacing:1px;margin-bottom:6px'>LINE {ln}</div>"
                f"<div style='font-family:Space Mono,monospace;font-size:1.4rem;font-weight:700;"
                f"color:{num_col};line-height:1.1'>{lph:,.0f}</div>"
                f"<div style='font-size:.7rem;color:var(--muted);margin-top:4px'>litres / hr</div>"
                f"<div style='font-size:.63rem;color:{lbl_col};margin-top:8px'>{status}</div>"
                f"<div style='font-size:.6rem;color:var(--muted);margin-top:2px'>{sub}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # ═══════════════════════════════════════════════════════════════════════════
    # SET A NEW TARGET
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    section_header("Set a new target")

    with st.form("set_target_form", clear_on_submit=True):
        fc1, fc2, fc3 = st.columns(3)
        with fc1:
            line_sel = st.selectbox(
                "Line *",
                ["— Select Line —"] + LINES,
                format_func=lambda x: f"Line {x}" if isinstance(x, int) else x,
            )
        with fc2:
            litres_per_hour = st.number_input(
                "Litres / Hour *",
                min_value=1.0,
                step=500.0,
                value=float(HOURLY_LITRES),
                help=(
                    f"Volume throughput for this line in litres per hour. "
                    f"Global default is {HOURLY_LITRES:,} L/hr. "
                    "Cases target is calculated automatically from this value based on the SKU running."
                ),
            )
        with fc3:
            effective_from = st.date_input("Effective From *", value=date.today())

        notes = st.text_input(
            "Notes (optional)",
            placeholder="e.g. Line 3 filler upgrade — revised throughput",
        )

        submitted = st.form_submit_button("💾 Save Target", use_container_width=True)

    if submitted:
        if not isinstance(line_sel, int):
            st.error("Please select a line.")
        elif litres_per_hour <= 0:
            st.error("Litres/hr must be greater than 0.")
        else:
            execute(
                "INSERT INTO line_targets (line_number, litres_per_hour, effective_from, set_by, notes) "
                "VALUES (?,?,?,?,?)",
                (line_sel, float(litres_per_hour), str(effective_from),
                 username, notes.strip() or None),
            )
            st.success(
                f"✅ Target saved — Line {line_sel}: **{litres_per_hour:,.0f} L/hr** "
                f"effective {effective_from}"
            )
            st.cache_data.clear()
            st.rerun()

    # ═══════════════════════════════════════════════════════════════════════════
    # GLOBAL PRODUCT DEFAULTS (reference)
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    with st.expander("Global product defaults (reference)", expanded=False):
        st.caption(
            f"Applied when no line-specific target is set ({HOURLY_LITRES:,} L/hr ÷ bottle size ÷ bottles per case)."
        )
        ref_rows = []
        for pname, sizes in HOURLY_TARGETS.items():
            for size, pkgs in sizes.items():
                for pkg, cph in pkgs.items():
                    ref_rows.append({
                        "Product":    pname,
                        "Pack Size":  size,
                        "Packaging":  pkg,
                        "Cases / Hr": f"{cph:,.1f}",
                    })
        if ref_rows:
            st.dataframe(pd.DataFrame(ref_rows), use_container_width=True, hide_index=True)

    # ═══════════════════════════════════════════════════════════════════════════
    # HISTORY LOG
    # ═══════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    section_header("Target history")

    if all_targets.empty:
        st.info("No custom targets have been set yet.")
    else:
        display = all_targets.copy()
        display["litres_per_hour"] = display["litres_per_hour"].apply(lambda x: f"{x:,.0f}")
        display["notes"]           = display["notes"].fillna("—") if "notes" in display.columns else "—"
        display = display.rename(columns={
            "line_number":     "Line",
            "litres_per_hour": "Litres / Hr",
            "effective_from":  "Effective From",
            "set_by":          "Set By",
            "notes":           "Notes",
        })
        cols_show = ["Line", "Litres / Hr", "Effective From", "Set By", "Notes"]
        st.dataframe(
            display[[c for c in cols_show if c in display.columns]],
            use_container_width=True,
            hide_index=True,
        )
