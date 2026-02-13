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

# First get column names
sql_columns = f"""
DESCRIBE {CATALOG}.{SCHEMA}.error_logs_parsed
"""

print("Checking table schema...\n")

try:
    response = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql_columns,
        catalog=CATALOG,
        schema=SCHEMA
    )
    
    # Wait for query to complete
    max_wait = 30
    waited = 0
    while (response.status and
           response.status.state in ("RUNNING", "QUEUED") and
           waited < max_wait):
        time.sleep(0.5)
        waited += 0.5
        if response.statement_id:
            response = w.statement_execution.get_statement(
                response.statement_id
            )
    
    # Get results
    if response.result and response.result.data_array:
        print("✓ Table schema:\n")
        print("Column Name           | Data Type")
        print("-" * 50)
        for row in response.result.data_array:
            col_name = row[0]
            col_type = row[1]
            print(f"{col_name:20} | {col_type}")
    else:
        print(f"Query status: {response.status.state if response.status else 'unknown'}")
        if response.status and hasattr(response.status, 'error'):
            print(f"Error: {response.status.error}")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
