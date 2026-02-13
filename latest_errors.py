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

sql = f"""
SELECT timestamp, severity, error_code, file_path, msg
FROM {CATALOG}.{SCHEMA}.error_logs_parsed
ORDER BY timestamp DESC
LIMIT 15
"""

print("Fetching 15 latest error messages...\n")

try:
    response = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql,
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
        print("✓ Query executed successfully!\n")
        print("15 LATEST ERROR MESSAGES")
        print("=" * 80)
        
        for i, row in enumerate(response.result.data_array, 1):
            timestamp = row[0]
            severity = row[1]
            error_code = row[2]
            file_path = row[3]
            message = row[4]
            
            print(f"\n#{i}. [{severity}] {error_code} - {timestamp}")
            print(f"    File: {file_path}")
            print(f"    Message: {message}")
        
        print("\n" + "=" * 80)
    else:
        print(f"Query status: {response.status.state if response.status else 'unknown'}")
        print("No results returned")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")
