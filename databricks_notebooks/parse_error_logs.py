# Databricks notebook source
# MAGIC %md
# MAGIC # Parse Application Error Logs
# MAGIC This notebook reads raw log files from the `log_data` volume and creates a structured Delta table for querying.

# COMMAND ----------

import re
from datetime import datetime
from pyspark.sql.types import StructType, StructField, StringType, TimestampType, ArrayType
from pyspark.sql.functions import col, lit, regexp_extract, explode, split, trim

# Configuration
VOLUME_PATH = "/Volumes/dbx_1/default/log_data"
CATALOG = "dbx_1"
SCHEMA = "default"
TABLE_NAME = "error_logs_parsed"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Read raw log files from volume

# COMMAND ----------

# Read all .log files from the volume
raw_logs_df = spark.read.text(f"{VOLUME_PATH}/*.log")

display(raw_logs_df.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Parse log entries and extract fields

# COMMAND ----------

from pyspark.sql.functions import when, regexp_extract_all, collect_list, struct

# Filter out header and separator lines
logs_df = raw_logs_df.filter(
    (~col("value").startswith("#")) &
    (~col("value").startswith("-")) &
    (col("value") != "")
)

# Parse tab-separated values
# Format: TIMESTAMP    ERROR_CODE    FILE    SEVERITY    MESSAGE
parsed_logs_df = logs_df.select(
    col("_metadata.file_path").alias("source_file"),
    regexp_extract(col("value"), r"^([^\t]+)", 1).alias("timestamp"),
    regexp_extract(col("value"), r"\t([^\t]+)", 1).alias("error_code"),
    regexp_extract(col("value"), r"\t[^\t]+\t([^\t]+)", 1).alias("file_path"),
    regexp_extract(col("value"), r"\t[^\t]+\t[^\t]+\t([^\t]+)", 1).alias("severity"),
    regexp_extract(col("value"), r"\t[^\t]+\t[^\t]+\t[^\t]+\t(.+)$", 1).alias("message"),
    lit(datetime.utcnow()).alias("parsed_at")
).filter(
    (col("timestamp").isNotNull()) & 
    (col("error_code").isNotNull()) &
    (col("message").isNotNull())
)

# Convert timestamp to proper format
parsed_logs_df = parsed_logs_df.withColumn(
    "timestamp", 
    col("timestamp").cast(TimestampType())
)

# Extract error code numeric part for analytics
parsed_logs_df = parsed_logs_df.withColumn(
    "error_code_numeric",
    regexp_extract(col("error_code"), r"(\d+)$", 1).cast("int")
)

display(parsed_logs_df.limit(20))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Create or update Delta table

# COMMAND ----------

# Create target table path
target_table = f"{CATALOG}.{SCHEMA}.{TABLE_NAME}"

# Write as managed Delta table with partitioning for optimal query performance
(
    parsed_logs_df
    .coalesce(10)  # Reduce number of files for better query performance
    .write
    .format("delta")
    .mode("overwrite")
    .option("mergeSchema", "true")
    .partitionBy("severity")
    .saveAsTable(target_table)
)

print(f"✓ Successfully created/updated table: {target_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Verify the table

# COMMAND ----------

# Show table structure
spark.sql(f"DESCRIBE TABLE {target_table}").display()

# COMMAND ----------

# Show sample data
spark.sql(f"""
    SELECT * FROM {target_table}
    ORDER BY timestamp DESC
    LIMIT 20
""").display()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 5: Create useful analytics views

# COMMAND ----------

# View 1: Error frequency by code
spark.sql(f"""
    CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.error_frequency AS
    SELECT 
        error_code,
        error_code_numeric,
        severity,
        COUNT(*) as occurrence_count,
        COUNT(DISTINCT file_path) as affected_files,
        COLLECT_SET(DISTINCT file_path) as files,
        MIN(timestamp) as first_occurrence,
        MAX(timestamp) as last_occurrence
    FROM {target_table}
    GROUP BY error_code, error_code_numeric, severity
    ORDER BY occurrence_count DESC
""")

print("✓ Created view: error_frequency")

# COMMAND ----------

# View 2: Recent errors by file
spark.sql(f"""
    CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.errors_by_file AS
    SELECT 
        file_path,
        severity,
        error_code,
        message,
        timestamp,
        source_file,
        ROW_NUMBER() OVER (PARTITION BY file_path ORDER BY timestamp DESC) as recency_rank
    FROM {target_table}
    QUALIFY recency_rank <= 5
    ORDER BY file_path, timestamp DESC
""")

print("✓ Created view: errors_by_file")

# COMMAND ----------

# View 3: Error patterns (group similar messages)
spark.sql(f"""
    CREATE OR REPLACE VIEW {CATALOG}.{SCHEMA}.error_patterns AS
    SELECT 
        error_code,
        severity,
        REGEXP_REPLACE(message, '\\d+', 'N') as pattern,
        COUNT(*) as pattern_count,
        COLLECT_SET(DISTINCT message) as example_messages
    FROM {target_table}
    GROUP BY error_code, severity, pattern
    ORDER BY pattern_count DESC
""")

print("✓ Created view: error_patterns")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

summary_stats = spark.sql(f"""
    SELECT 
        COUNT(*) as total_errors,
        COUNT(DISTINCT error_code) as unique_error_codes,
        COUNT(DISTINCT file_path) as affected_files,
        COUNT(DISTINCT severity) as severity_levels,
        MIN(timestamp) as earliest_error,
        MAX(timestamp) as latest_error
    FROM {target_table}
""")

summary_stats.display()

print(f"""
✓ Error log parsing complete!

Tables/Views created:
  - {CATALOG}.{SCHEMA}.{TABLE_NAME} (main parsed logs table)
  - {CATALOG}.{SCHEMA}.error_frequency (error frequency analysis)
  - {CATALOG}.{SCHEMA}.errors_by_file (recent errors by file)
  - {CATALOG}.{SCHEMA}.error_patterns (error message patterns)

Ready for querying by the MCP server!
""")
