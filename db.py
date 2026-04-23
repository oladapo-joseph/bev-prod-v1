"""
db.py — Table creation, migrations, and default data seeding
-------------------------------------------------------------
Supports both SQL Server and SQLite backends (controlled by DB_BACKEND in config).
Call init_db() once at app startup.
"""

import hashlib
import secrets
from config import get_conn, DB_BACKEND


def hash_pw(password: str, salt: str = None):
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return hashed, salt


# ── Schema existence checks (backend-aware) ───────────────────────────────────

def _table_exists(cursor, table_name: str) -> bool:
    if DB_BACKEND == "sqlite":
        cursor.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
    else:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME=?",
            (table_name,)
        )
    return cursor.fetchone()[0] > 0


def _column_exists(cursor, table_name: str, column_name: str) -> bool:
    if DB_BACKEND == "sqlite":
        cursor.execute(f"PRAGMA table_info({table_name})")
        return any(row[1] == column_name for row in cursor.fetchall())
    else:
        cursor.execute(
            "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE TABLE_NAME=? AND COLUMN_NAME=?",
            (table_name, column_name)
        )
        return cursor.fetchone()[0] > 0


# ── DDL — SQL Server ──────────────────────────────────────────────────────────

USERS_DDL_MSSQL = """
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

RUNS_DDL_MSSQL = """
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

FAULTS_DDL_MSSQL = """
CREATE TABLE fault_records (
    id                      INT IDENTITY(1,1) PRIMARY KEY,
    production_run_id       INT,
    record_date             NVARCHAR(20)   NOT NULL,
    shift                   NVARCHAR(50)   NOT NULL,
    line_number             INT            NOT NULL,
    fault_time              NVARCHAR(10),
    fault_machine           NVARCHAR(100)  NOT NULL,
    fault_detail            NVARCHAR(200),
    downtime_minutes        INT            NOT NULL,
    reported_by             NVARCHAR(100)  NOT NULL,
    notes                   NVARCHAR(500),
    logged_by               NVARCHAR(50),
    status                  NVARCHAR(10)   DEFAULT 'open',
    actual_downtime_minutes INT,
    engineer_notes          NVARCHAR(1000),
    root_cause              NVARCHAR(100),
    closed_by               NVARCHAR(50),
    closed_at               NVARCHAR(30),
    created_at              NVARCHAR(30)   DEFAULT (CONVERT(NVARCHAR, GETDATE(), 120)),
    FOREIGN KEY (production_run_id) REFERENCES production_runs(id)
)"""

HANDOVERS_DDL_MSSQL = """
CREATE TABLE shift_handovers (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    record_date  NVARCHAR(20)  NOT NULL,
    shift        NVARCHAR(50)  NOT NULL,
    submitted_by NVARCHAR(50)  NOT NULL,
    full_name    NVARCHAR(100) NOT NULL,
    comments     NVARCHAR(2000),
    submitted_at NVARCHAR(30)  DEFAULT (CONVERT(NVARCHAR, GETDATE(), 120))
)"""

LINE_TARGETS_DDL_MSSQL = """
CREATE TABLE line_targets (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    line_number     INT           NOT NULL,
    litres_per_hour FLOAT         NOT NULL,
    effective_from  NVARCHAR(10)  NOT NULL,
    set_by          NVARCHAR(50),
    notes           NVARCHAR(300),
    created_at      NVARCHAR(30)  DEFAULT (CONVERT(NVARCHAR, GETDATE(), 120))
)"""


# ── DDL — SQLite ──────────────────────────────────────────────────────────────

USERS_DDL_SQLITE = """
CREATE TABLE users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    full_name     TEXT NOT NULL,
    role          TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    active        INTEGER DEFAULT 1,
    created_at    TEXT DEFAULT (datetime('now'))
)"""

RUNS_DDL_SQLITE = """
CREATE TABLE production_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    record_date     TEXT NOT NULL,
    shift           TEXT NOT NULL,
    closed_shift    TEXT,
    line_number     INTEGER NOT NULL,
    product_name    TEXT NOT NULL,
    flavor          TEXT,
    pack_size       TEXT,
    packaging       TEXT,
    packs_produced  INTEGER,
    packs_target    INTEGER,
    packs_rejected  INTEGER DEFAULT 0,
    run_start       TEXT NOT NULL,
    run_end         TEXT,
    plan_time_hrs   REAL,
    actual_time_hrs REAL,
    down_time_hrs   REAL,
    status          TEXT DEFAULT 'open',
    operator_name   TEXT,
    handover_note   TEXT,
    logged_by       TEXT,
    edited_by       TEXT,
    edited_at       TEXT,
    created_at      TEXT DEFAULT (datetime('now'))
)"""

FAULTS_DDL_SQLITE = """
CREATE TABLE fault_records (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    production_run_id       INTEGER,
    record_date             TEXT    NOT NULL,
    shift                   TEXT    NOT NULL,
    line_number             INTEGER NOT NULL,
    fault_time              TEXT,
    fault_machine           TEXT    NOT NULL,
    fault_detail            TEXT,
    downtime_minutes        INTEGER NOT NULL,
    reported_by             TEXT    NOT NULL,
    notes                   TEXT,
    logged_by               TEXT,
    status                  TEXT    DEFAULT 'open',
    actual_downtime_minutes INTEGER,
    engineer_notes          TEXT,
    root_cause              TEXT,
    closed_by               TEXT,
    closed_at               TEXT,
    created_at              TEXT    DEFAULT (datetime('now')),
    FOREIGN KEY (production_run_id) REFERENCES production_runs(id)
)"""

HANDOVERS_DDL_SQLITE = """
CREATE TABLE shift_handovers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    record_date  TEXT NOT NULL,
    shift        TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    full_name    TEXT NOT NULL,
    comments     TEXT,
    submitted_at TEXT DEFAULT (datetime('now'))
)"""

LINE_TARGETS_DDL_SQLITE = """
CREATE TABLE line_targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    line_number     INTEGER NOT NULL,
    litres_per_hour REAL    NOT NULL,
    effective_from  TEXT    NOT NULL,
    set_by          TEXT,
    notes           TEXT,
    created_at      TEXT    DEFAULT (datetime('now'))
)"""


# ── Column migrations ─────────────────────────────────────────────────────────
# Each entry: (column_name, mssql_type, sqlite_type)
RUNS_MIGRATIONS = [
    ("closed_shift",    "NVARCHAR(50)",  "TEXT"),
    ("packs_rejected",  "INT",           "INTEGER"),
    ("run_start",       "NVARCHAR(30)",  "TEXT"),
    ("run_end",         "NVARCHAR(30)",  "TEXT"),
    ("status",          "NVARCHAR(10)",  "TEXT"),
    ("handover_note",   "NVARCHAR(500)", "TEXT"),
    ("plan_time_hrs",   "FLOAT",         "REAL"),
    ("actual_time_hrs", "FLOAT",         "REAL"),
    ("down_time_hrs",   "FLOAT",         "REAL"),
    ("edited_by",       "NVARCHAR(50)",  "TEXT"),
    ("edited_at",       "NVARCHAR(30)",  "TEXT"),
]

FAULT_MIGRATIONS = [
    ("production_run_id",       "INT",            "INTEGER"),
    ("fault_time",              "NVARCHAR(10)",   "TEXT"),
    ("notes",                   "NVARCHAR(500)",  "TEXT"),
    ("fault_machine",           "NVARCHAR(100)",  "TEXT"),
    ("fault_detail",            "NVARCHAR(200)",  "TEXT"),
    ("status",                  "NVARCHAR(10)",   "TEXT"),
    ("actual_downtime_minutes", "INT",            "INTEGER"),
    ("engineer_notes",          "NVARCHAR(1000)", "TEXT"),
    ("root_cause",              "NVARCHAR(100)",  "TEXT"),
    ("closed_by",               "NVARCHAR(50)",   "TEXT"),
    ("closed_at",               "NVARCHAR(30)",   "TEXT"),
]

# Handles tables created before the litres_per_hour rename
LINE_TARGETS_MIGRATIONS = [
    ("litres_per_hour", "FLOAT", "REAL"),
]

DEFAULT_USERS = [
    ("admin",    "Admin User",    "admin",      "admin123"),
    ("manager1", "Plant Manager", "manager",    "manager123"),
    ("lead1",    "Shift Lead A",  "shift_lead", "lead123"),
    ("lead2",    "Shift Lead B",  "shift_lead", "lead123"),
]


# ── init_db ───────────────────────────────────────────────────────────────────

def init_db():
    is_sqlite = (DB_BACKEND == "sqlite")

    if is_sqlite:
        tables = [
            ("users",           USERS_DDL_SQLITE),
            ("production_runs", RUNS_DDL_SQLITE),
            ("fault_records",   FAULTS_DDL_SQLITE),
            ("shift_handovers", HANDOVERS_DDL_SQLITE),
            ("line_targets",    LINE_TARGETS_DDL_SQLITE),
        ]
    else:
        tables = [
            ("users",           USERS_DDL_MSSQL),
            ("production_runs", RUNS_DDL_MSSQL),
            ("fault_records",   FAULTS_DDL_MSSQL),
            ("shift_handovers", HANDOVERS_DDL_MSSQL),
            ("line_targets",    LINE_TARGETS_DDL_MSSQL),
        ]

    conn = get_conn()
    c    = conn.cursor()

    for table, ddl in tables:
        if not _table_exists(c, table):
            c.execute(ddl)

    # Column migrations — add missing columns to existing tables
    for col, mssql_type, sqlite_type in RUNS_MIGRATIONS:
        if not _column_exists(c, "production_runs", col):
            col_type = sqlite_type if is_sqlite else mssql_type
            c.execute(f"ALTER TABLE production_runs ADD {'COLUMN ' if is_sqlite else ''}{col} {col_type}")

    for col, mssql_type, sqlite_type in FAULT_MIGRATIONS:
        if not _column_exists(c, "fault_records", col):
            col_type = sqlite_type if is_sqlite else mssql_type
            c.execute(f"ALTER TABLE fault_records ADD {'COLUMN ' if is_sqlite else ''}{col} {col_type}")

    for col, mssql_type, sqlite_type in LINE_TARGETS_MIGRATIONS:
        if not _column_exists(c, "line_targets", col):
            col_type = sqlite_type if is_sqlite else mssql_type
            c.execute(f"ALTER TABLE line_targets ADD {'COLUMN ' if is_sqlite else ''}{col} {col_type}")

    # Backfill status for pre-migration rows
    c.execute("UPDATE fault_records SET status='open' WHERE status IS NULL")

    # Seed default users if the table is empty
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
