# ABIET - API and web UI in one image.
# Debian bookworm is pinned because Microsoft publishes the SQL Server ODBC driver for it.
FROM python:3.11-slim-bookworm

ARG INSTALL_MSSQL_DRIVER=true

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DATA_DIR=/app/data

WORKDIR /app

# unixODBC + Microsoft ODBC Driver 18 for SQL Server (pyodbc)
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg unixodbc \
    && if [ "$INSTALL_MSSQL_DRIVER" = "true" ]; then \
         curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
         && curl -fsSL https://packages.microsoft.com/config/debian/12/prod.list -o /etc/apt/sources.list.d/mssql-release.list \
         && apt-get update \
         && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18; \
       fi \
    && apt-get purge -y --auto-remove gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ ./backend/
COPY ai/ ./ai/
COPY frontend/ ./frontend/

RUN useradd --create-home --uid 10001 abiet \
    && mkdir -p /app/data \
    && chown abiet:abiet /app/data
USER abiet
VOLUME ["/app/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4)" || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
