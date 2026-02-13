# 🎯 System Flow & Architecture

## End-to-End Data Flow

### What Happens When You Ask Copilot a Question

```
┌────────────────────────────────────────────────────────────────────┐
│ 1. DEVELOPER IN VS CODE / CLAUDE DESKTOP                          │
│                                                                    │
│    Prompt: "What's causing CC-3005 errors in deployment logs?"   │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────────────────────────────────┐
│ 2. GITHUB COPILOT / CLAUDE                                        │
│                                                                    │
│    Recognizes this is an error analysis question                  │
│    "I can help! Let me search your Databricks error logs..."      │
└────────┬─────────────────────────────────────────────────────────┘
         │
         ↓
┌────────────────────────────────────────────────────────────────────┐
│ 3. MCP SERVER (server.py)                                         │
│                                                                    │
│    Calls: search_error_logs(error_code='CC-3005')                │
│    Reads configuration from .env file                             │
│    Authenticates to Databricks                                    │
└────────┬─────────────────────────────────────────────────────────┘
         │ Uses Databricks SDK
         ↓
┌────────────────────────────────────────────────────────────────────┐
│ 4. DATABRICKS SQL WAREHOUSE                                       │
│                                                                    │
│    Executes SQL Query:                                            │
│    SELECT * FROM dbx_1.default.error_logs_parsed                │
│    WHERE error_code='CC-3005'                                     │
│    ORDER BY timestamp DESC LIMIT 20                               │
└────────┬─────────────────────────────────────────────────────────┘
         │ Row result set
         ↓
┌────────────────────────────────────────────────────────────────────┐
│ 5. DELTA TABLE: error_logs_parsed                                │
│                                                                    │
│    Returns matching rows:                                         │
│    - 2026-02-03 CC-3005 middleware.py Error "socket error"      │
│    - 2026-01-31 CC-3005 handlers.py  Error "connection refused" │
│    - 2026-01-29 CC-3005 api.py       Error "network timeout"    │
│    (20 most recent examples)                                      │
└────────┬─────────────────────────────────────────────────────────┘
         │ Formatted structured response
         ↓
┌────────────────────────────────────────────────────────────────────┐
│ 6. MCP SERVER                                                      │
│                                                                    │
│    Converts results to ErrorSearchResult object                   │
│    - total_found: 47                                              │
│    - results: [ErrorLog, ErrorLog, ...]                           │
│    - query: "Error code CC-3005"                                  │
└────────┬─────────────────────────────────────────────────────────┘
         │ JSON/structured response
         ↓
┌────────────────────────────────────────────────────────────────────┐
│ 7. COPILOT / CLAUDE                                               │
│                                                                    │
│    Receives 20 recent examples of CC-3005 errors                 │
│    "Found 47 instances of CC-3005. Recent examples show:         │
│     • Network socket errors in middleware.py                      │
│     • Connection refused in handlers.py                           │
│     • Timeouts in api.py                                          │
│                                                                    │
│    Probable cause: Database connectivity issues after deploy"     │
│    Suggested fix: Check database connection pool settings..."    │
└────────┬─────────────────────────────────────────────────────────┘
         │ Rich context-aware response
         ↓
┌────────────────────────────────────────────────────────────────────┐
│ 8. DEVELOPER                                                       │
│                                                                    │
│    Sees helpful analysis directly in Copilot chat                │
│    Can ask follow-up questions with full context                  │
│    Solves problem in minutes instead of hours                     │
└────────────────────────────────────────────────────────────────────┘
```

---

## System Components

### Component 1: Raw Logs (Input)
**`mock_logs/` directory**
- 200 log files (app_error_log_001.log through app_error_log_200.log)
- Format: Tab-separated values
- Contains: ~1500 total error entries
- Located: `/volumes/dbx_1/default/log_data` in Databricks

**Sample log file:**
```
# Application Error Log
# Generated: 2026-02-04T23:13:26.611908Z
# Format: TIMESTAMP	ERROR_CODE	FILE	SEVERITY	MESSAGE
2026-01-31T20:26:10Z	CC-3005	app/api/middleware.py	Error	Network socket error: connection refused
2026-02-03T00:45:20Z	CC-5002	scripts/deploy.py	Event	SSL certificate validation failed
```

### Component 2: Data Pipeline (Transformation)
**`databricks_notebooks/parse_error_logs.py`**

Steps:
1. **Read**: Loads all .log files from volume
2. **Parse**: Extracts tab-separated fields using regex
3. **Transform**: Converts to proper types (timestamp, integers)
4. **Load**: Creates Delta tables with partitioning
5. **Analyze**: Creates views for common queries

Creates these assets in Databricks:
- `error_logs_parsed` - Main table (1500 rows)
  - Columns: timestamp, error_code, file_path, severity, message, source_file
  - Optimized with: Partitioned by severity

- `error_frequency` - View aggregating errors
- `errors_by_file` - View for file-based analysis
- `error_patterns` - View finding similar messages

### Component 3: MCP Server (Interface)
**`mcp_server/server.py`**

6 Tools available:

1. **search_error_logs(error_code, severity, file_path, message_contains, limit)**
   - Flexible multi-criteria search
   - Returns: List of matching error logs with metadata

2. **get_error_frequency(severity, limit)**
   - Statistics on most common errors
   - Returns: Frequency, affected files, first/last seen

3. **analyze_error_pattern(error_code, severity)**
   - Finds similar error messages
   - Returns: Normalized patterns with examples

4. **get_file_errors(file_path, limit)**
   - All errors from specific application file
   - Returns: Chronological list with full context

5. **search_by_message(query, limit)**
   - Full-text search in error messages
   - Returns: All matching errors

6. **get_severity_summary()**
   - Overview by severity level
   - Returns: Counts by Warning/Error/Event

---

## Configuration Flow

### During Setup
```
1. User runs: python generate_logs.py
   ↓
2. Creates ./mock_logs/ with 200 files
   ↓
3. User uploads to Databricks Volume
   ↓
4. User copies parse_error_logs.py into Databricks notebook
   ↓
5. User runs notebook → Creates Delta tables
   ↓
6. User creates .env file with credentials
   ↓
7. User configures VS Code/Claude with MCP server
   ↓
8. System ready!
```

### During Usage
```
Copilot asks → MCP Server reads .env → 
Connects to Databricks → 
Queries Delta table → 
Returns results → 
Copilot provides answer
```

---

## Database Schema

### Main Table: error_logs_parsed
```sql
CREATE TABLE dbx_1.default.error_logs_parsed (
    timestamp TIMESTAMP,           -- When error occurred (UTC)
    error_code STRING,             -- e.g., "CC-1001"
    error_code_numeric INT,        -- e.g., 1001 (for sorting)
    file_path STRING,              -- e.g., "app/src/main.py"
    severity STRING,               -- "Warning" / "Error" / "Event"
    message STRING,                -- Full error message
    source_file STRING,            -- Which log file it came from
    parsed_at TIMESTAMP,           -- When we parsed it
    PARTITIONED BY (severity)      -- Optimized for severity filtering
)
```

### Derived Views

**error_frequency**: Shows most common errors
```
error_code | severity | occurrence_count | affected_files | files | first_occurrence | last_occurrence
CC-3005    | Error    | 47              | 5             | [...] | 2026-01-29       | 2026-02-04
CC-1001    | Error    | 42              | 8             | [...] | 2026-01-30       | 2026-02-03
```

**errors_by_file**: Recent errors grouped by file
```
file_path | severity | error_code | message | timestamp | recency_rank
app/src/main.py | Error | CC-1001 | Integer overflow | 2026-02-04 | 1
app/src/main.py | Error | CC-2003 | Cache miss | 2026-02-03 | 2
```

**error_patterns**: Message patterns
```
error_code | severity | pattern | pattern_count | example_messages
CC-3005 | Error | Network socket error: N | 12 | ["...connection refused", "...timeout", ...]
```

---

## Information Flow Summary

```
INFORMATION FLOW
════════════════════════════════════════════════════════════════

Raw Data (200 log files)
         ↓ (Parse & Enrich)
Delta Tables (1500 structured records)
         ↓ (Index & Partition)
SQL Queryable Views (Optimized for search)
         ↓ (MCP Interface)
MCP Tools (6 search functions)
         ↓ (LLM Integration)
GitHub Copilot/Claude
         ↓ (User-Friendly)
Developer Insights (Troubleshooting assistance)

QUERY PERFORMANCE
════════════════════════════════════════════════════════════════

Query Type                      Expected Result Time
─────────────────────          ──────────────────────
Single error code search        < 100ms
Top 20 errors                   < 200ms
Errors in specific file         < 150ms
Error patterns analysis         < 300ms
Severity summary               < 100ms

All queries hit indexed Delta tables with partitioning.
```

---

## Security & Authentication

```
┌─────────────────────────────────────────────────────────┐
│ MCP Server                                              │
│                                                         │
│ Reads .env file:                                        │
│  • DATABRICKS_HOST                                      │
│  • DATABRICKS_TOKEN (PAT)                               │
│  • DATABRICKS_WAREHOUSE_ID                              │
│                                                         │
│ Creates WorkspaceClient with token                      │
│ All queries use authenticated connection                │
│ Token is never exposed to Copilot                       │
│ All data stays within Databricks                        │
└─────────────────────────────────────────────────────────┘
```

✅ **Security Model:**
- Token stored locally in `.env` (gitignore protected)
- No credentials in code
- No data passes through Copilot
- SQL queries execute in authorized warehouse
- Row-level security can be added per user

---

## Error Handling

The system handles:
- Invalid error codes (returns empty results)
- Connection timeouts (graceful error messages)
- Missing credentials (clear error with setup instructions)
- Query failures (logged and reported)
- Malformed log entries (skipped during parsing)

---

## Scalability

Current setup handles:
- ✅ 200 log files
- ✅ 1500+ error entries
- ✅ 25 error codes
- ✅ 3+ severity levels
- ✅ Real-time queries

Can easily scale to:
- 10,000+ log files (use Auto Loader)
- 100,000+ error entries (partitioning)
- Custom error codes (modify generation)
- Multiple environments (separate tables)

---

## Extensions Possible

Once working, you can add:

1. **Real Log Integration**
   - Read from production log files (S3, blob storage)
   - Auto Loader for incremental updates
   - Scheduling with Databricks Jobs

2. **Enriched Data**
   - Add stack traces for context
   - Include user IDs / request IDs
   - Add environment tags (prod, staging, dev)

3. **Advanced Analytics**
   - Error correlation analysis
   - Root cause suggestions using LLM
   - Anomaly detection

4. **Integration**
   - Link to incident management (Jira, Slack)
   - Auto-create tickets for critical errors
   - Send alerts via email/SMS

5. **Custom Tools**
   - Add more MCP tools for specific analysis
   - Integration with your monitoring system
   - Custom prompts for domain-specific help

---

## Testing & Debugging

### Test MCP Server Locally
```bash
uv run mcp dev server.py
```
Opens Inspector to test each tool interactively.

### Verify Database Connection
```bash
# In a SQL cell in Databricks
SELECT COUNT(*) FROM dbx_1.default.error_logs_parsed
```

### Check MCP Tools in Copilot
Ask: "What tools do you have available?"
Copilot should list all 6 error search tools.

---

This architecture provides a **complete, scalable system** for bringing error context into your development workflow!
