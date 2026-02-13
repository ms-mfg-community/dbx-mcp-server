#!/usr/bin/env python
from databricks.sdk import WorkspaceClient
import os
import time

w = WorkspaceClient(
    host=os.getenv('DATABRICKS_HOST'),
    token=os.getenv('DATABRICKS_TOKEN')
)

WAREHOUSE_ID = os.getenv('DATABRICKS_WAREHOUSE_ID')
CATALOG = os.getenv('DATABRICKS_CATALOG', 'dbx_1')
SCHEMA = os.getenv('DATABRICKS_SCHEMA', 'default')

print("Checking if table exists...\n")

# First check if table exists
sql_check = f"SELECT COUNT(*) as count FROM {CATALOG}.{SCHEMA}.error_logs_parsed LIMIT 1"

try:
    response = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql_check,
        catalog=CATALOG,
        schema=SCHEMA
    )
    
    # Wait for query
    while (response.status and
           response.status.state in ("RUNNING", "QUEUED")):
        time.sleep(0.5)
        if response.statement_id:
            response = w.statement_execution.get_statement(
                response.statement_id
            )
    
    if response.result and response.result.data_array:
        count = response.result.data_array[0][0]
        print(f"✓ Table exists with {count} rows")
    else:
        print("✗ Table query returned empty")
        
except Exception as e:
    print(f"✗ Table check failed: {type(e).__name__}")
    print(f"  Details: {e}")
    print("\n⚠ The error_logs_parsed table may not exist yet.")
    print("  Make sure you've run the parse_error_logs notebook in Databricks!")
