"""
db.py — Table creation, migrations, and default data seeding
-------------------------------------------------------------
SQL Server only. Call init_db() once at app startup.
"""

import hashlib
import secrets
from config import get_conn


def hash_pw(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return hashed, salt


def _table_exists(cursor, table_name: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?",
        (table_name,)
    )
    return cursor.fetchone()[0] > 0


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    cursor.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_NAME = ? AND COLUMN_NAME = ?",
        (table_name, column_name)
    )
    return cursor.fetchone()[0] > 0


USERS_DDL = """
CREATE TABLE users (
    id            INT IDENTITY(1,1) PRIMARY KEY,
    username      NVARCHAR(50)  UNIQUE NOT NULL,
    full_name     NVARCHAR(100) NOT NULL,
    role          NVARCHAR(20)  NOT NULL,
    password_hash NVARCHAR(64)  NOT NULL,
    salt          NVARCHAR(64)  NOT NULL,
    active        INT           DEFAULT 1,
    created_at    NVARCHAR(30)  DEFAULT (CONVERT(NVARCHAR, GETDATE(), 120))
)"""

# shift        = shift the run was OPENED in
# closed_shift = shift the run was CLOSED in (may differ for cross-shift runs)
PRODUCTION_RUNS_DDL = """
CREATE TABLE production_runs (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    record_date     NVARCHAR(20)  NOT NULL,
    shift           NVARCHAR(50)  NOT NULL,
    closed_shift    NVARCHAR(50),
    line_number     INT           NOT NULL,
    product_name    NVARCHAR(100) NOT NULL,
    flavor          NVARCHAR(100),
    pack_size       NVARCHAR(20),
    packaging       NVARCHAR(20),
    packs_produced  INT,
    packs_target    INT,
    packs_rejected  INT  DEFAULT 0,
    run_start       NVARCHAR(30)  NOT NULL,
    run_end         NVARCHAR(30),
    plan_time_hrs   FLOAT,
    actual_time_hrs FLOAT,
    down_time_hrs   FLOAT,
    status          NVARCHAR(10)  DEFAULT 'open',
    operator_name   NVARCHAR(100),
    handover_note   NVARCHAR(500),
    logged_by       NVARCHAR(50),
    created_at      NVARCHAR(30)  DEFAULT (CONVERT(NVARCHAR, GETDATE(), 120))
)"""

FAULTS_DDL = """
CREATE TABLE fault_records (
    id                  INT IDENTITY(1,1) PRIMARY KEY,
    production_run_id   INT,
    record_date         NVARCHAR(20)  NOT NULL,
    shift               NVARCHAR(50)  NOT NULL,
    line_number         INT           NOT NULL,
    fault_time          NVARCHAR(10),
    fault_machine       NVARCHAR(100) NOT NULL,
    fault_detail        NVARCHAR(200),
    downtime_minutes    INT           NOT NULL,
    reported_by         NVARCHAR(100) NOT NULL,
    notes               NVARCHAR(500),
    logged_by           NVARCHAR(50),
    created_at          NVARCHAR(30)  DEFAULT (CONVERT(NVARCHAR, GETDATE(), 120)),
    FOREIGN KEY (production_run_id) REFERENCES production_runs(id)
)"""


RUNS_MIGRATIONS = [
    ("closed_shift",    "NVARCHAR(50)"),
    ("packs_rejected",  "INT"),
    ("run_start",       "NVARCHAR(30)"),
    ("run_end",         "NVARCHAR(30)"),
    ("status",          "NVARCHAR(10)"),
    ("handover_note",   "NVARCHAR(500)"),
    ("plan_time_hrs",   "FLOAT"),
    ("actual_time_hrs", "FLOAT"),
    ("down_time_hrs",   "FLOAT"),
    ("edited_by",       "NVARCHAR(50)"),
    ("edited_at",       "NVARCHAR(30)"),
]

FAULT_MIGRATIONS = [
    ("production_run_id", "INT"),
    ("fault_time",        "NVARCHAR(10)"),
    ("notes",             "NVARCHAR(500)"),
    ("fault_machine",     "NVARCHAR(100)"),
    ("fault_detail",      "NVARCHAR(200)"),
]

DEFAULT_USERS = [
    ("admin",    "Admin User",    "admin",      "admin123"),
    ("manager1", "Plant Manager", "manager",    "manager123"),
    ("lead1",    "Shift Lead A",  "shift_lead", "lead123"),
    ("lead2",    "Shift Lead B",  "shift_lead", "lead123"),
]


def init_db():
    conn = get_conn()
    c    = conn.cursor()

    for table, ddl in [
        ("users",           USERS_DDL),
        ("production_runs", PRODUCTION_RUNS_DDL),
        ("fault_records",   FAULTS_DDL),
    ]:
        if not _table_exists(c, table):
            c.execute(ddl)

    for col, typ in RUNS_MIGRATIONS:
        if not _column_exists(c, "production_runs", col):
            c.execute(f"ALTER TABLE production_runs ADD {col} {typ}")

    for col, typ in FAULT_MIGRATIONS:
        if not _column_exists(c, "fault_records", col):
            c.execute(f"ALTER TABLE fault_records ADD {col} {typ}")

    c.execute("SELECT COUNT(*) FROM users")
    if c.fetchone()[0] == 0:
        for username, full_name, role, pw in DEFAULT_USERS:
            h, s = hash_pw(pw)
            c.execute(
                "INSERT INTO users (username, full_name, role, password_hash, salt) "
                "VALUES (?, ?, ?, ?, ?)",
                (username, full_name, role, h, s)
            )

    conn.commit()
    conn.close()