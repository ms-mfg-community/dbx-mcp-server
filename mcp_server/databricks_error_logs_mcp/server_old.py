"""
Databricks Error Log Search MCP Server

This MCP server provides tools for searching and analyzing application
error logs stored in a Databricks Delta table. It enables developers to
get error context directly from GitHub Copilot.
"""

import os
import time
from typing import Optional
from databricks.sdk import WorkspaceClient
from pydantic import BaseModel, Field
from mcp import FastMCP

# Initialize MCP Server
mcp = FastMCP(
    "databricks-error-logs",
    capabilities={
        "tools": {},
        "resources": {},
        "prompts": {},
    }
)

# Initialize Databricks client
try:
    w = WorkspaceClient(
        host=os.getenv("DATABRICKS_HOST"),
        token=os.getenv("DATABRICKS_TOKEN"),
    )
except Exception as e:
    w = None
    print(f"Warning: Could not initialize Databricks client: {e}")

# Configuration
CATALOG = os.getenv("DATABRICKS_CATALOG", "dbx_1")
SCHEMA = os.getenv("DATABRICKS_SCHEMA", "default")
TABLE_NAME = "error_logs_parsed"
WAREHOUSE_ID = os.getenv("DATABRICKS_WAREHOUSE_ID")


class ErrorLog(BaseModel):
    """Error log entry"""
    timestamp: str = Field(description="When the error occurred (UTC)")
    error_code: str = Field(description="Error code (e.g., CC-1001)")
    file_path: str = Field(description="File where error occurred")
    severity: str = Field(
        description="Severity level: Warning, Error, or Event"
    )
    message: str = Field(description="Error message")
    source_file: str = Field(description="Log file name")


class ErrorSearchResult(BaseModel):
    """Search result for errors"""
    total_found: int = Field(description="Total number of matching errors")
    results: list[ErrorLog] = Field(description="Error log entries")
    query: str = Field(description="Query that was executed")


class ErrorFrequency(BaseModel):
    """Error frequency statistics"""
    error_code: str = Field(description="Error code")
    severity: str = Field(description="Severity level")
    occurrence_count: int = Field(
        description="Number of times this error occurred"
    )
    affected_files: int = Field(description="Number of files affected")
    files: list[str] = Field(description="Files where error occurred")
    first_occurrence: str = Field(description="When first seen")
    last_occurrence: str = Field(description="When last seen")


class ErrorPattern(BaseModel):
    """Error message pattern"""
    error_code: str = Field(description="Error code")
    severity: str = Field(description="Severity level")
    pattern: str = Field(description="Normalized error message pattern")
    pattern_count: int = Field(
        description="How many times this pattern appears"
    )
    example_messages: list[str] = Field(
        description="Example error messages matching this pattern"
    )


def execute_query(sql: str) -> list[dict]:
    """Execute SQL query against Databricks warehouse"""
    if not w or not WAREHOUSE_ID:
        return []
    
    try:
        response = w.statement_execution.execute_statement(
            warehouse_id=WAREHOUSE_ID,
            statement=sql
        )
        # Wait for query to complete
        while (response.status and
               response.status.state in ("RUNNING", "QUEUED")):
            time.sleep(0.5)
            if response.statement_id:
                response = w.statement_execution.get_statement(
                    response.statement_id
                )
        
        # Extract results
        if (response.result and response.result.data_array and
                response.manifest and response.manifest.schema and
                response.manifest.schema.columns):
            columns = [
                col.name for col in response.manifest.schema.columns
            ]
            return [
                dict(zip(columns, row))
                for row in response.result.data_array
            ]
        return []
    except Exception as e:
        print(f"Query error: {e}")
        return []


@mcp.tool()
def search_error_logs(
    error_code: Optional[str] = None,
    severity: Optional[str] = None,
    file_path: Optional[str] = None,
    message_contains: Optional[str] = None,
    limit: int = 20,
) -> ErrorSearchResult:
    """
    Search for error logs by various criteria.
    
    Args:
        error_code: Filter by error code (e.g., 'CC-1001')
        severity: Filter by severity ('Warning', 'Error', 'Event')
        file_path: Filter by file path (partial match)
        message_contains: Search for text in error message
        limit: Maximum number of results to return
    
    Returns:
        Search results with matching error logs
    """
    where_clauses = []
    
    if error_code:
        where_clauses.append(f"error_code = '{error_code}'")
    if severity:
        where_clauses.append(f"severity = '{severity}'")
    if file_path:
        where_clauses.append(f"file_path LIKE '%{file_path}%'")
    if message_contains:
        where_clauses.append(f"message LIKE '%{message_contains}%'")
    
    where_clause = (
        "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    )
    
    sql = f"""
        SELECT
            timestamp, error_code, file_path, severity, message,
            source_file,
            COUNT(*) OVER (PARTITION BY error_code) as error_frequency
        FROM {CATALOG}.{SCHEMA}.{TABLE_NAME}
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT {limit}
    """
    
    results = execute_query(sql)
    
    error_logs = [
        ErrorLog(
            timestamp=str(row.get("timestamp", "")),
            error_code=row.get("error_code", ""),
            file_path=row.get("file_path", ""),
            severity=row.get("severity", ""),
            message=row.get("message", ""),
            source_file=row.get("source_file", ""),
        )
        for row in results
    ]
    
    query_desc = (
        f"Errors with code={error_code}, severity={severity}, "
        f"file={file_path}, message={message_contains}"
    )
    
    return ErrorSearchResult(
        total_found=len(results),
        results=error_logs,
        query=query_desc
    )


@mcp.tool()
def get_error_frequency(
    severity: Optional[str] = None,
    limit: int = 20,
) -> list[ErrorFrequency]:
    """
    Get most frequently occurring error codes with statistics.
    
    Args:
        severity: Filter by severity level ('Warning', 'Error', 'Event')
        limit: Maximum number of error codes to return
    
    Returns:
        List of error codes with frequency information
    """
    where_clause = f"WHERE severity = '{severity}'" if severity else ""
    
    sql = f"""
        SELECT
            error_code,
            error_code_numeric,
            severity,
            occurrence_count,
            affected_files,
            files,
            first_occurrence,
            last_occurrence
        FROM {CATALOG}.{SCHEMA}.error_frequency
        {where_clause}
        ORDER BY occurrence_count DESC
        LIMIT {limit}
    """
    
    results = execute_query(sql)
    
    frequencies = [
        ErrorFrequency(
            error_code=row.get("error_code", ""),
            severity=row.get("severity", ""),
            occurrence_count=int(row.get("occurrence_count", 0)),
            affected_files=int(row.get("affected_files", 0)),
            files=(
                row.get("files", [])
                if isinstance(row.get("files"), list)
                else []
            ),
            first_occurrence=str(row.get("first_occurrence", "")),
            last_occurrence=str(row.get("last_occurrence", "")),
        )
        for row in results
    ]
    
    return frequencies


@mcp.tool()
def analyze_error_pattern(
    error_code: Optional[str] = None,
    severity: Optional[str] = None,
) -> list[ErrorPattern]:
    """
    Analyze patterns in error messages to find similar errors.
    
    Args:
        error_code: Filter by specific error code
        severity: Filter by severity level
    
    Returns:
        Error message patterns with frequency and examples
    """
    where_clauses = []
    if error_code:
        where_clauses.append(f"error_code = '{error_code}'")
    if severity:
        where_clauses.append(f"severity = '{severity}'")
    
    where_clause = (
        "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    )
    
    sql = f"""
        SELECT
            error_code,
            severity,
            pattern,
            pattern_count,
            example_messages
        FROM {CATALOG}.{SCHEMA}.error_patterns
        {where_clause}
        ORDER BY pattern_count DESC
        LIMIT 50
    """
    
    results = execute_query(sql)
    
    patterns = [
        ErrorPattern(
            error_code=row.get("error_code", ""),
            severity=row.get("severity", ""),
            pattern=row.get("pattern", ""),
            pattern_count=int(row.get("pattern_count", 0)),
            example_messages=(
                row.get("example_messages", [])
                if isinstance(row.get("example_messages"), list)
                else []
            ),
        )
        for row in results
    ]
    
    return patterns


@mcp.tool()
def get_file_errors(
    file_path: str,
    limit: int = 50,
) -> ErrorSearchResult:
    """
    Get all errors from a specific file.
    
    Args:
        file_path: Path to the file (e.g., 'app/src/main.py')
        limit: Maximum number of errors to return
    
    Returns:
        All errors that occurred in the specified file
    """
    sql = f"""
        SELECT
            timestamp, error_code, file_path, severity, message, source_file
        FROM {CATALOG}.{SCHEMA}.{TABLE_NAME}
        WHERE file_path = '{file_path}'
        ORDER BY timestamp DESC
        LIMIT {limit}
    """
    
    results = execute_query(sql)
    
    error_logs = [
        ErrorLog(
            timestamp=str(row.get("timestamp", "")),
            error_code=row.get("error_code", ""),
            file_path=row.get("file_path", ""),
            severity=row.get("severity", ""),
            message=row.get("message", ""),
            source_file=row.get("source_file", ""),
        )
        for row in results
    ]
    
    return ErrorSearchResult(
        total_found=len(results),
        results=error_logs,
        query=f"Errors in file: {file_path}"
    )


@mcp.tool()
def search_by_message(
    query: str,
    limit: int = 50,
) -> ErrorSearchResult:
    """
    Full-text search for errors by message content.
    
    Args:
        query: Text to search for in error messages
               (e.g., 'connection timeout')
        limit: Maximum number of results
    
    Returns:
        Matching error logs
    """
    sql = f"""
        SELECT
            timestamp, error_code, file_path, severity, message, source_file
        FROM {CATALOG}.{SCHEMA}.{TABLE_NAME}
        WHERE message LIKE '%{query}%'
        ORDER BY timestamp DESC
        LIMIT {limit}
    """
    
    results = execute_query(sql)
    
    error_logs = [
        ErrorLog(
            timestamp=str(row.get("timestamp", "")),
            error_code=row.get("error_code", ""),
            file_path=row.get("file_path", ""),
            severity=row.get("severity", ""),
            message=row.get("message", ""),
            source_file=row.get("source_file", ""),
        )
        for row in results
    ]
    
    return ErrorSearchResult(
        total_found=len(results),
        results=error_logs,
        query=f"Message contains: {query}"
    )


@mcp.tool()
def get_severity_summary() -> dict:
    """
    Get a summary of errors by severity level.
    
    Returns:
        Error counts grouped by severity
    """
    sql = f"""
        SELECT
            severity,
            COUNT(*) as error_count,
            COUNT(DISTINCT error_code) as unique_codes,
            MIN(timestamp) as earliest,
            MAX(timestamp) as latest
        FROM {CATALOG}.{SCHEMA}.{TABLE_NAME}
        GROUP BY severity
        ORDER BY error_count DESC
    """
    
    results = execute_query(sql)
    
    summary = {
        row.get("severity", "Unknown"): {
            "error_count": int(row.get("error_count", 0)),
            "unique_codes": int(row.get("unique_codes", 0)),
            "earliest": str(row.get("earliest", "")),
            "latest": str(row.get("latest", "")),
        }
        for row in results
    }
    
    return summary


def main():
    """Entry point for the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
