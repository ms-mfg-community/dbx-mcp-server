# Quick Start Checklist

Complete these steps in order to get error log searching working in GitHub Copilot.

## ✅ Pre-Check
- [ ] You have a Databricks workspace (Azure)
- [ ] You have 200 log files in `/volumes/dbx_1/default/log_data` 
- [ ] You have a SQL Warehouse running (or know its ID)
- [ ] You have a Databricks personal access token (PAT)

## ✅ Phase 1: Create Delta Table (5 minutes)

1. **In Databricks workspace:**
   - [ ] Create new notebook: `Workspace` → `Create` → `Notebook` → name: `parse_error_logs`
   - [ ] Copy entire contents of: `c:\Users\codycarlson\git\agentic-workflows\databricks\databricks_notebooks\parse_error_logs.py`
   - [ ] Paste into notebook
   - [ ] Click **Run all** and wait for completion
   - [ ] Verify success message appears at bottom

2. **Verify table created:**
   ```sql
   SELECT COUNT(*) FROM dbx_1.default.error_logs_parsed
   ```
   Should return ~1500+

## ✅ Phase 2: Configure MCP Server (10 minutes)

1. **Install UV:**
   ```bash
   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```

2. **Navigate to server directory:**
   ```bash
   cd c:\Users\codycarlson\git\agentic-workflows\databricks\mcp_server
   ```

3. **Create `.env` file:**
   ```bash
   cp .env.example .env
   ```

4. **Edit `.env` with your credentials:**
   - `DATABRICKS_HOST`: Your workspace URL (e.g., https://adb-xxxxx.azuredatabricks.net)
   - `DATABRICKS_TOKEN`: Your PAT (Settings → Developer → Personal access tokens)
   - `DATABRICKS_WAREHOUSE_ID`: Your SQL warehouse ID

5. **Install dependencies:**
   ```bash
   uv sync
   ```

## ✅ Phase 3: Test MCP Server (5 minutes)

1. **Start server in test mode:**
   ```bash
   uv run mcp dev server.py
   ```

2. **In the MCP Inspector:**
   - [ ] Click `get_severity_summary` tool
   - [ ] Click **Call tool** 
   - [ ] Should see error counts by severity

   If this works, your server is configured correctly!

## ✅ Phase 4: Add to GitHub Copilot (5 minutes)

### For VS Code:
```json
// .vscode/settings.json
{
  "mcpServers": {
    "databricks-error-logs": {
      "command": "uv",
      "args": ["run", "server.py"],
      "cwd": "${workspaceFolder}/mcp_server",
      "env": {
        "DATABRICKS_HOST": "https://your-workspace.azuredatabricks.net",
        "DATABRICKS_TOKEN": "dapi...",
        "DATABRICKS_WAREHOUSE_ID": "xxxxx"
      }
    }
  }
}
```
Then restart VS Code.

### For Claude Desktop (Windows):
Edit:
```
%APPDATA%\Claude\claude_desktop_config.json
```

Add:
```json
{
  "mcpServers": {
    "databricks": {
      "command": "uv",
      "args": ["run", "server.py"],
      "cwd": "C:\\...full path...\\mcp_server",
      "env": {
        "DATABRICKS_HOST": "...",
        "DATABRICKS_TOKEN": "...",
        "DATABRICKS_WAREHOUSE_ID": "..."
      }
    }
  }
}
```
Then restart Claude.

## ✅ Try It Out

Now ask Copilot questions about your errors:

- "What's causing CC-1001 errors?"
- "Show me the top 10 errors"
- "Find all database connection errors"
- "What happened in app/src/main.py?"

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Connection refused" | Check DATABRICKS_HOST and DATABRICKS_TOKEN in .env |
| Empty results | Run parse_error_logs notebook, then wait 1 min |
| "No compute available" | Create/start SQL Warehouse in Databricks |
| Tools not showing in Copilot | Restart VS Code or Claude Desktop |

## Need Help?

- **Setup Guide**: See `SETUP_GUIDE.md` for detailed instructions
- **MCP Server Docs**: See `mcp_server/README.md` for all tools
- **Test Locally**: Run `uv run mcp dev server.py` to debug
