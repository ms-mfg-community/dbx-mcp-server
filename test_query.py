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
SELECT severity, COUNT(*) as error_count, 
       COUNT(DISTINCT error_code) as unique_codes
FROM {CATALOG}.{SCHEMA}.error_logs_parsed
GROUP BY severity
ORDER BY error_count DESC
"""

print("Executing: Get Error Severity Summary\n")

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
        print("ERROR SEVERITY SUMMARY")
        print("=" * 60)
        
        for row in response.result.data_array:
            severity = row[0]
            count = row[1]
            unique = row[2]
            print(f"  {severity:12} | Count: {count:6} | Unique Codes: {unique}")
        print("=" * 60)
    else:
        print(f"Query status: {response.status.state if response.status else 'unknown'}")
        print("No results returned")
except Exception as e:
    print(f"✗ Error: {type(e).__name__}: {e}")

