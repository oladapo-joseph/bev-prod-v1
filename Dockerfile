# ── Ritefoods Production Management System ────────────────────────────────────
FROM python:3.12-slim

# Install system dependencies for pyodbc + MSSQL ODBC driver
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    unixodbc \
    unixodbc-dev \
    && curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add - \
    && curl https://packages.microsoft.com/config/debian/11/prod.list \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y msodbcsql17 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Write Streamlit config inline — avoids missing file errors during build
RUN mkdir -p /app/.streamlit && cat > /app/.streamlit/config.toml << 'TOML'
[client]
toolbarMode = "minimal"

[server]
headless = true
enableCORS = false
enableXsrfProtection = false
port = 8501

[browser]
serverAddress = "0.0.0.0"
gatherUsageStats = false
TOML

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false"]