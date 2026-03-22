"""
config.py — SQL Server database connection
------------------------------------------
All credentials are loaded from a .env file (or environment variables).

Required .env variables:
    DB_SERVER   — SQL Server host, e.g. 192.168.1.10 or myserver.database.windows.net
    DB_NAME     — Database name, e.g. linetrack
    DB_USER     — SQL Server login username
    DB_PASSWORD — SQL Server login password
    DB_DRIVER   — ODBC driver name (default: ODBC Driver 17 for SQL Server)

Install dependencies:
    pip install pyodbc pandas python-dotenv

Install ODBC driver:
    Windows : https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server
    Ubuntu  : sudo ACCEPT_EULA=Y apt-get install -y msodbcsql17
"""

import os
import pyodbc
import pandas as pd
import streamlit as st
from dotenv import load_dotenv, dotenv_values

env = dotenv_values('.env')

# ── Connection settings from environment ─────────────────────────────────────
_SERVER   = env['DB_SERVER'] 
_DATABASE = env["DB_NAME"]
_USER     = env["DB_USER"]
_PASSWORD = env["DB_PASSWORD"]
_DRIVER   = env["DB_DRIVER"]


def _build_conn_str() -> str:
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
    Create and cache a single pyodbc connection pool representative.
    Returns a callable that produces fresh connections from the same config.
    Cached once per Streamlit session — reconnects automatically on failure
    via pool_pre_ping equivalent (autocommit=False, connection tested on use).
    """
    conn_str = _build_conn_str()
    # Verify the connection is reachable at startup
    test = pyodbc.connect(conn_str, timeout=10)
    test.close()
    return conn_str   # store the string; each get_conn() opens a fresh connection


def get_conn() -> pyodbc.Connection:
    """
    Return a live pyodbc connection to SQL Server.
    Call conn.close() after use (handled inside read_sql and execute).
    """
    try:
        conn_str = _get_engine()
        return pyodbc.connect(conn_str, timeout=15)
    except pyodbc.Error as e:
        st.error(f"❌ Database connection failed: {e}")
        raise


def read_sql(query: str, params: list | tuple | None = None) -> pd.DataFrame:
    """
    Execute a SELECT query and return results as a DataFrame.
    Uses ? placeholders for parameters (pyodbc standard).

    Example:
        df = read_sql("SELECT * FROM users WHERE username = ?", params=["admin"])
    """
    conn = get_conn()
    try:
        if params:
            return pd.read_sql(query, conn, params=params)
        return pd.read_sql(query, conn)
    except pyodbc.Error as e:
        st.error(f"❌ Query failed: {e}")
        raise
    finally:
        conn.close()


def execute(query: str, params: list | tuple | None = None) -> None:
    """
    Execute an INSERT / UPDATE / DELETE / DDL statement and commit.
    Uses ? placeholders for parameters (pyodbc standard).

    Example:
        execute("INSERT INTO users (username) VALUES (?)", params=["lead3"])
    """
    conn = get_conn()
    try:
        cursor = conn.cursor()
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        conn.commit()
    except pyodbc.Error as e:
        conn.rollback()
        st.error(f"❌ Execute failed: {e}")
        raise
    finally:
        conn.close()