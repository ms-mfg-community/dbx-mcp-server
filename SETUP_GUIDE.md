# Error Log Analysis System - Complete Setup Guide

This guide walks through the entire process of setting up dynamic error log searching in GitHub Copilot using your Databricks instance.

## Overview

The system consists of three components:

1. **Mock Log Files** - 200 sample app error logs (already created in `mock_logs/`)
2. **Databricks Notebook** - Parses raw logs into a searchable Delta table
3. **MCP Server** - Provides error search tools to GitHub Copilot

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         GitHub Copilot                              │
│  Developer: "What's causing CC-1001 errors?"                       │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│                      MCP Server (server.py)                         │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │ Tools:                                                   │       │
│  │ • search_error_logs(error_code='CC-1001')               │       │
│  │ • get_error_frequency()                                  │       │
│  │ • analyze_error_pattern()                               │       │
│  │ • get_file_errors(file_path)                            │       │
│  │ • search_by_message(query)                              │       │
│  │ • get_severity_summary()                                │       │
│  └──────────────────────────────────────────────────────────┘       │
└────────────────────────────┬────────────────────────────────────────┘
                             │ SQL Queries
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│               Databricks SQL Warehouse                              │
│  ┌──────────────────────────────────────────────────────────┐       │
│  │ Tables/Views:                                            │       │
│  │ • error_logs_parsed (main table)                         │       │
│  │ • error_frequency (aggregated stats)                     │       │
│  │ • errors_by_file (recent errors)                         │       │
│  │ • error_patterns (similar errors)                        │       │
│  └──────────────────────────────────────────────────────────┘       │
└────────────────────────────┬────────────────────────────────────────┘
                             │ Row Result Sets
                             ↓
┌─────────────────────────────────────────────────────────────────────┐
│              Databricks Volume: /volumes/dbx_1/default/log_data    │
│                   (200 raw log files)                               │
└─────────────────────────────────────────────────────────────────────┘
```

## Step-by-Step Setup

### Phase 1: Prepare Your Databricks Workspace

#### Step 1.1: Verify Your Workspace

1. Log into your Azure Databricks workspace: `https://adb-xxxxx.azuredatabricks.net`
2. Navigate to **Data** → **Volumes**
3. Confirm the `log_data` volume exists in catalog `dbx_1`, schema `default`
4. Verify it contains your app error logs (200 files starting with `app_error_log_001.log`)

#### Step 1.2: Create SQL Warehouse (if needed)

If you don't have a SQL warehouse:
1. Navigate to **SQL** → **Warehouses**
2. Click **Create warehouse**
3. Name it (e.g., "Log Analysis")
4. Choose size (Small is fine for testing)
5. Start it and copy the **Warehouse ID**

---

### Phase 2: Create Delta Table from Raw Logs

#### Step 2.1: Import Notebook to Databricks

1. In your Databricks workspace, click **Workspace** and navigate to a location
2. Click **Create** → **Notebook**
3. Name it: `parse_error_logs`
4. Copy the entire contents of `databricks_notebooks/parse_error_logs.py`
5. Paste into the notebook cells
6. Update these values if different:
   - `CATALOG = "dbx_1"` 
   - `SCHEMA = "default"`
   - `VOLUME_PATH = "/Volumes/dbx_1/default/log_data"`

#### Step 2.2: Run the Notebook

1. Click the **Run all** button
2. Wait for execution to complete (should take 1-2 minutes)
3. Verify the output shows:
   ```
   ✓ Successfully created/updated table: dbx_1.default.error_logs_parsed
   ✓ Created view: error_frequency
   ✓ Created view: errors_by_file
   ✓ Created view: error_patterns
   ```

#### Step 2.3: Verify Tables Created

In a new SQL cell, run:
```sql
SELECT COUNT(*) as error_count FROM dbx_1.default.error_logs_parsed;
```

You should see ~1500+ errors (depends on your log file count).

---

### Phase 3: Set Up MCP Server

#### Step 3.1: Install UV Package Manager

**Windows:**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Verify installation:
```bash
uv --version
```

#### Step 3.2: Create Configuration File

Navigate to the `mcp_server` directory:
```bash
cd mcp_server
```

Create `.env` file (copy from `.env.example`):
```bash
cp .env.example .env
```

Edit `.env` with your Databricks credentials:
```
DATABRICKS_HOST=https://adb-xxxxxxxx.azuredatabricks.net
DATABRICKS_TOKEN=dapi1234567890abcdefghijklmnop
DATABRICKS_WAREHOUSE_ID=xxxxxxxxxxxx
DATABRICKS_CATALOG=dbx_1
DATABRICKS_SCHEMA=default
```

**To get these credentials:**
- **DATABRICKS_HOST**: From your workspace URL
- **DATABRICKS_TOKEN**: Settings → Developer → Personal access tokens → Generate new token
- **DATABRICKS_WAREHOUSE_ID**: SQL → Warehouses → Click your warehouse → copy ID from URL

#### Step 3.3: Install Dependencies

```bash
uv sync
```

#### Step 3.4: Test the Server

```bash
uv run mcp dev server.py
```

This opens the **MCP Inspector** where you can test tools interactively:
- Click on each tool to see its definition
- Fill in parameters and click "Call tool"
- See results in real-time

Try calling `get_severity_summary()` first - this should work if everything is configured correctly.

---

### Phase 4: Integrate with GitHub Copilot

#### Option A: VS Code with Claude

1. Create/edit `.vscode/settings.json` in your VS Code workspace:

```json
{
  "mcpServers": {
    "databricks-error-logs": {
      "command": "uv",
      "args": ["run", "server.py"],
      "cwd": "${workspaceFolder}/mcp_server",
      "env": {
        "DATABRICKS_HOST": "https://adb-xxxxx.azuredatabricks.net",
        "DATABRICKS_TOKEN": "dapi...",
        "DATABRICKS_WAREHOUSE_ID": "xxxxx"
      }
    }
  }
}
```

2. Restart VS Code
3. Open GitHub Copilot chat
4. Copilot will automatically load the MCP server

#### Option B: Claude Desktop (macOS/Windows)

1. Find or create the config file:
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
   - **macOS**: `~/.config/Claude/claude_desktop_config.json`

2. Add this configuration:
```json
{
  "mcpServers": {
    "databricks": {
      "command": "uv",
      "args": ["run", "server.py"],
      "cwd": "/full/path/to/mcp_server",
      "env": {
        "DATABRICKS_HOST": "https://adb-xxxxx.azuredatabricks.net",
        "DATABRICKS_TOKEN": "dapi...",
        "DATABRICKS_WAREHOUSE_ID": "xxxxx"
      }
    }
  }
}
```

3. Restart Claude Desktop
4. The MCP server will be available in Claude chat

---

## Usage Examples

Once set up, you can ask Copilot questions about your errors:

### Example 1: Find specific error code
**Prompt:** "What's causing CC-3005 errors in our logs?"

Copilot will:
1. Call `search_error_logs(error_code='CC-3005')`
2. Get recent examples of this error
3. Provide analysis and suggestions

### Example 2: Find most common errors
**Prompt:** "What are the top 10 most frequently occurring errors?"

Copilot will:
1. Call `get_error_frequency(limit=10)`
2. Show frequency statistics
3. Suggest which to fix first

### Example 3: Understand error patterns
**Prompt:** "Show me all the different ways CC-1001 errors occur"

Copilot will:
1. Call `analyze_error_pattern(error_code='CC-1001')`
2. Show normalized message patterns
3. Help identify root causes

### Example 4: Check specific file
**Prompt:** "What errors are happening in app/src/database.py?"

Copilot will:
1. Call `get_file_errors(file_path='app/src/database.py')`
2. Show all errors from that file
3. Help debug file-specific issues

### Example 5: Search by message
**Prompt:** "Find all timeout-related errors"

Copilot will:
1. Call `search_by_message(query='timeout')`
2. Return all matching errors
3. Provide patterns across your codebase

---

## Available Tools

### `search_error_logs`
Search logs by error code, severity, file, or message.

**Parameters:**
- `error_code`: Optional, e.g., 'CC-1001'
- `severity`: Optional, one of: 'Warning', 'Error', 'Event'
- `file_path`: Optional, partial filename match
- `message_contains`: Optional, search term
- `limit`: Max results (default: 20)

**Returns:** ErrorSearchResult with matching logs

### `get_error_frequency`
Top occurring errors with statistics.

**Parameters:**
- `severity`: Optional filter
- `limit`: Max error codes (default: 20)

**Returns:** List with occurrence count, affected files, first/last seen

### `analyze_error_pattern`
Find similar errors and recurring patterns.

**Parameters:**
- `error_code`: Optional filter
- `severity`: Optional filter

**Returns:** Message patterns with frequency and examples

### `get_file_errors`
All errors from a specific file.

**Parameters:**
- `file_path`: Application file path (required)
- `limit`: Max results (default: 50)

**Returns:** All errors from that file

### `search_by_message`
Full-text search in error messages.

**Parameters:**
- `query`: Search text (required)
- `limit`: Max results (default: 50)

**Returns:** Matching error logs

### `get_severity_summary`
Overview by severity level.

**Parameters:** None

**Returns:** Count, unique codes, earliest/latest for each severity

---

## Troubleshooting

### "Connection refused to Databricks"
- Verify `DATABRICKS_HOST` is correct (should include `https://` and end with `.azuredatabricks.net`)
- Check token: go to Settings → Developer → verify token is still active
- Regenerate token if needed: Settings → Developer → Personal access tokens → Generate new

### "No available computes found"
- You need a SQL Warehouse running
- Go to SQL → Warehouses → ensure your warehouse is running
- Copy its ID to `DATABRICKS_WAREHOUSE_ID`

### "Table not found: error_logs_parsed"
- Run the `parse_error_logs` notebook (Phase 2)
- Verify it completed without errors
- Check catalog/schema names match configuration

### MCP tools not showing in Copilot
- Restart VS Code or Claude Desktop
- Check `.env` file has all required fields
- Run `uv run mcp dev server.py` locally to test tools
- Check logs for authentication errors

### Query returns empty results
- Wait 5-10 minutes after running the parsing notebook
- Verify log files exist in the volume
- Run manual SQL query: `SELECT COUNT(*) FROM dbx_1.default.error_logs_parsed`

---

## Next Steps

Once working, consider:

1. **Automate parsing**: Schedule the notebook to run periodically
2. **Add more context**: Include stack traces, user IDs, request IDs
3. **Build dashboards**: Use Databricks SQL dashboards to visualize trends
4. **Alert on patterns**: Create alerts for critical error spikes
5. **Integrate into incident response**: Link to your incident management system

---

## File Structure

```
databricks/
├── mock_logs/                      # 200 generated log files
│   ├── app_error_log_001.log
│   ├── app_error_log_002.log
│   └── ...
│
├── databricks_notebooks/
│   └── parse_error_logs.py        # Notebook to parse logs → Delta table
│
├── mcp_server/                     # MCP Server for Copilot integration
│   ├── server.py                   # Main MCP server implementation
│   ├── pyproject.toml              # UV project config
│   ├── requirements.txt            # Python dependencies
│   ├── .env.example                # Configuration template
│   ├── .env                        # Your credentials (gitignored)
│   └── README.md                   # MCP server documentation
│
└── SETUP_GUIDE.md                  # This file
```

---

## Questions?

Refer to:
- **MCP Protocol**: [modelcontextprotocol.io](https://modelcontextprotocol.io)
- **Databricks**: [docs.databricks.com](https://docs.databricks.com)
- **GitHub Copilot**: [github.com/features/copilot](https://github.com/features/copilot)
