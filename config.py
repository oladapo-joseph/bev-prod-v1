"""
config.py — Database connection (SQL Server or SQLite)
------------------------------------------------------
Backend is selected by the DB_BACKEND environment variable (or secret):

    DB_BACKEND=mssql    (default) — connects to SQL Server via pyodbc
    DB_BACKEND=sqlite             — connects to a local SQLite file

Credential resolution order (first non-empty value wins):
    1. .env file (local dev)
    2. OS environment variables (Docker, Railway, Render, Fly.io)
    3. st.secrets (Streamlit Cloud)

SQL Server variables:
    DB_SERVER, DB_NAME, DB_USER, DB_PASSWORD
    DB_DRIVER  (default: ODBC Driver 17 for SQL Server)

SQLite variables:
    SQLITE_PATH  (default: production.db)
"""

import os
import sqlite3
import pandas as pd
import streamlit as st
from dotenv import dotenv_values

_env = dotenv_values(".env")


def _secret(key: str, default: str = "") -> str:
    """Read a config value from .env → os.environ → st.secrets, in that order."""
    val = _env.get(key) or os.getenv(key)
    if not val:
        try:
            val = st.secrets.get(key)
        except Exception:
            pass
    return val or default


DB_BACKEND  = _secret("DB_BACKEND", "mssql").lower()
SQLITE_PATH = _secret("SQLITE_PATH", "production.db")


# ══════════════════════════════════════════════════════════════════════════════
# SQLite backend
# ══════════════════════════════════════════════════════════════════════════════

if DB_BACKEND == "sqlite":

    def get_conn() -> sqlite3.Connection:
        conn = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def read_sql(query: str, params: list | tuple | None = None) -> pd.DataFrame:
        conn = get_conn()
        try:
            return pd.read_sql_query(query, conn, params=params or [])
        except Exception as e:
            st.error(f"❌ Query failed: {e}")
            raise
        finally:
            conn.close()

    def execute(query: str, params: list | tuple | None = None) -> None:
        conn = get_conn()
        try:
            cur = conn.cursor()
            cur.execute(query, params or [])
            conn.commit()
        except Exception as e:
            conn.rollback()
            st.error(f"❌ Execute failed: {e}")
            raise
        finally:
            conn.close()


# ══════════════════════════════════════════════════════════════════════════════
# SQL Server backend (default)
# ══════════════════════════════════════════════════════════════════════════════

else:
    import urllib.parse
    import pyodbc
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import QueuePool

    _SERVER   = _secret("DB_SERVER")
    _DATABASE = _secret("DB_NAME")
    _USER     = _secret("DB_USER")
    _PASSWORD = _secret("DB_PASSWORD")
    _DRIVER   = _secret("DB_DRIVER", "ODBC Driver 17 for SQL Server")

    def _build_odbc_str() -> str:
        return (
            f"DRIVER={{{_DRIVER}}};"
            f"SERVER={_SERVER};"
            f"DATABASE={_DATABASE};"
            f"UID={_USER};"
            f"PWD={_PASSWORD};"
            f"TrustServerCertificate=yes;"
            f"Encrypt=yes;"
        )

    @st.cache_resource(show_spinner="Connecting to database…")
    def _get_engine():
        """
        Creates a SQLAlchemy engine with a QueuePool (5 persistent + 10 overflow).
        Cached for the lifetime of the Streamlit server process — all users share
        the same pool instead of opening a new TCP connection per query.
        pool_pre_ping=True silently replaces stale connections before use.
        pool_recycle=1800 drops and recreates connections idle for >30 min.
        """
        odbc_str = _build_odbc_str()
        engine = create_engine(
            f"mssql+pyodbc:///?odbc_connect={urllib.parse.quote_plus(odbc_str)}",
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            pool_recycle=1800,
        )
        # Smoke-test on startup
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        return engine

    def get_conn():
        """
        Returns a DBAPI (pyodbc) connection drawn from the pool.
        Callers must call .close() when done — this returns it to the pool,
        not to SQL Server, so there is no TCP overhead.
        """
        try:
            return _get_engine().raw_connection()
        except Exception as e:
            st.error(f"❌ Database connection failed: {e}")
            raise

    def read_sql(query: str, params: list | tuple | None = None) -> pd.DataFrame:
        conn = get_conn()
        try:
            if params:
                return pd.read_sql(query, conn, params=params)
            return pd.read_sql(query, conn)
        except Exception as e:
            st.error(f"❌ Query failed: {e}")
            raise
        finally:
            conn.close()

    def execute(query: str, params: list | tuple | None = None) -> None:
        conn = get_conn()
        try:
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            conn.commit()
        except Exception as e:
            conn.rollback()
            st.error(f"❌ Execute failed: {e}")
            raise
        finally:
            conn.close()
