"""
reports/pdf_report.py — Management-ready production performance PDF
Usage: pdf_bytes = build_production_pdf(r_prod, r_faults, date_from, date_to, shift_label)
"""

import io
from datetime import datetime

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand palette ─────────────────────────────────────────────────────────────
_GREEN   = colors.HexColor("#00C087")   # accent
_GREEN_L = colors.HexColor("#E6FAF5")
_WARN    = colors.HexColor("#F59E0B")
_WARN_L  = colors.HexColor("#FFFBEB")
_RED     = colors.HexColor("#EF4444")
_RED_L   = colors.HexColor("#FEF2F2")
_DARK    = colors.HexColor("#0F172A")
_MID     = colors.HexColor("#334155")
_MUTED   = colors.HexColor("#94A3B8")
_BORDER  = colors.HexColor("#E2E8F0")
_SURFACE = colors.HexColor("#F8FAFC")
_WHITE   = colors.white

W, H = A4   # 210 × 297 mm
MARGIN = 18 * mm
INNER_W = W - 2 * MARGIN


# ── Style helpers ─────────────────────────────────────────────────────────────
def _styles():
    base = getSampleStyleSheet()
    def _s(name, **kw):
        defaults = dict(fontName="Helvetica", fontSize=9, leading=13, textColor=_DARK)
        defaults.update(kw)
        return ParagraphStyle(name, parent=base["Normal"], **defaults)

    return dict(
        h1    = _s("h1", fontName="Helvetica-Bold", fontSize=22, textColor=_DARK, leading=26),
        h2    = _s("h2", fontName="Helvetica-Bold", fontSize=13, textColor=_DARK, leading=18),
        h3    = _s("h3", fontName="Helvetica-Bold", fontSize=10, textColor=_MID,  leading=14),
        body  = _s("body"),
        muted = _s("muted", textColor=_MUTED, fontSize=8),
        mono  = _s("mono",  fontName="Courier",   fontSize=8,  textColor=_MID),
        right = _s("right", alignment=TA_RIGHT),
        center= _s("center",alignment=TA_CENTER),
        kpi_val = _s("kpi_val", fontName="Helvetica-Bold", fontSize=15, textColor=_GREEN, leading=19, alignment=TA_CENTER),
        kpi_lbl = _s("kpi_lbl", fontSize=7,  textColor=_MUTED, alignment=TA_CENTER, leading=10),
        thead   = _s("thead", fontName="Helvetica-Bold", fontSize=8, textColor=_WHITE, alignment=TA_CENTER, leading=11),
        tcell   = _s("tcell", fontSize=8, textColor=_DARK, alignment=TA_LEFT, leading=11),
        tcell_c = _s("tcell_c", fontSize=8, textColor=_DARK, alignment=TA_CENTER, leading=11),
        tcell_r = _s("tcell_r", fontSize=8, textColor=_DARK, alignment=TA_RIGHT, leading=11),
    )


def _hr(width=INNER_W, color=_BORDER, thickness=0.5):
    return HRFlowable(width=width, thickness=thickness, color=color, spaceAfter=4)


def _eff(produced, target):
    if not target or target == 0:
        return 0.0
    return round((produced / target) * 100, 1)


def _eff_color(e):
    if e >= 85: return _GREEN
    if e >= 70: return _WARN
    return _RED


def _eff_dt(df):
    if not df.empty and "actual_downtime_minutes" in df.columns:
        return df["actual_downtime_minutes"].fillna(df["downtime_minutes"])
    if not df.empty and "downtime_minutes" in df.columns:
        return df["downtime_minutes"]
    return pd.Series(dtype=float)


def _calc_oee(plan_hrs: float, actual_hrs: float, produced: int,
              target: int, rejected: int, down_hrs: float) -> float:
    """OEE = Availability × Performance × Quality. Returns 0.0 if data insufficient."""
    if actual_hrs <= 0 or target <= 0:
        return 0.0
    net_hrs      = max(actual_hrs - down_hrs, 0.0)
    availability = net_hrs / actual_hrs
    performance  = min(produced / target, 1.0)
    good         = max(produced - rejected, 0)
    quality      = (good / produced) if produced > 0 else 0.0
    return round(availability * performance * quality * 100, 1)


# ── Header / Footer callbacks ─────────────────────────────────────────────────
def _make_header_footer(title: str, date_range: str):
    def _draw(canvas, doc):
        canvas.saveState()
        pw, ph = canvas._pagesize

        # Header bar
        canvas.setFillColor(_DARK)
        canvas.rect(0, ph - 18*mm, pw, 18*mm, fill=1, stroke=0)
        canvas.setFont("Helvetica-Bold", 10)
        canvas.setFillColor(_WHITE)
        canvas.drawString(MARGIN, ph - 11*mm, "RITEFOODS LIMITED")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(_MUTED)
        canvas.drawString(MARGIN, ph - 15.5*mm, "Production Management System")
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(_GREEN)
        right_x = pw - MARGIN - canvas.stringWidth(title, "Helvetica", 8)
        canvas.drawString(right_x, ph - 11*mm, title)
        canvas.setFillColor(_MUTED)
        dr_x = pw - MARGIN - canvas.stringWidth(date_range, "Helvetica", 8)
        canvas.drawString(dr_x, ph - 15.5*mm, date_range)

        # Footer
        canvas.setFillColor(_SURFACE)
        canvas.rect(0, 0, pw, 10*mm, fill=1, stroke=0)
        canvas.setStrokeColor(_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(MARGIN, 10*mm, pw - MARGIN, 10*mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(_MUTED)
        canvas.drawString(MARGIN, 4*mm, f"Generated {datetime.now().strftime('%d %b %Y, %H:%M')}  ·  Confidential — For management use only")
        page_str = f"Page {doc.page}"
        canvas.drawRightString(pw - MARGIN, 4*mm, page_str)
        canvas.restoreState()
    return _draw


# ── KPI banner ────────────────────────────────────────────────────────────────
def _kpi_table(kpis: list, s: dict) -> Table:
    """kpis: list of (value_str, label_str, color). Auto-heights — no clipping."""
    vals = [Paragraph(v, ParagraphStyle("kv", parent=s["kpi_val"], textColor=c))
            for v, l, c in kpis]
    lbls = [Paragraph(l, s["kpi_lbl"]) for v, l, c in kpis]
    col_w = INNER_W / len(kpis)
    t = Table(
        [vals, lbls],
        colWidths=[col_w] * len(kpis),
        # None = auto-height so long values wrap rather than clip
    )
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _SURFACE),
        ("BOX",           (0, 0), (-1, -1), 0.5, _BORDER),
        ("INNERGRID",     (0, 0), (-1, -1), 0.5, _BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1,  0), 10),
        ("BOTTOMPADDING", (0, 0), (-1,  0), 6),
        ("TOPPADDING",    (0, 1), (-1,  1), 4),
        ("BOTTOMPADDING", (0, 1), (-1,  1), 10),
    ]))
    return t


# ── Generic data table ────────────────────────────────────────────────────────
def _data_table(headers: list, rows: list, col_widths: list, s: dict,
                header_bg=_DARK, alt_bg=_SURFACE) -> Table:
    h_cells = [Paragraph(h, s["thead"]) for h in headers]
    data = [h_cells]
    for row in rows:
        cells = []
        for j, cell in enumerate(row):
            style = s["tcell_c"] if j > 0 else s["tcell"]
            if isinstance(cell, tuple):
                val, align, color = cell
                ps = ParagraphStyle("dc", parent=s["tcell"], alignment=TA_CENTER if align=="c" else (TA_RIGHT if align=="r" else TA_LEFT), textColor=color)
                cells.append(Paragraph(str(val), ps))
            else:
                cells.append(Paragraph(str(cell), style))
        data.append(cells)

    t = Table(data, colWidths=col_widths, repeatRows=1)
    ts = [
        ("BACKGROUND",    (0, 0), (-1, 0), header_bg),
        ("TEXTCOLOR",     (0, 0), (-1, 0), _WHITE),
        ("FONTNAME",      (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 0), 8),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, alt_bg]),
        ("LINEBELOW",     (0, 0), (-1, -1), 0.3, _BORDER),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]
    t.setStyle(TableStyle(ts))
    return t


# ── Section heading ───────────────────────────────────────────────────────────
def _section(title: str, s: dict) -> list:
    return [
        Spacer(1, 6*mm),
        Paragraph(title.upper(), ParagraphStyle(
            "sh", fontName="Helvetica-Bold", fontSize=7,
            textColor=_GREEN, letterSpacing=1.2, leading=10,
        )),
        _hr(),
    ]


# ── Main builder ──────────────────────────────────────────────────────────────
def build_production_pdf(
    prod_df: pd.DataFrame,
    fault_df: pd.DataFrame,
    date_from,
    date_to,
    shift_label: str = "All Shifts",
) -> bytes:
    """
    Build a management-ready production PDF report.
    Returns raw PDF bytes.
    """
    buf = io.BytesIO()
    s   = _styles()

    date_from_str = str(date_from)
    date_to_str   = str(date_to)
    period_lbl    = f"{date_from_str} to {date_to_str}" if date_from_str != date_to_str else date_from_str
    title_str     = "Production Performance Report"
    hdr_footer    = _make_header_footer(title_str, period_lbl)

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=22*mm, bottomMargin=14*mm,
        title=title_str,
        author="Ritefoods Limited — Production Management System",
    )

    story = []

    # ── Cover / Title block ───────────────────────────────────────────────────
    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Production Performance Report", s["h1"]))
    story.append(Spacer(1, 2*mm))
    story.append(Paragraph(
        f"Period: <b>{period_lbl}</b>   ·   Shift: <b>{shift_label}</b>",
        s["muted"],
    ))
    story.append(Spacer(1, 6*mm))
    story.append(_hr(color=_GREEN, thickness=1.5))

    # ── Executive KPI Summary ────────────────────────────────────────────────
    story += _section("Executive Summary", s)

    if prod_df is None or prod_df.empty:
        story.append(Paragraph("No closed production runs in the selected period.", s["muted"]))
    else:
        total_produced = int(prod_df["packs_produced"].fillna(0).sum())
        total_target   = int(prod_df["packs_target"].fillna(0).sum())
        plant_eff      = _eff(total_produced, total_target)
        total_runs     = len(prod_df)
        lines_active   = prod_df["line_number"].nunique() if "line_number" in prod_df.columns else 0

        f_dt = int(_eff_dt(fault_df).sum()) if fault_df is not None and not fault_df.empty else 0
        f_ct = len(fault_df) if fault_df is not None and not fault_df.empty else 0

        # Plant-level OEE (aggregate all closed runs in period)
        _plan_h   = float(prod_df["plan_time_hrs"].fillna(8).sum())
        _actual_h = float(prod_df["actual_time_hrs"].fillna(0).sum())
        _rejected = int(prod_df["packs_rejected"].fillna(0).sum()) \
            if "packs_rejected" in prod_df.columns else 0
        plant_oee = _calc_oee(_plan_h, _actual_h, total_produced,
                               total_target, _rejected, f_dt / 60.0)

        kpis = [
            (f"{total_produced:,}", "Cases Produced",
             _GREEN if plant_eff >= 85 else _WARN),
            (f"{plant_eff}%", "Line Efficiency (vs Target)",
             _eff_color(plant_eff)),
            (f"{plant_oee}%", "Plant OEE",
             _eff_color(plant_oee)),
            (f"{total_runs}", "Production Runs", _MID),
            (f"{f_dt} min", "Total Downtime",
             _RED if f_dt > 240 else (_WARN if f_dt > 60 else _GREEN)),
        ]
        story.append(_kpi_table(kpis, s))
        story.append(Spacer(1, 3*mm))

        gap = total_target - total_produced
        gap_pct = round((gap / total_target * 100), 1) if total_target else 0
        summary_lines = [
            (f"Total target: <b>{total_target:,} cases</b>"
             f"   ·   Gap to target: <b>{gap:,} cases ({gap_pct}%)</b>"),
            (f"Active lines: <b>{lines_active}</b>"
             f"   ·   Fault incidents: <b>{f_ct}</b>"
             f"   ·   Downtime: <b>{f_dt} min</b>"
             f"   ·   OEE note: Line Efficiency = Output/Target;"
             f" OEE also factors Availability &amp; Quality"),
        ]
        for line in summary_lines:
            story.append(Paragraph(line, s["muted"]))
            story.append(Spacer(1, 1*mm))

    # ── Per-Line Performance ──────────────────────────────────────────────────
    story += _section("Per-Line Performance", s)

    if prod_df is not None and not prod_df.empty:
        try:
            _agg = {
                "Runs":      ("id", "count"),
                "Produced":  ("packs_produced", "sum"),
                "Target":    ("packs_target", "sum"),
                "Plan_hrs":  ("plan_time_hrs", "sum"),
                "Actual_hrs":("actual_time_hrs", "sum"),
            }
            if "packs_rejected" in prod_df.columns:
                _agg["Rejected"] = ("packs_rejected", "sum")
            line_grp = prod_df.groupby("line_number").agg(**_agg).reset_index()
            if "Rejected" not in line_grp.columns:
                line_grp["Rejected"] = 0

            line_grp["Eff%"] = line_grp.apply(
                lambda r: _eff(int(r["Produced"]), int(r["Target"])), axis=1
            )
            line_grp["Gap"] = (line_grp["Target"] - line_grp["Produced"]).astype(int)
            line_grp = line_grp.sort_values("line_number")

            # Merge downtime per line
            if fault_df is not None and not fault_df.empty \
                    and "line_number" in fault_df.columns:
                fdt_line = fault_df.groupby("line_number").apply(
                    lambda g: _eff_dt(g).sum(), include_groups=False
                ).reset_index().rename(columns={0: "DT_min"})
                line_grp = line_grp.merge(fdt_line, on="line_number", how="left")
                line_grp["DT_min"] = line_grp["DT_min"].fillna(0).astype(int)
            else:
                line_grp["DT_min"] = 0

            # OEE per line
            line_grp["OEE%"] = line_grp.apply(
                lambda r: _calc_oee(
                    float(r.get("Plan_hrs") or 0),
                    float(r.get("Actual_hrs") or 0),
                    int(r["Produced"]),
                    int(r["Target"]),
                    int(r.get("Rejected") or 0),
                    float(r["DT_min"]) / 60.0,
                ), axis=1
            )

            headers = [
                "Line", "Runs", "Produced", "Target",
                "Efficiency", "OEE", "Gap (cases)", "DT (min)",
            ]
            col_widths = [
                20*mm, 14*mm, 26*mm, 26*mm,
                22*mm, 20*mm, 24*mm, 22*mm,
            ]
            rows = []
            for _, r in line_grp.iterrows():
                e   = float(r["Eff%"])
                oee = float(r["OEE%"])
                dt  = int(r["DT_min"])
                rows.append([
                    f"Line {int(r['line_number'])}",
                    (str(int(r["Runs"])), "c", _DARK),
                    (f"{int(r['Produced']):,}", "c", _DARK),
                    (f"{int(r['Target']):,}", "c", _DARK),
                    (f"{e}%", "c", _eff_color(e)),
                    (f"{oee}%", "c", _eff_color(oee)),
                    (f"{int(r['Gap']):,}", "c", _RED if r["Gap"] > 0 else _GREEN),
                    (str(dt), "c",
                     _RED if dt > 60 else (_WARN if dt > 20 else _DARK)),
                ])

            # Totals row
            tot_prod = int(line_grp["Produced"].sum())
            tot_tgt  = int(line_grp["Target"].sum())
            tot_e    = _eff(tot_prod, tot_tgt)
            tot_gap  = tot_tgt - tot_prod
            tot_dt   = int(line_grp["DT_min"].sum())
            _tp_h    = float(line_grp["Plan_hrs"].sum())
            _ta_h    = float(line_grp["Actual_hrs"].sum())
            _tr      = int(line_grp["Rejected"].sum())
            tot_oee  = _calc_oee(_tp_h, _ta_h, tot_prod, tot_tgt, _tr, tot_dt / 60.0)
            rows.append([
                "TOTAL",
                (str(int(line_grp["Runs"].sum())), "c", _WHITE),
                (f"{tot_prod:,}", "c", _WHITE),
                (f"{tot_tgt:,}", "c", _WHITE),
                (f"{tot_e}%", "c", _WHITE),
                (f"{tot_oee}%", "c", _WHITE),
                (f"{tot_gap:,}", "c", _WHITE),
                (str(tot_dt), "c", _WHITE),
            ])

            t = _data_table(headers, rows, col_widths, s)
            # Override last row background
            nrows = len(rows) + 1  # +1 for header
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, nrows - 1), (-1, nrows - 1), _DARK),
                ("FONTNAME",   (0, nrows - 1), (-1, nrows - 1), "Helvetica-Bold"),
            ]))
            story.append(t)
        except Exception as exc:
            story.append(Paragraph(f"Could not build per-line table: {exc}", s["muted"]))

    # ── SKU Performance ───────────────────────────────────────────────────────
    story += _section("Performance by SKU / Product", s)

    if prod_df is not None and not prod_df.empty:
        try:
            sku_cols = [c for c in ["product_name","flavor","pack_size","packaging",
                                    "packs_produced","packs_target"] if c in prod_df.columns]
            sku_df = prod_df[sku_cols].copy()
            sku_df["sku"] = (
                sku_df.get("product_name", pd.Series("")).fillna("") + " " +
                sku_df.get("flavor", pd.Series("")).fillna("") + " · " +
                sku_df.get("pack_size", pd.Series("")).fillna("") + " " +
                sku_df.get("packaging", pd.Series("")).fillna("")
            ).str.strip()
            sku_grp = sku_df.groupby("sku").agg(
                Runs     = ("packs_produced","count"),
                Produced = ("packs_produced","sum"),
                Target   = ("packs_target","sum"),
            ).reset_index()
            sku_grp["Eff%"] = sku_grp.apply(
                lambda r: _eff(int(r["Produced"]), int(r["Target"])), axis=1
            )
            sku_grp["Gap"] = (sku_grp["Target"] - sku_grp["Produced"]).astype(int)
            sku_grp = sku_grp.sort_values("Eff%").reset_index(drop=True)

            headers  = ["SKU / Product", "Runs", "Produced", "Target", "Efficiency", "Gap (cases)"]
            col_w    = [68*mm, 14*mm, 24*mm, 24*mm, 22*mm, 24*mm]
            rows = []
            for _, r in sku_grp.iterrows():
                e = float(r["Eff%"])
                rows.append([
                    str(r["sku"])[:55],
                    (str(int(r["Runs"])), "c", _DARK),
                    (f"{int(r['Produced']):,}", "c", _DARK),
                    (f"{int(r['Target']):,}", "c", _DARK),
                    (f"{e}%", "c", _eff_color(e)),
                    (f"{int(r['Gap']):,}", "c", _RED if r["Gap"] > 0 else _GREEN),
                ])
            story.append(_data_table(headers, rows, col_w, s))
        except Exception as exc:
            story.append(Paragraph(f"Could not build SKU table: {exc}", s["muted"]))

    # ── Fault Summary ─────────────────────────────────────────────────────────
    story += _section("Fault & Downtime Summary", s)

    if fault_df is None or fault_df.empty:
        story.append(Paragraph("No fault records in the selected period.", s["muted"]))
    else:
        f_total_dt  = int(_eff_dt(fault_df).sum())
        f_count     = len(fault_df)
        validated   = int((fault_df.get("status", pd.Series()) == "closed").sum()) if "status" in fault_df.columns else 0
        pending     = f_count - validated

        story.append(Paragraph(
            f"Total incidents: <b>{f_count}</b>   ·   "
            f"Validated by engineering: <b>{validated}</b>   ·   "
            f"Pending validation: <b>{pending}</b>   ·   "
            f"Total downtime: <b>{f_total_dt} min ({f_total_dt/60:.1f} hrs)</b>",
            s["muted"],
        ))
        story.append(Spacer(1, 3*mm))

        if "fault_machine" in fault_df.columns:
            try:
                mach_grp = fault_df.groupby("fault_machine").agg(
                    Incidents=("id","count"),
                ).reset_index()
                mach_grp["Downtime (min)"] = fault_df.groupby("fault_machine").apply(
                    lambda g: int(_eff_dt(g).sum()), include_groups=False
                ).values
                mach_grp = mach_grp.sort_values("Downtime (min)", ascending=False).reset_index(drop=True)

                headers = ["Fault Area / Machine", "Incidents", "Downtime (min)", "% of Total DT"]
                col_w   = [70*mm, 24*mm, 32*mm, 30*mm]
                rows    = []
                for _, r in mach_grp.iterrows():
                    pct = round(r["Downtime (min)"] / f_total_dt * 100, 1) if f_total_dt else 0
                    dt  = int(r["Downtime (min)"])
                    rows.append([
                        str(r["fault_machine"]),
                        (str(int(r["Incidents"])), "c", _DARK),
                        (str(dt), "c", _RED if dt > 60 else (_WARN if dt > 20 else _DARK)),
                        (f"{pct}%", "c", _MUTED),
                    ])
                story.append(_data_table(headers, rows, col_w, s))
            except Exception as exc:
                story.append(Paragraph(f"Fault table error: {exc}", s["muted"]))

    # ── Shift Breakdown ───────────────────────────────────────────────────────
    if prod_df is not None and not prod_df.empty and "shift" in prod_df.columns:
        story += _section("Shift Breakdown", s)
        try:
            prod_df["shift_short"] = prod_df["shift"].str.split("(").str[0].str.strip()
            sh_grp = prod_df.groupby("shift_short").agg(
                Runs     = ("id","count"),
                Produced = ("packs_produced","sum"),
                Target   = ("packs_target","sum"),
            ).reset_index()
            sh_grp["Eff%"] = sh_grp.apply(lambda r: _eff(int(r["Produced"]), int(r["Target"])), axis=1)
            sh_grp["Gap"]  = (sh_grp["Target"] - sh_grp["Produced"]).astype(int)

            headers = ["Shift", "Runs", "Produced", "Target", "Efficiency", "Gap (cases)"]
            col_w   = [36*mm, 18*mm, 28*mm, 28*mm, 24*mm, 22*mm]
            rows    = []
            for _, r in sh_grp.iterrows():
                e = float(r["Eff%"])
                rows.append([
                    str(r["shift_short"]),
                    (str(int(r["Runs"])), "c", _DARK),
                    (f"{int(r['Produced']):,}", "c", _DARK),
                    (f"{int(r['Target']):,}", "c", _DARK),
                    (f"{e}%", "c", _eff_color(e)),
                    (f"{int(r['Gap']):,}", "c", _RED if r["Gap"] > 0 else _GREEN),
                ])
            story.append(_data_table(headers, rows, col_w, s))
        except Exception as exc:
            story.append(Paragraph(f"Shift table error: {exc}", s["muted"]))

    # ── Closing note ──────────────────────────────────────────────────────────
    story.append(Spacer(1, 8*mm))
    story.append(_hr(color=_GREEN, thickness=1))
    story.append(Spacer(1, 3*mm))
    story.append(Paragraph(
        "This report is auto-generated by the Ritefoods Limited Production Management System. "
        "All figures reflect actual logged data for the selected period. "
        "OEE validation data sourced from engineering closure records where available.",
        s["muted"],
    ))

    doc.build(story, onFirstPage=hdr_footer, onLaterPages=hdr_footer)
    return buf.getvalue()
