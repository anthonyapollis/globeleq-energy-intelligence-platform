# Databricks notebook source
# MAGIC %md
# MAGIC # Baobab Power Energy Intelligence Platform
# MAGIC ## Notebook 03 — Gold Layer: Executive KPIs & Aggregations
# MAGIC **Purpose:** Build the analytical Gold layer used by Power BI and the ML feature store.
# MAGIC Computes portfolio-level KPIs, plant rankings, and month-over-month trends.
# MAGIC
# MAGIC **Gold tables created:**
# MAGIC | Table | Grain | Description |
# MAGIC |---|---|---|
# MAGIC | `portfolio_daily_kpis` | Day | Portfolio-level generation, availability & ESG |
# MAGIC | `plant_monthly_kpis` | Plant × Month | Per-plant commercial + operational metrics |
# MAGIC | `plant_ranking_ytd` | Plant × Year | Ranked performance table |
# MAGIC | `availability_heatmap` | Plant × Month | Availability % for heatmap visual |
# MAGIC | `revenue_by_region_month` | Region × Month | Revenue aggregated by geography |
# MAGIC | `ml_feature_store_daily` | Plant × Day | Feature-engineered table for ML models |

# COMMAND ----------
SILVER_DB = "silver"
GOLD_DB   = "gold"
GOLD_PATH = "/mnt/baobab_power/gold"
spark.sql(f"CREATE DATABASE IF NOT EXISTS {GOLD_DB} LOCATION '{GOLD_PATH}'")

from pyspark.sql import functions as F
from pyspark.sql.window import Window

# COMMAND ----------
# MAGIC %md ### 1. Portfolio Daily KPIs

# COMMAND ----------
ops = spark.table(f"{SILVER_DB}.fact_plant_operations_daily")
dim = spark.table(f"{SILVER_DB}.dim_plant")

portfolio_daily = (ops
    .groupBy("FullDate","Year","Month","YearMonth")
    .agg(
        F.round(F.sum("NetGenerationMWh"),    2).alias("PortfolioNetGenMWh"),
        F.round(F.sum("EnergyExportedMWh"),   2).alias("PortfolioExportedMWh"),
        F.round(F.sum("CO2AvoidedTonnes"),    2).alias("PortfolioCO2AvoidedTonnes"),
        F.round(F.sum("Scope1EmissionsTonnesCO2e"), 2).alias("PortfolioScope1tCO2e"),
        F.round(
            F.sum(F.col("AvailabilityPct") * F.col("NameplateCapacity")) /
            F.sum("NameplateCapacity"), 3
        ).alias("WeightedAvailabilityPct"),
        F.round(
            F.sum(F.col("CapacityFactorPct") * F.col("NameplateCapacity")) /
            F.sum("NameplateCapacity"), 3
        ).alias("WeightedCapacityFactorPct"),
        F.sum(F.when(F.col("IsRenewable")==1, F.col("NetGenerationMWh"))).alias("RenewableGenMWh"),
        F.sum(F.when(F.col("IsRenewable")==0, F.col("NetGenerationMWh"))).alias("ThermalGenMWh"),
        F.countDistinct("PlantKey").alias("ActivePlants"),
    )
    .withColumn("RenewableSharePct",
                F.round(F.col("RenewableGenMWh") / F.col("PortfolioNetGenMWh") * 100, 2))
    .withColumn("EmissionsIntensity",
                F.round(F.col("PortfolioScope1tCO2e") / F.col("PortfolioNetGenMWh"), 4))
    # Day-over-day delta
    .withColumn("GenMWh_DoD",
                F.col("PortfolioNetGenMWh") -
                F.lag("PortfolioNetGenMWh", 1).over(Window.orderBy("FullDate")))
)

portfolio_daily.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .partitionBy("Year").saveAsTable(f"{GOLD_DB}.portfolio_daily_kpis")
print(f"portfolio_daily_kpis: {portfolio_daily.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 2. Plant Monthly KPIs

# COMMAND ----------
sales = spark.table(f"{SILVER_DB}.fact_energy_sales_monthly")
maint = spark.table(f"{SILVER_DB}.fact_maintenance_work_order")
outage = spark.table(f"{SILVER_DB}.fact_outage")

# Monthly ops aggregation
ops_monthly = (ops
    .groupBy("PlantKey","PlantCode","Country","Region","PrimaryTechnology","IsRenewable",
             "NameplateCapacity","YearMonth","Year","Month")
    .agg(
        F.round(F.sum("NetGenerationMWh"),      2).alias("NetGenMWh"),
        F.round(F.sum("EnergyExportedMWh"),     2).alias("ExportedMWh"),
        F.round(F.avg("AvailabilityPct"),       3).alias("AvailabilityPct"),
        F.round(F.avg("CapacityFactorPct"),     3).alias("CapacityFactorPct"),
        F.round(F.avg("CurtailmentPct"),        3).alias("CurtailmentPct"),
        F.round(F.sum("PlannedDowntimeHours"),  2).alias("PlannedDowntimeHours"),
        F.round(F.sum("ForcedDowntimeHours"),   2).alias("ForcedDowntimeHours"),
        F.round(F.sum("CO2AvoidedTonnes"),      2).alias("CO2AvoidedTonnes"),
        F.round(F.sum("Scope1EmissionsTonnesCO2e"),2).alias("Scope1tCO2e"),
    )
)

# Monthly maintenance cost
maint_monthly = (maint
    .withColumn("YearMonth", F.date_format("OpenedDate","yyyy-MM"))
    .groupBy("PlantKey","YearMonth")
    .agg(
        F.round(F.sum("TotalMaintenanceCostZAR"), 2).alias("MaintenanceCostZAR"),
        F.count("*").alias("WorkOrderCount"),
        F.sum("IsPreventive").alias("PreventiveWOCount"),
        F.sum("IsOverdue").alias("OverdueWOCount"),
    )
)

# Monthly outage hours
outage_monthly = (outage
    .withColumn("YearMonth", F.date_format("StartDateTime","yyyy-MM"))
    .groupBy("PlantKey","YearMonth")
    .agg(
        F.round(F.sum("DurationHours"),              2).alias("TotalOutageHours"),
        F.round(F.sum("EstimatedEnergyLostMWh"),     2).alias("EnergyLostMWh"),
        F.sum("IsForced").alias("ForcedOutageCount"),
        F.round(
            F.sum(F.when(F.col("IsForced")==1, F.col("DurationHours"))), 2
        ).alias("ForcedOutageHours"),
    )
)

plant_monthly = (ops_monthly
    .join(sales.select("PlantKey","YearMonth","EnergySoldMWh","RevenueZAR",
                        "CollectedRevenueZAR","RevPerMWh_ZAR","ContractedTariffUSD"),
          on=["PlantKey","YearMonth"], how="left")
    .join(maint_monthly,  on=["PlantKey","YearMonth"], how="left")
    .join(outage_monthly, on=["PlantKey","YearMonth"], how="left")
    .fillna(0, subset=["MaintenanceCostZAR","TotalOutageHours","EnergyLostMWh",
                        "ForcedOutageCount","WorkOrderCount"])
    # EBITDA proxy: Revenue minus maintenance cost
    .withColumn("EBITDAProxyZAR",
                F.round(F.col("CollectedRevenueZAR") - F.col("MaintenanceCostZAR"), 2))
    .withColumn("MTTR_Hours",
                F.round(F.col("ForcedOutageHours") / F.greatest(F.col("ForcedOutageCount"),F.lit(1)), 2))
)

plant_monthly.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .partitionBy("Year","PlantKey").saveAsTable(f"{GOLD_DB}.plant_monthly_kpis")
print(f"plant_monthly_kpis: {plant_monthly.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 3. Plant YTD Ranking

# COMMAND ----------
plant_ytd = (plant_monthly
    .groupBy("PlantKey","PlantCode","Country","Region","PrimaryTechnology",
             "IsRenewable","NameplateCapacity","Year")
    .agg(
        F.round(F.sum("NetGenMWh"),           2).alias("AnnualNetGenMWh"),
        F.round(F.avg("AvailabilityPct"),     3).alias("AnnualAvailabilityPct"),
        F.round(F.avg("CapacityFactorPct"),   3).alias("AnnualCapacityFactorPct"),
        F.round(F.sum("RevenueZAR"),          2).alias("AnnualRevenueZAR"),
        F.round(F.sum("CO2AvoidedTonnes"),    2).alias("AnnualCO2AvoidedTonnes"),
        F.round(F.sum("MaintenanceCostZAR"),  2).alias("AnnualMaintenanceCostZAR"),
        F.sum("ForcedOutageCount").alias("AnnualForcedOutages"),
        F.round(F.sum("EnergyLostMWh"),       2).alias("AnnualEnergyLostMWh"),
    )
    .withColumn("RevenuePerMW_ZAR",
                F.round(F.col("AnnualRevenueZAR") / F.col("NameplateCapacity"), 2))
    .withColumn("AvailRank",
                F.rank().over(Window.partitionBy("Year").orderBy(F.desc("AnnualAvailabilityPct"))))
    .withColumn("GenRank",
                F.rank().over(Window.partitionBy("Year").orderBy(F.desc("AnnualNetGenMWh"))))
    .withColumn("RevenueRank",
                F.rank().over(Window.partitionBy("Year").orderBy(F.desc("AnnualRevenueZAR"))))
)

plant_ytd.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"{GOLD_DB}.plant_ranking_ytd")
print(f"plant_ranking_ytd: {plant_ytd.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 4. Availability Heatmap

# COMMAND ----------
heatmap = (ops_monthly
    .select("PlantKey","PlantCode","PrimaryTechnology","Country","YearMonth","AvailabilityPct")
    .withColumn("AvailBand",
        F.when(F.col("AvailabilityPct") >= 95, ">=95%")
        .when(F.col("AvailabilityPct") >= 85, "85–95%")
        .when(F.col("AvailabilityPct") >= 70, "70–85%")
        .otherwise("<70%"))
)

heatmap.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"{GOLD_DB}.availability_heatmap")
print(f"availability_heatmap: {heatmap.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 5. Revenue by Region × Month

# COMMAND ----------
rev_region = (plant_monthly
    .groupBy("Region","YearMonth","Year","Month")
    .agg(
        F.round(F.sum("RevenueZAR"),           2).alias("TotalRevenueZAR"),
        F.round(F.sum("CollectedRevenueZAR"),  2).alias("CollectedRevenueZAR"),
        F.round(F.sum("NetGenMWh"),            2).alias("TotalNetGenMWh"),
        F.countDistinct("PlantKey").alias("PlantCount"),
    )
    .withColumn("CollectionRate",
                F.round(F.col("CollectedRevenueZAR") / F.col("TotalRevenueZAR"), 4))
)

rev_region.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"{GOLD_DB}.revenue_by_region_month")
print(f"revenue_by_region_month: {rev_region.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 6. ML Feature Store (Daily)

# COMMAND ----------
# Outage flag at daily plant level (used as ML target)
outage_daily_flag = (outage
    .withColumn("DateKey", F.date_format("StartDateTime","yyyyMMdd").cast("int"))
    .groupBy("PlantKey","DateKey")
    .agg(
        F.sum("IsForced").alias("ForcedOutageDay"),
        F.sum("DurationHours").alias("TotalOutageHoursDay"),
    )
    .withColumn("HasForcedOutage", F.when(F.col("ForcedOutageDay") > 0, 1).otherwise(0))
)

feature_store = (ops
    .join(outage_daily_flag, on=["PlantKey","DateKey"], how="left")
    .fillna(0, subset=["ForcedOutageDay","TotalOutageHoursDay","HasForcedOutage"])
    # Lag features (t-1, t-7)
    .withColumn("Avail_Lag1",  F.lag("AvailabilityPct", 1).over(
        Window.partitionBy("PlantKey").orderBy("DateKey")))
    .withColumn("Avail_Lag7",  F.lag("AvailabilityPct", 7).over(
        Window.partitionBy("PlantKey").orderBy("DateKey")))
    .withColumn("Gen_Lag1",    F.lag("NetGenerationMWh", 1).over(
        Window.partitionBy("PlantKey").orderBy("DateKey")))
    .withColumn("ForcedOut_Lag1", F.lag("HasForcedOutage", 1).over(
        Window.partitionBy("PlantKey").orderBy("DateKey")))
    .withColumn("ForcedOut_Lag7", F.lag("HasForcedOutage", 7).over(
        Window.partitionBy("PlantKey").orderBy("DateKey")))
    # Target: forced outage in next 7 days
    .withColumn("ForcedOutage_Next7d",
        F.max("HasForcedOutage").over(
            Window.partitionBy("PlantKey")
            .orderBy("DateKey")
            .rowsBetween(1, 7)))
    .fillna(0, subset=["Avail_Lag1","Avail_Lag7","Gen_Lag1",
                        "ForcedOut_Lag1","ForcedOut_Lag7","ForcedOutage_Next7d"])
    .select(
        "PlantKey","PlantCode","PrimaryTechnology","Country","Region",
        "NameplateCapacity","DateKey","FullDate","Year","Month","YearMonth",
        "NetGenerationMWh","AvailabilityPct","CapacityFactorPct",
        "CurtailmentPct","PlannedDowntimeHours","ForcedDowntimeHours",
        "CO2AvoidedTonnes","Scope1tCO2e","AvailabilityPct_7d","AvailabilityPct_30d",
        "GenMWh_7d","GenMWh_30d",
        "Avail_Lag1","Avail_Lag7","Gen_Lag1","ForcedOut_Lag1","ForcedOut_Lag7",
        "HasForcedOutage","ForcedOutage_Next7d","IsRenewable",
    )
)

feature_store.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .partitionBy("Year","PlantKey").saveAsTable(f"{GOLD_DB}.ml_feature_store_daily")
print(f"ml_feature_store_daily: {feature_store.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 7. Gold Layer Validation Summary

# COMMAND ----------
# ── Section 7: OPTIMIZE + ZORDER ──────────────────────────────────────────────
# Delta Lake: compact small files and co-locate data for the most common
# filter patterns (PlantKey first — nearly every PBI query filters by plant).
# Run after every full load; skip on incremental if row delta < 5%.

print("Optimising Delta tables...")

OPTIMIZE_TARGETS = [
    ("fact_plant_operations_gold",   ["PlantKey", "DateKey"]),
    ("fact_ml_feature_store",        ["PlantKey", "DateKey"]),
    ("fact_portfolio_kpis_monthly",  ["PlantKey"]),
    ("dim_plant_gold",               ["PlantKey"]),
]

for tbl, zorder_cols in OPTIMIZE_TARGETS:
    full = f"{GOLD_DB}.{tbl}"
    cols = ", ".join(zorder_cols)
    try:
        spark.sql(f"OPTIMIZE {full} ZORDER BY ({cols})")
        print(f"  OPTIMIZE ZORDER {full} BY ({cols}) — done")
    except Exception as e:
        print(f"  OPTIMIZE {full} — skipped: {e}")

print("Delta optimisation complete.\n")

# COMMAND ----------
gold_tables = spark.sql(f"SHOW TABLES IN {GOLD_DB}").collect()
summary = [(t["tableName"],
            spark.sql(f"SELECT COUNT(*) FROM {GOLD_DB}.{t['tableName']}").collect()[0][0])
           for t in gold_tables]

print("\n" + "="*45)
print("GOLD LAYER — TABLE ROW COUNTS")
print("="*45)
for tbl, cnt in sorted(summary, key=lambda x: x[1], reverse=True):
    print(f"  {tbl:<35} {cnt:>8,}")
print("="*45)

dbutils.notebook.exit("SUCCESS")
