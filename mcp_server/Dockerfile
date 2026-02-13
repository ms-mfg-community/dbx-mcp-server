# ---------- build stage ----------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock* requirements.txt README.md ./
COPY databricks_error_logs_mcp/ databricks_error_logs_mcp/

RUN uv sync --frozen --no-dev 2>/dev/null || uv sync --no-dev

# ---------- runtime stage ----------
FROM python:3.12-slim

WORKDIR /app

COPY --from=builder /app /app

ENV PATH="/app/.venv/bin:$PATH"
ENV MCP_TRANSPORT=streamable-http
ENV MCP_SERVER_PORT=8000

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["python", "-m", "databricks_error_logs_mcp"]
