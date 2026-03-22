# 🏭 LineTrack — Modular Bottling Production App

## Project Structure

```
linetrack/
├── app.py                        # Entrypoint, login, sidebar, routing
├── config.py                     # SQL Server connection (pyodbc)
├── db.py                         # Schema: production_runs + fault_records
├── auth.py                       # Login / session helpers
├── requirements.txt
├── .env.example                  # DB credentials template
│
├── data/
│   └── reference.py              # Products, fault taxonomy, targets
│
├── components/
│   └── ui.py                     # CSS, widgets, report builder
│
└── views/
    ├── log_production.py         # ▶️ Open Run / ✅ Close Run + fault backfill
    ├── log_fault.py              # ⚠️ Independent fault logging with fault_time
    ├── shift_dashboard.py        # 📊 Shift view
    ├── manager_overview.py       # 🏭 Manager tabs (5)
    ├── records.py                # 📁 Historical records
    └── user_management.py        # 👤 Admin user management
```
## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment
```bash
cp .env.example .env
# Edit .env with your settings
```

### 3. Run
```bash
streamlit run app.py
```

---

## Database Backends

### SQLite (default — development)
```env
DB_BACKEND=sqlite
SQLITE_PATH=production.db
```
No extra install needed. Data is stored in a local file.

### SQL Server (production)
```env
DB_BACKEND=mssql
DB_SERVER=your-server.database.windows.net
DB_NAME=linetrack
DB_USER=linetrack_user
DB_PASSWORD=your-password
DB_DRIVER=ODBC Driver 17 for SQL Server
```

Install additional dependencies:
```bash
pip install pyodbc sqlalchemy
```

Also install the ODBC driver on your server:
- **Windows**: [Microsoft ODBC Driver 17](https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server)
- **Linux/Ubuntu**:
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
curl https://packages.microsoft.com/config/ubuntu/22.04/prod.list > /etc/apt/sources.list.d/mssql-release.list
apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql17
```

Tables and columns are created automatically on first run — no manual SQL needed.

---

## Default Accounts

| Role        | Username   | Password     |
|-------------|------------|--------------|
| Admin       | `admin`    | `admin123`   |
| Manager     | `manager1` | `manager123` |
| Shift Lead  | `lead1`    | `lead123`    |
| Shift Lead  | `lead2`    | `lead123`    |

> Change default passwords after first login via **User Management**.