# Azure Deployment Guide

Deploy the Databricks Error Logs MCP Server to Azure with a single command using Azure Developer CLI (`azd`).

## Architecture

```mermaid
graph TB
    subgraph Client["🖥️ Developer IDE"]
        VSCode["VS Code / GitHub Copilot"]
        Claude["Claude Desktop"]
        CLI["GitHub Copilot CLI"]
    end

    subgraph Azure["☁️ Azure (Resource Group: rg-dev)"]
        subgraph APIM["Azure API Management (Standard v2)"]
            APIMGw["Gateway Endpoint<br/>apim-*.azure-api.net/dbx-mcp/mcp"]
            SubKey["🔑 Subscription Key Auth"]
            RateLimit["⏱️ Rate Limiting (60 req/min)"]
            StripToken["🛡️ Strip X-Databricks-Token<br/>from outbound"]
        end

        subgraph CAE["Container Apps Environment"]
            CA["Container App<br/>ca-mcp-server-dev<br/>0.5 vCPU / 1 GiB"]
            MCP["MCP Server (Python)<br/>streamable-http on :8000<br/>/mcp  •  /health"]
            Scale["📈 Scale 0→5 replicas<br/>(HTTP concurrency)"]
        end

        ACR["Azure Container<br/>Registry (Basic)<br/>cr*.azurecr.io"]
        LAW["Log Analytics<br/>Workspace"]
    end

    subgraph DBX["🔶 Databricks (User's Workspace)"]
        SQL["SQL Warehouse"]
        Delta["Delta Table<br/>catalog.schema.parsed_error_logs"]
    end

    VSCode -- "HTTPS + Sub Key<br/>+ Databricks Headers" --> APIMGw
    Claude -- "HTTPS + Sub Key<br/>+ Databricks Headers" --> APIMGw
    CLI -- "HTTPS + Sub Key<br/>+ Databricks Headers" --> APIMGw

    APIMGw --> SubKey --> RateLimit --> StripToken
    StripToken -- "HTTPS (internal)" --> CA
    CA --> MCP
    MCP -- "SQL via PAT Token<br/>(user-provided)" --> SQL
    SQL --> Delta

    ACR -. "Image Pull" .-> CA
    CAE -. "Logs" .-> LAW

    style Azure fill:#e6f3ff,stroke:#0078d4,stroke-width:2px
    style APIM fill:#fff3e0,stroke:#ff8c00,stroke-width:2px
    style CAE fill:#e8f5e9,stroke:#4caf50,stroke-width:2px
    style DBX fill:#fff8e1,stroke:#ff6f00,stroke-width:2px
    style Client fill:#f3e5f5,stroke:#9c27b0,stroke-width:2px
```

### Data Flow

```mermaid
sequenceDiagram
    participant Dev as Developer IDE
    participant APIM as Azure API Management
    participant MCP as MCP Server (Container App)
    participant DBX as Databricks SQL Warehouse

    Dev->>APIM: POST /mcp (initialize)<br/>Headers: Sub Key
    APIM->>APIM: Validate subscription key
    APIM->>MCP: Forward request
    MCP-->>APIM: 200 OK + Mcp-Session-Id
    APIM-->>Dev: Session established

    Dev->>APIM: POST /mcp (tools/call)<br/>Headers: Sub Key + Session ID<br/>+ X-Databricks-Host/Token/Warehouse
    APIM->>MCP: Forward (strips token from response)
    MCP->>MCP: Resolve config from headers
    MCP->>DBX: SQL query via PAT token
    DBX-->>MCP: Query results
    MCP-->>APIM: Tool result (JSON-RPC)
    APIM-->>Dev: Structured response
```

## Resources Created & Cost Estimates

All prices are approximate USD, East US 2 region. Container App costs assume 0.5 vCPU / 1 GiB, ~2 seconds average processing time per MCP request, and include free monthly grants (180K vCPU-seconds, 360K GiB-seconds, 2M requests per subscription).

### With APIM Standard v2

| Resource | SKU/Tier | 500 req/day | 1K req/day | 5K req/day | 10K req/day |
|----------|----------|------------|-----------|-----------|------------|
| Resource Group | — | Free | Free | Free | Free |
| Container Registry | Basic (10 GB) | $5 | $5 | $5 | $5 |
| Container Apps Env | Consumption | Free | Free | Free | Free |
| Container App | 0.5 vCPU / 1 GiB | ~$0 ¹ | ~$0 ¹ | ~$0 ¹ | ~$4 |
| Log Analytics | Per-GB | ~$2 | ~$3 | ~$4 | ~$5 |
| API Management | Standard v2 | $700 | $700 | $700 | $700 |
| **Monthly Total** | | **~$707** | **~$708** | **~$709** | **~$714** |

### With APIM Basic v2

| Resource | SKU/Tier | 500 req/day | 1K req/day | 5K req/day | 10K req/day |
|----------|----------|------------|-----------|-----------|------------|
| Resource Group | — | Free | Free | Free | Free |
| Container Registry | Basic (10 GB) | $5 | $5 | $5 | $5 |
| Container Apps Env | Consumption | Free | Free | Free | Free |
| Container App | 0.5 vCPU / 1 GiB | ~$0 ¹ | ~$0 ¹ | ~$0 ¹ | ~$4 |
| Log Analytics | Per-GB | ~$2 | ~$3 | ~$4 | ~$5 |
| API Management | Basic v2 | $170 | $170 | $170 | $170 |
| **Monthly Total** | | **~$177** | **~$178** | **~$179** | **~$184** |

### Without APIM (Direct to Container App)

| Resource | SKU/Tier | 500 req/day | 1K req/day | 5K req/day | 10K req/day |
|----------|----------|------------|-----------|-----------|------------|
| Resource Group | — | Free | Free | Free | Free |
| Container Registry | Basic (10 GB) | $5 | $5 | $5 | $5 |
| Container Apps Env | Consumption | Free | Free | Free | Free |
| Container App | 0.5 vCPU / 1 GiB | ~$0 ¹ | ~$0 ¹ | ~$0 ¹ | ~$4 |
| Log Analytics | Per-GB | ~$2 | ~$3 | ~$4 | ~$5 |
| **Monthly Total** | | **~$7** | **~$8** | **~$9** | **~$14** |

<details>
<summary>¹ Container App cost breakdown</summary>

At **5K req/day and below**, all compute stays within the free monthly grants:
- 5K/day = 150K req/mo → 150K vCPU-seconds + 300K GiB-seconds (both under free thresholds)

At **10K req/day**:
- 300K requests/mo — covered by 2M free request grant ($0)
- 300K vCPU-seconds (300K req × 2s × 0.5 vCPU) — 180K free, 120K billable × $0.000024 = $2.88
- 600K GiB-seconds (300K req × 2s × 1 GiB) — 360K free, 240K billable × $0.0000031 = $0.74
- **Total: ~$3.62/mo**
</details>

### Choosing an APIM Tier

APIM is the largest cost driver in this deployment, but it's important to understand that **APIM is a shared platform, not a dedicated resource for this MCP server**:

- **One APIM instance can front multiple MCP servers**, internal APIs, partner integrations, and other backend services across your organization
- Standard v2 includes **50M API calls/month** — at 10K MCP requests/day you're using less than 1% of that capacity
- APIM provides **centralized authentication, rate limiting, usage analytics, and a developer portal** across all your APIs
- If your organization already runs an APIM instance, adding this MCP server is essentially **zero incremental cost**

| Consideration | Standard v2 ($700/mo) | Basic v2 ($170/mo) | No APIM |
|--------------|----------------------|-------------------|---------|
| Subscription key auth | ✅ | ✅ | ❌ |
| Rate limiting | ✅ | ✅ | ❌ |
| VNet integration | ✅ | ❌ | ❌ |
| Scale units | Up to 10 | Up to 2 | N/A |
| Developer portal | ✅ | ❌ | ❌ |
| Multi-API gateway | ✅ Best value at scale | ✅ Good for small teams | N/A |
| Included API calls | 50M/mo | 10M/mo | N/A |

> **Without APIM**, you can connect VS Code directly to the Container App endpoint. The endpoint is still HTTPS-secured and supports the same per-request header-based config. To add access control without APIM, consider [Container Apps EasyAuth](https://learn.microsoft.com/en-us/azure/container-apps/authentication) or IP restrictions.

## Prerequisites

1. [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) installed
2. [Azure Developer CLI (azd)](https://learn.microsoft.com/en-us/azure/developer/azure-developer-cli/install-azd) installed
3. [Docker](https://docs.docker.com/get-docker/) installed and running
4. An Azure subscription with Contributor access

## One-Click Deploy

```bash
# From the databricks/ directory
cd databricks

# Login to Azure
azd auth login

# Provision and deploy everything
azd up
```

You'll be prompted for:
- **Environment name** (e.g., `dev`, `staging`, `prod`)
- **Azure subscription**
- **Azure location** (e.g., `eastus`, `westus2`)

The command will:
1. Create all Azure resources via Bicep
2. Build the Docker image
3. Push to Azure Container Registry
4. Deploy to Container Apps
5. Configure APIM gateway

This takes approximately 3-5 minutes (plus 10-20 minutes if APIM is provisioned for the first time).

### Step 2: Register MCP Server in APIM

After `azd up` completes, you need to register the MCP server using APIM's native MCP server support. This step is done via the Azure Portal because the `mcpServers` resource type is not yet available in ARM/Bicep.

> **Why this step?** APIM has built-in MCP protocol support that handles session management, streaming, and tool routing automatically — much better than treating MCP as a generic REST API. See [Expose an existing MCP server](https://learn.microsoft.com/en-us/azure/api-management/expose-existing-mcp-server) for details.

1. Go to the [Azure Portal](https://portal.azure.com) and navigate to your APIM instance
2. In the left menu, under **APIs**, select **MCP Servers**
3. Click **+ Create MCP server**
4. Select **Expose an existing MCP server**
5. Fill in the form:
   - **MCP server base URL**: Your Container App URL (find it with `azd env get-values` → `MCP_SERVER_URL`, e.g., `https://ca-mcp-server-dev.xxxxx.eastus2.azurecontainerapps.io`)

     > ⚠️ Use the **Container App URL** (not the APIM URL). This is the backend server that APIM will proxy to. Do **not** include `/mcp` — APIM appends this automatically.
   - **Transport type**: `Streamable HTTP`
   - **Name**: `databricks-error-logs`
   - **Base path**: `dbx-mcp` (this becomes part of the APIM URL, e.g., `https://apim-xxx.azure-api.net/dbx-mcp/mcp`)
   - **Description**: `Databricks Error Logs MCP Server`
6. Click **Create**

The MCP server will appear in the **MCP Servers** list with a **Server URL** — this is the endpoint developers will use in their VS Code configuration.

### Step 3: Configure Security Policies (Recommended)

After creating the MCP server, add security policies to control rate limiting and protect sensitive headers.

#### Navigate to the Policy Editor

1. In the [Azure Portal](https://portal.azure.com), go to your **API Management** instance
2. In the left menu, under **APIs**, select **MCP Servers**
3. Click on the MCP server you created in Step 2 (e.g., `databricks-error-logs`)
4. In the left menu that appears under **MCP**, select **Policies**
5. The policy editor opens with a default XML skeleton that looks like this:

```xml
<policies>
    <inbound>
        <base />
    </inbound>
    <backend>
        <base />
    </backend>
    <outbound>
        <base />
    </outbound>
    <on-error>
        <base />
    </on-error>
</policies>
```

#### Add the Recommended Policies

Replace the entire contents of the policy editor with the following complete policy document. This adds:
- **Rate limiting** — 60 `tools/call` requests per minute per MCP session
- **Outbound header stripping** — removes `X-Databricks-Token` from responses so tokens are never leaked to clients

```xml
<policies>
    <inbound>
        <base />
        <!-- Rate limit tool calls by MCP session (60 calls/min per session) -->
        <set-variable name="body" value="@(context.Request.Body.As<string>(preserveContent: true))" />
        <choose>
            <when condition="@(
                Newtonsoft.Json.Linq.JObject.Parse((string)context.Variables["body"])["method"] != null
                && Newtonsoft.Json.Linq.JObject.Parse((string)context.Variables["body"])["method"].ToString() == "tools/call"
            )">
                <rate-limit-by-key
                    calls="60"
                    renewal-period="60"
                    counter-key="@(
                        context.Request.Headers.GetValueOrDefault("Mcp-Session-Id", "unknown")
                    )" />
            </when>
        </choose>
    </inbound>
    <backend>
        <base />
    </backend>
    <outbound>
        <base />
        <!-- Strip Databricks PAT token from responses to prevent leakage -->
        <set-header name="X-Databricks-Token" exists-action="delete" />
    </outbound>
    <on-error>
        <base />
    </on-error>
</policies>
```

6. Click **Save** at the top of the policy editor

> **⚠️ Important:** Do **not** access `context.Response.Body` in MCP server policies. Doing so triggers response buffering which breaks MCP streaming. The policy above only inspects the *request* body, which is safe.

> **💡 Tip:** Policies defined at the **All APIs** scope in APIM are evaluated *before* MCP server-scoped policies. If you have global policies, ensure they don't conflict (e.g., duplicate rate limiting).

#### Optional: Add OAuth 2.1 / Entra ID Authentication

For stronger authentication beyond subscription keys, add a `validate-azure-ad-token` policy in the `<inbound>` section (after `<base />`):

```xml
<validate-azure-ad-token tenant-id="YOUR_ENTRA_TENANT_ID"
    header-name="Authorization"
    failed-validation-httpcode="401"
    failed-validation-error-message="Unauthorized. Access token is missing or invalid.">
    <client-application-ids>
        <application-id>YOUR_CLIENT_APP_ID</application-id>
    </client-application-ids>
</validate-azure-ad-token>
```

> For the full security reference including credential manager and outbound OAuth, see [Secure access to MCP servers](https://learn.microsoft.com/en-us/azure/api-management/secure-mcp-servers).

### Step 4: Get Your MCP Server URL

After registration, the MCP server URL will be shown in the **MCP Servers** blade:

```
https://<your-apim>.azure-api.net/dbx-mcp/mcp
```

This is the URL developers will use in their VS Code `mcp.json` configuration.

## After Deployment

### For Admins: Get Your Deployment Details

If you ran `azd up`, retrieve your endpoints:

```bash
azd env get-values
```

Key outputs:
- `APIM_GATEWAY_URL` — The APIM gateway base URL
- `MCP_SERVER_URL` — The Container App backend URL (used in APIM MCP server registration above)
- The **MCP Server URL** from the APIM MCP Servers blade (e.g., `https://apim-xxxxx.azure-api.net/dbx-mcp/mcp`) — this is what developers use

---

## 👩‍💻 Developer Setup Guide

**You don't need Azure access to use the MCP server.** Your admin has deployed it — you just need a few values to connect from VS Code. Here's exactly what you need and where to find each one.

### What You'll Need

| Value | Where to Get It | Example |
|-------|----------------|---------|
| **MCP Server URL** | Your admin provides this (from the APIM MCP Servers blade) | `https://apim-xxxxx.azure-api.net/dbx-mcp/mcp` |
| **APIM Subscription Key** | Your admin provides this, or self-service from the APIM Developer Portal (see below) | `c17ba71f3ed248e6...` |
| **Databricks Workspace URL** | Your Databricks workspace → browser address bar, or **Settings → Workspace URL** | `https://adb-1234567890.azuredatabricks.net` |
| **Databricks Personal Access Token** | Generate one in Databricks (see steps below) | `dapi0123456789abcdef...` |
| **SQL Warehouse ID** | Databricks → **SQL Warehouses** → click your warehouse → copy the ID from the URL or **Connection Details** tab | `3b344f0c124e23fa` |
| **Catalog Name** | Databricks → **Data** (left sidebar) → your catalog name appears at the top of the tree | `dbx_1` |
| **Schema Name** | Databricks → **Data** → expand your catalog → schema name (often `default`) | `default` |

### Step 1: Get Your APIM Subscription Key

Your admin will provide this in one of two ways:

**Option A: Admin shares it directly**
Ask your admin for the APIM subscription key. They can find it in the Azure Portal:
1. Go to [portal.azure.com](https://portal.azure.com)
2. Search for **API Management services** in the top search bar
3. Click on the APIM instance (name starts with `apim-`)
4. In the left menu, go to **APIs → Subscriptions**
5. Click **Show/hide keys** (the eye icon 👁️) next to "Built-in all-access subscription" or the "Databricks MCP Access" product subscription
6. Copy the **Primary key**

**Option B: Self-service via Developer Portal** (if enabled by your admin)
1. Navigate to the APIM Developer Portal URL (ask your admin, typically `https://apim-xxxxx.developer.azure-api.net`)
2. Sign in and subscribe to the **Databricks MCP Access** product
3. Your subscription key will appear in your profile

### Step 2: Generate a Databricks Personal Access Token

1. Log in to your Databricks workspace (e.g., `https://adb-1234567890.azuredatabricks.net`)
2. Click your **user icon** (top-right corner) → **Settings**
3. Go to **Developer** → **Access tokens**
4. Click **Generate new token**
5. Add a comment (e.g., "MCP Server - VS Code") and set a lifetime (e.g., 90 days)
6. Click **Generate** → **copy the token immediately** (you won't see it again!)

> ⚠️ **Treat this token like a password.** Don't commit it to source control or share it in chat.

### Step 3: Find Your SQL Warehouse ID

1. In Databricks, click **SQL Warehouses** in the left sidebar
2. Click on the warehouse you want to query
3. The Warehouse ID is in the URL: `https://adb-xxx.azuredatabricks.net/sql/warehouses/`**`3b344f0c124e23fa`**
4. Alternatively, click the **Connection details** tab and copy the **HTTP Path** — the warehouse ID is the last segment after `/warehouses/`

### Step 4: Configure VS Code

Add to `.vscode/mcp.json` in any workspace where you want Databricks error log tools available:

```json
{
  "servers": {
    "databricksErrorLogs": {
      "type": "http",
      "url": "https://<your-apim>.azure-api.net/dbx-mcp/mcp",
      "headers": {
        "Ocp-Apim-Subscription-Key": "${input:apim-key}",
        "X-Databricks-Host": "${input:databricks-host}",
        "X-Databricks-Token": "${input:databricks-token}",
        "X-Databricks-Warehouse-Id": "${input:databricks-warehouse-id}",
        "X-Databricks-Catalog": "${input:databricks-catalog}",
        "X-Databricks-Schema": "${input:databricks-schema}"
      }
    }
  },
  "inputs": [
    {
      "type": "promptString",
      "id": "apim-key",
      "description": "APIM Subscription Key",
      "password": true
    },
    {
      "type": "promptString",
      "id": "databricks-host",
      "description": "Databricks workspace URL (e.g. https://adb-xxx.azuredatabricks.net)"
    },
    {
      "type": "promptString",
      "id": "databricks-token",
      "description": "Databricks Personal Access Token",
      "password": true
    },
    {
      "type": "promptString",
      "id": "databricks-warehouse-id",
      "description": "SQL Warehouse ID"
    },
    {
      "type": "promptString",
      "id": "databricks-catalog",
      "description": "Catalog name",
      "default": "dbx_1"
    },
    {
      "type": "promptString",
      "id": "databricks-schema",
      "description": "Schema name",
      "default": "default"
    }
  ]
}
```

Replace `<your-apim>` with your APIM instance name. The full URL comes from the **MCP Servers** blade in the Azure Portal (see admin setup Step 2 above).

> **Important:** Use `"type": "http"` (not `"sse"`). This tells VS Code to use the streamable-http MCP transport, which is the current standard for remote servers.

### Step 5: Verify It Works

1. **Restart VS Code** (or reload the window with `Ctrl+Shift+P` → "Developer: Reload Window")
2. VS Code will prompt you for each value the first time:
   - APIM subscription key (masked — won't show on screen)
   - Databricks workspace URL
   - Databricks PAT (masked)
   - SQL Warehouse ID
   - Catalog and schema names (defaults pre-filled)
3. Open **GitHub Copilot Chat** (`Ctrl+Shift+I`) and ask:
   > "What are the top 10 most common errors?"
4. Copilot should invoke the `get_error_frequency` tool and return results from your Databricks workspace

> 💡 **Tip:** Each value is entered once per VS Code session. If you need to change a value, restart VS Code and you'll be prompted again.

---

### Configure Claude Desktop (Alternative)

Edit your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "databricks": {
      "url": "https://<your-apim>.azure-api.net/dbx-mcp/mcp",
      "headers": {
        "Ocp-Apim-Subscription-Key": "your-subscription-key",
        "X-Databricks-Host": "https://adb-xxx.azuredatabricks.net",
        "X-Databricks-Token": "dapi...",
        "X-Databricks-Warehouse-Id": "your-warehouse-id",
        "X-Databricks-Catalog": "dbx_1",
        "X-Databricks-Schema": "default"
      }
    }
  }
}
```

> **Note:** Claude Desktop does not support `${input:...}` prompts, so values must be hardcoded in the config file. Alternatively, connect without headers and use the `configure_databricks` tool conversationally at the start of your session.

## Managing the Deployment

```bash
# Redeploy after code changes
azd deploy

# View logs
az containerapp logs show \
  --name ca-mcp-server-<env> \
  --resource-group rg-<env> \
  --follow

# Tear down all resources
azd down
```

## Security Considerations

APIM's native MCP server support provides built-in security features. See [Secure access to MCP servers](https://learn.microsoft.com/en-us/azure/api-management/secure-mcp-servers) for the full reference.

### Inbound Security (MCP Client → APIM)

| Method | Description | Configuration |
|--------|-------------|---------------|
| **Subscription key** (default) | Clients send `Ocp-Apim-Subscription-Key` header | Enabled via the APIM product — no extra config needed |
| **OAuth 2.1 / Entra ID** | Validate JWT tokens from Microsoft Entra ID | Add `validate-azure-ad-token` policy to MCP server policies |
| **IP filtering** | Restrict by client IP | Add `ip-filter` policy |

### Outbound Security (APIM → Backend)

- **Databricks PAT tokens** are passed via `X-Databricks-*` headers per-request and **never stored** server-side
- **HTTPS** is enforced end-to-end (APIM → Container App)
- Request headers are automatically forwarded to MCP tool invocations by APIM's native MCP support
- For enhanced security, use APIM's [credential manager](https://learn.microsoft.com/en-us/azure/api-management/credentials-overview) to inject OAuth tokens to backends

### Additional Measures

- **Rate limiting** — configure per-session rate limits in MCP server policies (see Step 3 above)
- **Container Apps** ingress can be locked down with IP restrictions to only accept APIM traffic
- **Diagnostic logging** — if enabled at the "All APIs" scope, set **Frontend Response payload bytes to log** to `0` to avoid interfering with MCP streaming (see [MS Learn](https://learn.microsoft.com/en-us/azure/api-management/expose-existing-mcp-server#prerequisites))

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `azd up` fails on APIM | APIM Standard v2 takes 10-20 min to provision; retry if timeout |
| 401 Unauthorized | Check APIM subscription key is correct |
| Empty results from tools | Verify Databricks headers are correct; test PAT token directly |
| Container not starting | Check `az containerapp logs show` for startup errors |
| APIM returns 500 | Container App may be scaling from zero; retry after 30s |
| MCP streaming hangs/fails | Do not access `context.Response.Body` in MCP server policies; disable response body logging at the All APIs scope (set Frontend Response payload bytes to `0`) |
| MCP server not visible in APIM portal | Known issue with Standard v2 portal blade; verify via REST API or CLI — the server may be functional even if not displayed |
