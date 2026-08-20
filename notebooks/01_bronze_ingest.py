# Databricks notebook source
# MAGIC %md
# MAGIC # Aquila Energy Intelligence Platform
# MAGIC ## Notebook 01 — Bronze Layer: Raw Data Ingestion
# MAGIC **Purpose:** Ingest all raw CSV files from ADLS Gen2 into Delta Lake Bronze tables with
# MAGIC schema enforcement, audit columns, and data quality tagging.
# MAGIC
# MAGIC | Layer  | Schema   | Description                        |
# MAGIC |--------|----------|------------------------------------|
# MAGIC | Bronze | `bronze` | Raw ingestion, no transformations  |
# MAGIC | Silver | `silver` | Cleaned, deduplicated, enriched    |
# MAGIC | Gold   | `gold`   | Aggregated KPIs & feature store    |

# COMMAND ----------
# MAGIC %md ### 0. Configuration

# COMMAND ----------
# Storage account and container (update for your workspace)
STORAGE_ACCOUNT = "aquiladatalake"
CONTAINER       = "raw"
ADLS_PATH       = f"abfss://{CONTAINER}@{STORAGE_ACCOUNT}.dfs.core.windows.net"

# Mount point (or use direct ABFSS paths)
MOUNT_POINT     = "/mnt/aquila"
BRONZE_DB       = "bronze"
BRONZE_PATH     = "/mnt/aquila/bronze"

# Audit metadata
PIPELINE_RUN_ID = dbutils.widgets.get("pipeline_run_id") if dbutils.widgets.get("pipeline_run_id") != "" else "manual"
INGESTED_BY     = "adf_aquila_bronze_pipeline"

spark.conf.set("spark.sql.shuffle.partitions", "200")
spark.conf.set("spark.databricks.delta.optimizeWrite.enabled", "true")
spark.conf.set("spark.databricks.delta.autoCompact.enabled", "true")

print(f"Pipeline Run ID : {PIPELINE_RUN_ID}")
print(f"ADLS Path       : {ADLS_PATH}")

# COMMAND ----------
# MAGIC %md ### 1. Create Bronze Database & Mount Point

# COMMAND ----------
spark.sql(f"CREATE DATABASE IF NOT EXISTS {BRONZE_DB} LOCATION '{BRONZE_PATH}'")

# Mount ADLS Gen2 (skip if already mounted)
try:
    dbutils.fs.mount(
        source=ADLS_PATH,
        mount_point=MOUNT_POINT,
        extra_configs={
            f"fs.azure.account.auth.type.{STORAGE_ACCOUNT}.dfs.core.windows.net": "OAuth",
            f"fs.azure.account.oauth.provider.type.{STORAGE_ACCOUNT}.dfs.core.windows.net":
                "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider",
            f"fs.azure.account.oauth2.client.id.{STORAGE_ACCOUNT}.dfs.core.windows.net":
                dbutils.secrets.get("aquila-scope", "sp-client-id"),
            f"fs.azure.account.oauth2.client.secret.{STORAGE_ACCOUNT}.dfs.core.windows.net":
                dbutils.secrets.get("aquila-scope", "sp-client-secret"),
            f"fs.azure.account.oauth2.client.endpoint.{STORAGE_ACCOUNT}.dfs.core.windows.net":
                f"https://login.microsoftonline.com/{dbutils.secrets.get('aquila-scope','tenant-id')}/oauth2/token",
        }
    )
    print(f"Mounted {MOUNT_POINT}")
except Exception as e:
    if "already mounted" in str(e).lower():
        print(f"{MOUNT_POINT} already mounted — OK")
    else:
        raise e

# COMMAND ----------
# MAGIC %md ### 2. Helper — Ingest CSV to Bronze Delta

# COMMAND ----------
from pyspark.sql import functions as F
from pyspark.sql.types import *
from datetime import datetime

def ingest_csv_to_bronze(
    source_path: str,
    table_name:  str,
    infer_schema: bool = True,
    partition_cols: list = None
) -> int:
    """Read CSV from ADLS, add audit columns, write to Bronze Delta."""
    print(f"\n{'─'*55}")
    print(f"  Ingesting → bronze.{table_name}")
    print(f"  Source    : {source_path}")

    df = (spark.read
          .option("header", "true")
          .option("inferSchema", str(infer_schema).lower())
          .option("multiLine", "true")
          .option("escape", '"')
          .csv(source_path))

    row_count = df.count()
    print(f"  Rows read : {row_count:,}")

    # Add audit columns
    df = (df
          .withColumn("_ingested_at",     F.current_timestamp())
          .withColumn("_pipeline_run_id", F.lit(PIPELINE_RUN_ID))
          .withColumn("_ingested_by",     F.lit(INGESTED_BY))
          .withColumn("_source_file",     F.lit(source_path)))

    write_opts = (spark.createDataFrame([], df.schema)
                  .write
                  .format("delta")
                  .mode("overwrite")
                  .option("overwriteSchema", "true"))

    if partition_cols:
        write_opts = write_opts.partitionBy(*partition_cols)

    write_opts.saveAsTable(f"{BRONZE_DB}.{table_name}")
    print(f"  Written   : bronze.{table_name}  ({row_count:,} rows)")
    return row_count

# COMMAND ----------
# MAGIC %md ### 3. Ingest Dimension Tables

# COMMAND ----------
DIMS = {
    "dim_plant"             : f"{MOUNT_POINT}/raw/dim_plant.csv",
    "dim_geography"         : f"{MOUNT_POINT}/raw/dim_geography.csv",
    "dim_technology"        : f"{MOUNT_POINT}/raw/dim_technology.csv",
    "dim_organisation"      : f"{MOUNT_POINT}/raw/dim_organisation.csv",
    "dim_agreement"         : f"{MOUNT_POINT}/raw/dim_agreement.csv",
    "dim_asset"             : f"{MOUNT_POINT}/raw/dim_asset.csv",
    "bridge_plant_org"      : f"{MOUNT_POINT}/raw/bridge_plant_organisation.csv",
    "bridge_plant_tech"     : f"{MOUNT_POINT}/raw/bridge_plant_technology.csv",
}

total_dim_rows = 0
for tbl, path in DIMS.items():
    total_dim_rows += ingest_csv_to_bronze(path, tbl)

print(f"\n  Dimensions total: {total_dim_rows:,} rows")

# COMMAND ----------
# MAGIC %md ### 4. Ingest Fact Tables (with partitioning)

# COMMAND ----------
# SCADA Telemetry — largest table (2.98M rows) — partition by PlantKey
ingest_csv_to_bronze(
    source_path    = f"{MOUNT_POINT}/generated/scada_telemetry_15min.csv",
    table_name     = "scada_telemetry_15min_raw",
    partition_cols = ["PlantKey"]
)

# Daily plant operations
ingest_csv_to_bronze(
    source_path    = f"{MOUNT_POINT}/generated/fact_plant_operations_daily_5yr.csv",
    table_name     = "fact_plant_operations_daily_raw",
    partition_cols = ["PlantKey"]
)

# Outage events
ingest_csv_to_bronze(
    source_path = f"{MOUNT_POINT}/generated/fact_outage_5yr.csv",
    table_name  = "fact_outage_raw"
)

# Maintenance work orders
ingest_csv_to_bronze(
    source_path = f"{MOUNT_POINT}/generated/fact_maintenance_work_order_5yr.csv",
    table_name  = "fact_maintenance_work_order_raw"
)

# Energy sales
ingest_csv_to_bronze(
    source_path = f"{MOUNT_POINT}/generated/fact_energy_sales_monthly_5yr.csv",
    table_name  = "fact_energy_sales_monthly_raw"
)

# HSE incidents
ingest_csv_to_bronze(
    source_path = f"{MOUNT_POINT}/generated/fact_hse_incident_5yr.csv",
    table_name  = "fact_hse_incident_raw"
)

# FX rates
ingest_csv_to_bronze(
    source_path = f"{MOUNT_POINT}/raw/fact_fx_rate_monthly.csv",
    table_name  = "fact_fx_rate_monthly_raw"
)

# COMMAND ----------
# MAGIC %md ### 5. Data Quality Gate — Bronze Row Counts

# COMMAND ----------
quality_results = []
tables = spark.sql(f"SHOW TABLES IN {BRONZE_DB}").collect()
for tbl in tables:
    t = tbl["tableName"]
    cnt = spark.sql(f"SELECT COUNT(*) AS cnt FROM {BRONZE_DB}.{t}").collect()[0]["cnt"]
    quality_results.append({"table": t, "row_count": cnt, "status": "PASS" if cnt > 0 else "FAIL"})

qdf = spark.createDataFrame(quality_results)
display(qdf.orderBy("row_count", ascending=False))

total_rows = sum(r["row_count"] for r in quality_results)
print(f"\n  TOTAL BRONZE ROWS : {total_rows:,}")
print(f"  SCADA alone       : {spark.sql('SELECT COUNT(*) FROM bronze.scada_telemetry_15min_raw').collect()[0][0]:,}")

# COMMAND ----------
# MAGIC %md ### 6. Optimize Delta Tables

# COMMAND ----------
# Optimize largest tables for query performance
for tbl in ["scada_telemetry_15min_raw", "fact_plant_operations_daily_raw"]:
    print(f"  OPTIMIZE {BRONZE_DB}.{tbl} ...")
    spark.sql(f"OPTIMIZE {BRONZE_DB}.{tbl} ZORDER BY (PlantKey)")

print("\nBronze ingestion complete.")
dbutils.notebook.exit("SUCCESS")
