# 🏭 Ritefoods Limited — Production Management System

A real-time, role-based production management system built with Streamlit and SQL Server. Tracks production runs, faults/downtime, shift handovers, and OEE across 8 bottling lines.

---

## Project Structure

```text
project/
├── app.py                        # Entrypoint, login, sidebar, routing
├── config.py                     # SQL Server connection (pyodbc)
├── db.py                         # Schema + auto-migrations (production_runs, fault_records, shift_handovers)
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
│   └── ui.py                     # CSS injection, KPI widgets, OEE report builder
│
└── views/
    ├── log_production.py         # Open Run / Close Run + fault backfill
    ├── log_fault.py              # Independent fault logging with auto-run linking
    ├── shift_dashboard.py        # Live shift view: closed runs, active lines, faults
    ├── shift_handover.py         # End-of-shift KPI summary + handover comments
    ├── manager_overview.py       # Manager tabs: overview, production report, trends, faults, alerts
    ├── records.py                # Historical records browser + manager edit capability
    └── user_management.py        # Admin: create, deactivate, reset users
```

---

## Roles & Default Accounts

| Role       | Username   | Password     | Access                                                              |
|------------|------------|--------------|---------------------------------------------------------------------|
| Admin      | `admin`    | `admin123`   | Everything + User Management                                        |
| Manager    | `manager1` | `manager123` | Manager Overview, Records (with edit), all read-only views          |
| Shift Lead | `lead1`    | `lead123`    | Log Production, Log Fault, Shift Dashboard, Shift Handover, Records |
| Shift Lead | `lead2`    | `lead123`    | Same as above                                                       |

> **Change default passwords after first login** via User Management (admin only).

---

## Features

### Shift Lead

- **Log Production** — open and close production runs per line (1–8), shift, and product; confirmation summary before close; run-time-based case target recalculated at close
- **Log Fault** — log faults with area/machine, detail, downtime, and reporter; auto-linked to the active run on the selected line; shift and fault time auto-populated
- **Shift Dashboard** — live view of closed runs, active lines (estimated target + cases/hr), and today's faults grouped by shift
- **Shift Handover** — end-of-shift KPI strip (runs, cases, efficiency, faults, downtime, open lines), line-by-line summary, outgoing comments, and incoming brief from the previous shift

### Manager

- All of the above (read-only where applicable)
- **Records** — full history browser with manager-only edit capability (packs produced/rejected, target, notes); edits are audit-trailed
- **Manager Overview** — 5 tabs:
  - *All Lines* — real-time table of all 8 lines for any date
  - *Production Report* — closed runs filterable by date range and shift, with OEE metrics
  - *Trends* — 14-day bar charts for cases and efficiency
  - *Fault Analysis* — top fault categories and per-line downtime breakdown
  - *Alerts* — lines below 70% efficiency, unlinked faults, open runs

### Admin

- All of the above
- **User Management** — add users, assign roles, activate/deactivate accounts

---

## Target Calculation

Targets are based on **actual run time**, not a fixed 8-hour shift:

```text
hourly_rate = HOURLY_LITRES (20,000 L/hr) ÷ bottle_litres ÷ bottles_per_case
run_target  = round(hourly_rate × actual_run_hours)
```

`packs_target` is recalculated and stored when a run is closed, so the efficiency figure always reflects what was achievable in that specific window.

---

## Production Day Logic

The system uses a **production day** rather than a calendar day:

- Night shift (21:00–07:00) spans midnight — the hours between 00:00 and 07:00 belong to the **previous** calendar day's production day.
- All records (runs, faults, handovers) are stamped with `production_day()`, not `date.today()`.

---

## Shift Times

| Shift     | Window        |
|-----------|---------------|
| Morning   | 07:00 – 14:00 |
| Afternoon | 14:00 – 21:00 |
| Night     | 21:00 – 07:00 |

Shift selectors across all pages auto-populate with the current shift based on wall-clock time.

---

## Setup

### Local (development)

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in DB credentials in .env
streamlit run app.py
```

### Docker (production / LAN deployment)

```bash
cp .env.example .env
# Fill in .env with SQL Server LAN IP, DB name, credentials
docker compose up -d --build
```

App is accessible at `http://<server-lan-ip>:8501` from any device on the same network.

> **Tip:** assign a static IP to the server in your router's DHCP settings so the address never changes.
> **Windows Firewall:** if the network URL is unreachable from other devices, allow inbound traffic on port 8501:
>
> ```powershell
> New-NetFirewallRule -DisplayName "Streamlit 8501" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow
> ```

---

## Environment Variables (`.env`)

```env
DB_BACKEND=mssql
DB_SERVER=192.168.x.x          # LAN IP of the SQL Server machine (not localhost inside Docker)
DB_NAME=ritefoods_prod
DB_USER=your_user
DB_PASSWORD=your_password
DB_DRIVER=ODBC Driver 17 for SQL Server
```

Tables and columns are created and migrated automatically on first run — no manual SQL needed.

---

## Database Schema

| Table             | Purpose                                                           |
|-------------------|-------------------------------------------------------------------|
| `users`           | Accounts, roles, hashed passwords                                 |
| `production_runs` | One row per open/closed run (line, product, shift, targets, OEE)  |
| `fault_records`   | Faults linked (or unlinked) to a production run                   |
| `shift_handovers` | One submission per user per shift; incoming brief for next shift   |

Migrations are applied automatically via `INFORMATION_SCHEMA.COLUMNS` checks on startup.
