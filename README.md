# 🏭 Ritefoods Limited — Production Management System

A real-time, role-based production management system built with Streamlit and SQL Server. Tracks production runs, faults/downtime, shift handovers, and OEE across 8 bottling lines.

---

## Project Structure

```text
project/
├── app.py                        # Entrypoint, login, sidebar, routing
├── config.py                     # SQL Server / SQLite connection
├── db.py                         # Schema + auto-migrations
├── auth.py                       # Login, session, role enforcement, production day logic
├── requirements.txt
├── Dockerfile                    # python:3.12-bullseye + msodbcsql17
├── docker-compose.yaml           # Single service, port 8501
├── .env.example                  # DB credentials template
│
├── data/
│   └── reference.py              # Products, pack sizes, fault taxonomy, hourly targets
│
├── components/
│   └── ui.py                     # CSS injection, KPI widgets, OEE badge, production report table
│
├── reports/
│   └── pdf_report.py             # Management PDF report builder (reportlab)
│
└── views/
    ├── log_production.py         # Open Run / Close Run + fault backfill
    ├── log_fault.py              # Fault logging with auto-run linking + downtime sanity check
    ├── shift_dashboard.py        # Live shift view + Excel shift report export
    ├── shift_handover.py         # End-of-shift KPI summary + handover comments
    ├── manager_overview.py       # Manager tabs: overview, trends, fault analysis, production report + PDF export
    ├── engineer_faults.py        # Engineer fault dashboard: close/validate faults, Pareto, MTTR
    ├── records.py                # Historical records browser (role-filtered) + manager edit
    └── user_management.py        # Admin: create, deactivate, reset users
```

---

## Roles & Default Accounts

| Role       | Username                       | Password     | Access                                                              |
|------------|--------------------------------|--------------|---------------------------------------------------------------------|
| Admin      | `admin`                        | `admin123`   | Everything + User Management                                        |
| Manager    | `manager1`                     | `manager123` | Manager Overview (+ PDF export), Records (with edit)               |
| Shift Lead | `lead1`                        | `lead123`    | Log Production, Log Fault, Shift Dashboard (+ Excel export), Shift Handover, Records |
| Shift Lead | `lead2`                        | `lead123`    | Same as above                                                       |
| Engineer   | *(create via User Management)* | —            | Fault Dashboard (close/validate faults), Fault Records only        |

> **Change default passwords after first login** via User Management (admin only).

---

## Features

### Shift Lead

- **Log Production** — open and close production runs per line (1–8); run-time target calculated at close; zero-case guard prevents empty run closure
- **Log Fault** — log faults with area/machine, detail, downtime (minutes), and reporter; auto-linked to the active run on the selected line; warns if total downtime would exceed run elapsed time
- **Shift Dashboard** — live view of closed runs, active lines, and today's faults grouped by shift; **Excel export** (4-sheet: Summary, Per-Line, Fault Log, Run Detail)
- **Shift Handover** — end-of-shift KPI strip, line-by-line summary, outgoing comments, incoming brief from the previous shift

### Engineer

- **Fault Dashboard** — KPI strip (faults today, downtime, MTTR, recurring alerts); tabs: Close Faults, Live Feed, Pareto, Trends, MTTR
- **Close Faults** — engineers validate shift-lead fault entries: select root cause, confirm actual downtime, add resolution notes; updates `actual_downtime_minutes` which OEE and all reports use in preference to the shift-lead estimate
- **Fault Records** — filtered view of fault records only (no production run data)

### Manager

- **Manager Overview** — 5 tabs:
  - *All Lines* — real-time table of all 8 lines for any date with run expanders
  - *Shift Comparison* — efficiency and downtime across Morning/Afternoon/Night
  - *Weekly Trends* — 14-day charts + SKU performance breakdown (sorted worst-to-best)
  - *Fault Analysis* — top fault categories, per-line downtime, exportable CSV
  - *Production Report* — line-by-line report (Plan Time, Actual Time, Downtime, Plan Production, Actual Production, Loss/Gain, **Line Efficiency**, **OEE + Availability/Performance/Quality**); filterable by date range and shift; **PDF export** for management presentation
- **Records** — full history browser with manager-only edit capability (audit-trailed)

### Admin

- All of the above
- **User Management** — add users, assign roles, activate/deactivate accounts

---

## Fault Lifecycle (Two-Phase)

Faults go through two phases:

1. **Shift Lead logs fault** → `status = 'open'`, `downtime_minutes` = estimate
2. **Engineer validates fault** → `status = 'closed'`, `actual_downtime_minutes` = confirmed value, plus `root_cause`, `engineer_notes`, `closed_by`, `closed_at`

All OEE calculations and reports use `actual_downtime_minutes` when available, falling back to `downtime_minutes` (the shift-lead estimate) for faults not yet validated. This means historical data is never lost or broken when engineers validate after the fact.

---

## OEE Calculation

OEE = Availability × Performance × Quality

| Component    | Formula                                                      |
|--------------|--------------------------------------------------------------|
| Availability | `(actual_run_hrs - downtime_hrs) / actual_run_hrs`          |
| Performance  | `packs_produced / packs_target`                             |
| Quality      | `(packs_produced - packs_rejected) / packs_produced`        |

Downtime used = `actual_downtime_minutes` (engineer-confirmed) if available, else `downtime_minutes` (shift-lead estimate).

**Line Efficiency** (shown separately) = `packs_produced / packs_target × 100%` — the Performance component without availability or quality adjustment. Useful for a quick floor-level view.

| Metric     | Green  | Amber  | Red   |
|------------|--------|--------|-------|
| Efficiency | ≥ 85%  | ≥ 70%  | < 70% |
| OEE        | ≥ 85%  | ≥ 65%  | < 65% |

---

## Target Calculation

Targets are based on **actual run time**, not a fixed 8-hour shift:

```text
hourly_rate = HOURLY_LITRES (20,000 L/hr) ÷ bottle_litres ÷ bottles_per_case
run_target  = round(hourly_rate × actual_run_hours)
```

`packs_target` is set when a run is closed, so efficiency always reflects what was achievable in that specific window.

---

## Production Day Logic

The system uses a **production day** rather than a calendar day:

- Night shift (21:00–07:00) spans midnight — hours between 00:00 and 07:00 belong to the **previous** calendar day.
- All records are stamped with `production_day()`, not `date.today()`.

| Shift     | Window        |
|-----------|---------------|
| Morning   | 07:00 – 14:00 |
| Afternoon | 14:00 – 21:00 |
| Night     | 21:00 – 07:00 |

---

## Database Schema

| Table             | Purpose                                                           |
|-------------------|-------------------------------------------------------------------|
| `users`           | Accounts, roles, hashed passwords                                 |
| `production_runs` | One row per open/closed run (line, product, shift, targets, OEE)  |
| `fault_records`   | Faults with two-phase lifecycle (shift-lead estimate + engineer validation) |
| `shift_handovers` | One submission per user per shift; incoming brief for next shift   |

### Key `fault_records` columns

| Column                   | Notes                                                    |
|--------------------------|----------------------------------------------------------|
| `downtime_minutes`       | Shift-lead estimate (always present)                     |
| `status`                 | `open` (logged) / `closed` (engineer-validated)          |
| `actual_downtime_minutes`| Engineer-confirmed downtime (NULL until validated)       |
| `root_cause`             | Selected from standard taxonomy by engineer              |
| `engineer_notes`         | Resolution notes from engineer                           |
| `closed_by`              | Engineer username                                        |
| `closed_at`              | ISO timestamp of validation                              |

Migrations are applied automatically via `INFORMATION_SCHEMA.COLUMNS` checks on every startup — no manual SQL needed.

---

## Setup

### Local (development)

```bash
pip install -r requirements.txt
streamlit run app.py
```

### Docker (production / LAN deployment)

```bash
cp .env.example .env
# Fill in .env with SQL Server LAN IP, DB name, credentials
docker compose up -d --build
```

App accessible at `http://<server-lan-ip>:8501` from any device on the same network.

> **Windows Firewall:** allow inbound TCP on port 8501:
> ```powershell
> New-NetFirewallRule -DisplayName "Streamlit 8501" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow
> ```

---

## Environment Variables (`.env`)

```env

DB_BACKEND=mssql
DB_SERVER=192.168.x.x          # LAN IP of SQL Server (not localhost inside Docker)
DB_NAME=ritefoods_prod
DB_USER=your_user
DB_PASSWORD=your_password
DB_DRIVER=ODBC Driver 17 for SQL Server
```
