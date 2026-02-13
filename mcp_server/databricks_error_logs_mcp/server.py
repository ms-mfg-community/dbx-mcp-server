"""
Databricks Error Log Search MCP Server

This MCP server provides tools for searching and analyzing application
error logs stored in a Databricks Delta table. It enables developers to
get error context directly from GitHub Copilot.

Supports two modes:
  - stdio transport (local dev, default)
  - streamable-http transport (Azure / remote hosting)

Databricks configuration can be provided via:
  1. Environment variables (local dev fallback)
  2. HTTP headers per-request (X-Databricks-Host, X-Databricks-Token, etc.)
  3. The configure_databricks tool (session-based config)
"""

import os
import re
import sys
import time
from typing import Optional

from databricks.sdk import WorkspaceClient
from mcp.server.fastmcp import FastMCP, Context
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class DatabricksConfig(BaseModel):
    """Validated Databricks connection configuration."""
    host: str = Field(description="Databricks workspace URL")
    token: str = Field(description="Databricks personal access token")
    warehouse_id: str = Field(description="SQL warehouse ID")
    catalog: str = Field(default="dbx_1", description="Unity Catalog name")
    schema_name: str = Field(default="default", description="Schema name")


class ErrorLog(BaseModel):
    """A single error log entry."""
    timestamp: str = Field(description="When the error occurred (UTC)")
    error_code: str = Field(description="Error code (e.g., CC-1001)")
    file_path: str = Field(description="File where error occurred")
    severity: str = Field(
        description="Severity level: Warning, Error, or Event"
    )
    message: str = Field(description="Error message")
    source_file: str = Field(default="", description="Log file name")


class ErrorSearchResult(BaseModel):
    """Search result for errors."""
    total_found: int = Field(description="Total number of matching errors")
    results: list[ErrorLog] = Field(description="Error log entries")
    query: str = Field(description="Description of the query executed")


class ErrorFrequency(BaseModel):
    """Error frequency statistics."""
    error_code: str = Field(description="Error code")
    severity: str = Field(description="Severity level")
    count: int = Field(description="Number of occurrences")


class SeveritySummary(BaseModel):
    """Summary of errors for one severity level."""
    severity: str = Field(description="Severity level")
    error_count: int = Field(description="Total errors")
    unique_codes: int = Field(description="Distinct error codes")


# ---------------------------------------------------------------------------
# Session-level config store (for configure_databricks tool)
# ---------------------------------------------------------------------------
_session_configs: dict[str, DatabricksConfig] = {}

# ---------------------------------------------------------------------------
# Sanitisation helper
# ---------------------------------------------------------------------------
_SAFE_PATTERN = re.compile(r"^[A-Za-z0-9_./ -]+$")


def _sanitize(value: str) -> str:
    """Basic SQL injection prevention for string-interpolated values."""
    cleaned = value.replace("'", "''")
    if not _SAFE_PATTERN.match(cleaned):
        raise ValueError(f"Invalid characters in query parameter: {value}")
    return cleaned


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def _resolve_config(ctx: Optional[Context] = None) -> DatabricksConfig:
    """Resolve Databricks configuration from headers, session, or env vars.

    Priority: HTTP headers > session config > environment variables.
    """
    host = os.getenv("DATABRICKS_HOST", "")
    token = os.getenv("DATABRICKS_TOKEN", "")
    warehouse_id = os.getenv("DATABRICKS_WAREHOUSE_ID", "")
    catalog = os.getenv("DATABRICKS_CATALOG", "dbx_1")
    schema_name = os.getenv("DATABRICKS_SCHEMA", "default")

    # Try session config
    if ctx is not None:
        session_id = getattr(
            getattr(ctx, "request_context", None), "session_id", None
        ) or id(ctx)
        session_cfg = _session_configs.get(str(session_id))
        if session_cfg:
            return session_cfg

    # Try HTTP headers (available when running streamable-http transport)
    if ctx is not None:
        req = getattr(
            getattr(ctx, "request_context", None), "request", None
        )
        if req is not None:
            headers = getattr(req, "headers", {})
            host = headers.get("x-databricks-host", host)
            token = headers.get("x-databricks-token", token)
            warehouse_id = headers.get(
                "x-databricks-warehouse-id", warehouse_id
            )
            catalog = headers.get("x-databricks-catalog", catalog)
            schema_name = headers.get("x-databricks-schema", schema_name)

    return DatabricksConfig(
        host=host,
        token=token,
        warehouse_id=warehouse_id,
        catalog=catalog,
        schema_name=schema_name,
    )


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------

def _execute_query(
    cfg: DatabricksConfig, sql: str
) -> list[dict]:
    """Execute a SQL query against a Databricks SQL warehouse."""
    if not cfg.host or not cfg.token or not cfg.warehouse_id:
        return []

    try:
        client = WorkspaceClient(host=cfg.host, token=cfg.token)
        response = client.statement_execution.execute_statement(
            warehouse_id=cfg.warehouse_id,
            statement=sql,
            catalog=cfg.catalog,
            schema=cfg.schema_name,
        )

        while (
            response.status
            and response.status.state in ("RUNNING", "QUEUED")
        ):
            time.sleep(0.5)
            if response.statement_id:
                response = client.statement_execution.get_statement(
                    response.statement_id
                )

        if not response.result or not response.result.data_array:
            return []
        if (
            not response.manifest
            or not response.manifest.schema
            or not response.manifest.schema.columns
        ):
            return []

        columns = [
            col.name for col in response.manifest.schema.columns
        ]
        return [
            dict(zip(columns, row if isinstance(row, list) else list(row)))
            for row in response.result.data_array
        ]
    except Exception as e:
        print(f"Query error: {e}", file=sys.stderr)
        return []


def _fqn(cfg: DatabricksConfig, table: str) -> str:
    """Return the fully-qualified table/view name."""
    return f"{cfg.catalog}.{cfg.schema_name}.{table}"


# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

def _get_transport() -> str:
    """Get the transport mode from environment."""
    return os.getenv("MCP_TRANSPORT", "stdio")


def _get_port() -> int:
    """Get the server port from environment."""
    return int(os.getenv("MCP_SERVER_PORT", "8000"))


def _get_host() -> str:
    """Get the server host from environment."""
    return os.getenv("MCP_SERVER_HOST", "0.0.0.0")


mcp = FastMCP(
    "databricks-error-logs",
    host=_get_host(),
    port=_get_port(),
)

TABLE_NAME = "error_logs_parsed"


@mcp.tool()
async def configure_databricks(
    host: str,
    token: str,
    warehouse_id: str,
    catalog: str = "dbx_1",
    schema_name: str = "default",
    ctx: Context = None,
) -> str:
    """
    Set Databricks connection details for this session.

    Use this tool if you cannot pass HTTP headers. The configuration
    persists for the lifetime of the MCP session.

    Args:
        host: Databricks workspace URL (e.g. https://adb-xxx.azuredatabricks.net)
        token: Databricks personal access token
        warehouse_id: SQL warehouse ID
        catalog: Unity Catalog name (default: dbx_1)
        schema_name: Schema name (default: default)
    """
    cfg = DatabricksConfig(
        host=host,
        token=token,
        warehouse_id=warehouse_id,
        catalog=catalog,
        schema_name=schema_name,
    )

    session_id = str(
        getattr(
            getattr(ctx, "request_context", None), "session_id", None
        )
        or id(ctx)
    )
    _session_configs[session_id] = cfg

    return (
        f"Databricks configured for session. "
        f"Host: {host}, Catalog: {catalog}.{schema_name}, "
        f"Warehouse: {warehouse_id}"
    )


@mcp.tool()
async def search_error_logs(
    error_code: Optional[str] = None,
    severity: Optional[str] = None,
    file_path: Optional[str] = None,
    message_contains: Optional[str] = None,
    limit: int = 20,
    ctx: Context = None,
) -> ErrorSearchResult:
    """
    Search for error logs by various criteria.

    Args:
        error_code: Filter by error code (e.g., 'CC-1001')
        severity: Filter by severity ('Warning', 'Error', 'Event')
        file_path: Filter by file path (partial match)
        message_contains: Search for text in error message
        limit: Maximum number of results to return
    """
    cfg = _resolve_config(ctx)
    where = []

    if error_code:
        where.append(f"error_code = '{_sanitize(error_code)}'")
    if severity:
        where.append(f"severity = '{_sanitize(severity)}'")
    if file_path:
        where.append(f"file_path LIKE '%{_sanitize(file_path)}%'")
    if message_contains:
        where.append(f"message LIKE '%{_sanitize(message_contains)}%'")

    clause = ("WHERE " + " AND ".join(where)) if where else ""
    safe_limit = max(1, min(int(limit), 100))

    sql = (
        f"SELECT timestamp, error_code, file_path, severity, "
        f"message, source_file "
        f"FROM {_fqn(cfg, TABLE_NAME)} {clause} "
        f"ORDER BY timestamp DESC LIMIT {safe_limit}"
    )

    rows = _execute_query(cfg, sql)
    logs = [
        ErrorLog(
            timestamp=str(r.get("timestamp", "")),
            error_code=r.get("error_code", ""),
            file_path=r.get("file_path", ""),
            severity=r.get("severity", ""),
            message=r.get("message", ""),
            source_file=r.get("source_file", ""),
        )
        for r in rows
    ]

    return ErrorSearchResult(
        total_found=len(logs),
        results=logs,
        query=(
            f"error_code={error_code}, severity={severity}, "
            f"file={file_path}, message={message_contains}"
        ),
    )


@mcp.tool()
async def get_error_frequency(
    severity: Optional[str] = None,
    limit: int = 10,
    ctx: Context = None,
) -> list[ErrorFrequency]:
    """
    Get most frequently occurring error codes with statistics.

    Args:
        severity: Filter by severity level ('Warning', 'Error', 'Event')
        limit: Maximum number of error codes to return
    """
    cfg = _resolve_config(ctx)
    where = f"WHERE severity = '{_sanitize(severity)}'" if severity else ""
    safe_limit = max(1, min(int(limit), 100))

    sql = (
        f"SELECT error_code, severity, COUNT(*) as count "
        f"FROM {_fqn(cfg, TABLE_NAME)} {where} "
        f"GROUP BY error_code, severity "
        f"ORDER BY count DESC LIMIT {safe_limit}"
    )

    rows = _execute_query(cfg, sql)
    return [
        ErrorFrequency(
            error_code=r.get("error_code", ""),
            severity=r.get("severity", ""),
            count=int(r.get("count", 0)),
        )
        for r in rows
    ]


@mcp.tool()
async def get_severity_summary(
    ctx: Context = None,
) -> list[SeveritySummary]:
    """
    Get a summary of errors grouped by severity level.
    """
    cfg = _resolve_config(ctx)

    sql = (
        f"SELECT severity, COUNT(*) as error_count, "
        f"COUNT(DISTINCT error_code) as unique_codes "
        f"FROM {_fqn(cfg, TABLE_NAME)} "
        f"GROUP BY severity ORDER BY error_count DESC"
    )

    rows = _execute_query(cfg, sql)
    return [
        SeveritySummary(
            severity=r.get("severity", "Unknown"),
            error_count=int(r.get("error_count", 0)),
            unique_codes=int(r.get("unique_codes", 0)),
        )
        for r in rows
    ]


@mcp.tool()
async def get_file_errors(
    file_path: str,
    limit: int = 50,
    ctx: Context = None,
) -> ErrorSearchResult:
    """
    Get all errors from a specific application file.

    Args:
        file_path: Path to the file (e.g., 'app/src/main.py')
        limit: Maximum number of errors to return
    """
    cfg = _resolve_config(ctx)
    safe_limit = max(1, min(int(limit), 100))
    safe_path = _sanitize(file_path)

    sql = (
        f"SELECT timestamp, error_code, file_path, severity, "
        f"message, source_file "
        f"FROM {_fqn(cfg, TABLE_NAME)} "
        f"WHERE file_path = '{safe_path}' "
        f"ORDER BY timestamp DESC LIMIT {safe_limit}"
    )

    rows = _execute_query(cfg, sql)
    logs = [
        ErrorLog(
            timestamp=str(r.get("timestamp", "")),
            error_code=r.get("error_code", ""),
            file_path=r.get("file_path", ""),
            severity=r.get("severity", ""),
            message=r.get("message", ""),
            source_file=r.get("source_file", ""),
        )
        for r in rows
    ]

    return ErrorSearchResult(
        total_found=len(logs),
        results=logs,
        query=f"Errors in file: {file_path}",
    )


@mcp.tool()
async def search_by_message(
    query: str,
    limit: int = 50,
    ctx: Context = None,
) -> ErrorSearchResult:
    """
    Full-text search for errors by message content.

    Args:
        query: Text to search for in error messages (e.g., 'connection timeout')
        limit: Maximum number of results
    """
    cfg = _resolve_config(ctx)
    safe_limit = max(1, min(int(limit), 100))
    safe_query = _sanitize(query)

    sql = (
        f"SELECT timestamp, error_code, file_path, severity, "
        f"message, source_file "
        f"FROM {_fqn(cfg, TABLE_NAME)} "
        f"WHERE message LIKE '%{safe_query}%' "
        f"ORDER BY timestamp DESC LIMIT {safe_limit}"
    )

    rows = _execute_query(cfg, sql)
    logs = [
        ErrorLog(
            timestamp=str(r.get("timestamp", "")),
            error_code=r.get("error_code", ""),
            file_path=r.get("file_path", ""),
            severity=r.get("severity", ""),
            message=r.get("message", ""),
            source_file=r.get("source_file", ""),
        )
        for r in rows
    ]

    return ErrorSearchResult(
        total_found=len(logs),
        results=logs,
        query=f"Message contains: {query}",
    )


@mcp.tool()
async def search_by_time_range(
    hours_ago: int = 24,
    severity: Optional[str] = None,
    ctx: Context = None,
) -> ErrorSearchResult:
    """
    Search errors within a specific time range.

    Args:
        hours_ago: How many hours back to search (e.g., 24 for last day)
        severity: Optional severity filter ('Warning', 'Error', 'Event')
    """
    cfg = _resolve_config(ctx)
    safe_hours = max(1, min(int(hours_ago), 8760))

    sev_clause = ""
    if severity:
        sev_clause = f" AND severity = '{_sanitize(severity)}'"

    sql = (
        f"SELECT timestamp, error_code, file_path, severity, "
        f"message, source_file "
        f"FROM {_fqn(cfg, TABLE_NAME)} "
        f"WHERE timestamp >= current_timestamp() - INTERVAL {safe_hours} HOURS"
        f"{sev_clause} "
        f"ORDER BY timestamp DESC LIMIT 50"
    )

    rows = _execute_query(cfg, sql)
    logs = [
        ErrorLog(
            timestamp=str(r.get("timestamp", "")),
            error_code=r.get("error_code", ""),
            file_path=r.get("file_path", ""),
            severity=r.get("severity", ""),
            message=r.get("message", ""),
            source_file=r.get("source_file", ""),
        )
        for r in rows
    ]

    return ErrorSearchResult(
        total_found=len(logs),
        results=logs,
        query=f"Errors in last {safe_hours} hours (severity={severity})",
    )


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main():
    """Run the MCP server.

    Transport is selected via the MCP_TRANSPORT environment variable:
      - "stdio"           (default) — for local dev / VS Code / Claude Desktop
      - "streamable-http" — for Azure Container Apps / remote hosting
    """
    transport = _get_transport()

    if transport == "streamable-http":
        # Add a /health endpoint alongside the MCP app for probes
        import anyio
        import uvicorn
        from contextlib import asynccontextmanager
        from starlette.applications import Starlette
        from starlette.responses import JSONResponse
        from starlette.routing import Mount, Route

        async def health(_request):
            return JSONResponse({"status": "healthy"})

        # Wrap the MCP session manager lifespan so it initializes properly
        @asynccontextmanager
        async def lifespan(_app):
            async with mcp.session_manager.run():
                yield

        mcp_http_app = mcp.streamable_http_app()

        app = Starlette(
            routes=[
                Route("/health", health, methods=["GET"]),
                Mount("/", app=mcp_http_app),
            ],
            lifespan=lifespan,
        )

        async def _serve():
            config = uvicorn.Config(
                app,
                host=_get_host(),
                port=_get_port(),
                log_level="info",
            )
            server = uvicorn.Server(config)
            await server.serve()

        anyio.run(_serve)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
