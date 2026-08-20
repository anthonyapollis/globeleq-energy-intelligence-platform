# Databricks notebook source
# MAGIC %md
# MAGIC # Baobab Power Energy Intelligence Platform
# MAGIC ## Notebook 02 — Silver Layer: Cleansing, Enrichment & Standardisation
# MAGIC **Purpose:** Apply data quality rules, join dimensions, engineer time features,
# MAGIC and produce publication-ready Silver Delta tables.
# MAGIC
# MAGIC **Key transformations applied:**
# MAGIC - Cast columns to correct types & handle nulls
# MAGIC - Derive `DimDate` surrogate keys from timestamps
# MAGIC - Tag "SUSPECT" SCADA readings; remove duplicates
# MAGIC - Join plant master for technology / region context
# MAGIC - Compute hourly aggregations from 15-min SCADA
# MAGIC - Add rolling 7-day and 30-day averages

# COMMAND ----------
BRONZE_DB = "bronze"
SILVER_DB = "silver"
SILVER_PATH = "/mnt/baobab_power/silver"
spark.sql(f"CREATE DATABASE IF NOT EXISTS {SILVER_DB} LOCATION '{SILVER_PATH}'")

from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import *

# COMMAND ----------
# MAGIC %md ### 1. Clean Dimension: DimPlant (Silver)

# COMMAND ----------
dim_plant_raw = spark.table(f"{BRONZE_DB}.dim_plant")

dim_plant_silver = (dim_plant_raw
    .withColumn("PlantKey",         F.col("PlantKey").cast(IntegerType()))
    .withColumn("NameplateCapacity",F.col("NameplateCapacity").cast(DoubleType()))
    .withColumn("AgreementTermYears",F.col("AgreementTermYears").cast(DoubleType()))
    .withColumn("BrochureAnnualGenerationGWh",
                F.col("BrochureAnnualGenerationGWh").cast(DoubleType()))
    .withColumn("IsRenewable",
                F.when(F.col("PrimaryTechnology").isin(
                    ["Solar PV","Solar PV + BESS","Wind","Geothermal"]), F.lit(1)
                ).otherwise(F.lit(0)))
    .withColumn("IsOperating",
                F.when(F.col("ProjectStatus") == "Operating", F.lit(1)).otherwise(F.lit(0)))
    .dropDuplicates(["PlantKey"])
    .drop("_ingested_at","_pipeline_run_id","_ingested_by","_source_file")
)

dim_plant_silver.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"{SILVER_DB}.dim_plant")
print(f"dim_plant (silver): {dim_plant_silver.count()} rows")

# COMMAND ----------
# MAGIC %md ### 2. Clean SCADA Telemetry → Silver (hourly aggregated)

# COMMAND ----------
scada_raw = spark.table(f"{BRONZE_DB}.scada_telemetry_15min_raw")

# Cast and derive time features
scada_typed = (scada_raw
    .withColumn("Timestamp",         F.to_timestamp("Timestamp"))
    .withColumn("PlantKey",          F.col("PlantKey").cast(IntegerType()))
    .withColumn("ActivePowerMW",     F.col("ActivePowerMW").cast(DoubleType()))
    .withColumn("ReactivePowerMVAR", F.col("ReactivePowerMVAR").cast(DoubleType()))
    .withColumn("GridFrequencyHz",   F.col("GridFrequencyHz").cast(DoubleType()))
    .withColumn("AmbientTemperatureC",F.col("AmbientTemperatureC").cast(DoubleType()))
    .withColumn("SolarIrradianceWm2",F.col("SolarIrradianceWm2").cast(DoubleType()))
    .withColumn("WindSpeedMs",       F.col("WindSpeedMs").cast(DoubleType()))
    .withColumn("CurtailmentFactor", F.col("CurtailmentFactor").cast(DoubleType()))
    .withColumn("TransformerTempC",  F.col("TransformerTempC").cast(DoubleType()))
    .withColumn("Date",              F.to_date("Timestamp"))
    .withColumn("HourOfDay",         F.hour("Timestamp"))
    .withColumn("DayOfWeek",         F.dayofweek("Timestamp"))
    .withColumn("Month",             F.month("Timestamp"))
    .withColumn("Year",              F.year("Timestamp"))
    .withColumn("CalendarYearMonth", F.date_format("Timestamp","yyyy-MM"))
    .withColumn("DateKey",           F.date_format("Timestamp","yyyyMMdd").cast(IntegerType()))
    # Energy generated this 15-min interval (MWh)
    .withColumn("EnergyMWh_15min",   F.col("ActivePowerMW") * F.lit(0.25))
    # Data quality flag
    .withColumn("IsGoodData",
                F.when(F.col("DataQualityFlag") == "GOOD", F.lit(1)).otherwise(F.lit(0)))
)

# Remove full duplicates
scada_deduped = scada_typed.dropDuplicates(["Timestamp","PlantKey"])

# Hourly aggregation (more manageable size for downstream ML)
scada_hourly = (scada_deduped
    .withColumn("HourTimestamp",
                F.date_trunc("hour", F.col("Timestamp")))
    .groupBy("HourTimestamp","PlantKey","PlantCode","Technology","Country","Date",
             "HourOfDay","DayOfWeek","Month","Year","CalendarYearMonth","DateKey")
    .agg(
        F.avg("ActivePowerMW").alias("AvgPowerMW"),
        F.max("ActivePowerMW").alias("MaxPowerMW"),
        F.min("ActivePowerMW").alias("MinPowerMW"),
        F.sum("EnergyMWh_15min").alias("EnergyMWh"),
        F.avg("SolarIrradianceWm2").alias("AvgIrradianceWm2"),
        F.avg("WindSpeedMs").alias("AvgWindSpeedMs"),
        F.avg("AmbientTemperatureC").alias("AvgAmbientTempC"),
        F.avg("GridFrequencyHz").alias("AvgFrequencyHz"),
        F.avg("TransformerTempC").alias("AvgTransformerTempC"),
        F.avg("CurtailmentFactor").alias("AvgCurtailmentFactor"),
        F.sum("IsGoodData").alias("GoodReadingCount"),
        F.count("*").alias("TotalReadingCount"),
        F.sum(F.when(F.col("AlarmCode") == "OUTAGE", 1).otherwise(0)).alias("OutageIntervals"),
        F.sum(F.when(F.col("AlarmCode") == "CURTAILMENT", 1).otherwise(0)).alias("CurtailmentIntervals"),
    )
    .withColumn("DataQualityScore",
                F.round(F.col("GoodReadingCount") / F.col("TotalReadingCount") * 100, 2))
    .withColumn("AvailabilityHour",
                F.when(F.col("OutageIntervals") < 4, F.lit(1)).otherwise(F.lit(0)))
)

# Join plant dimension for context
scada_enriched = scada_hourly.join(
    dim_plant_silver.select("PlantKey","NameplateCapacity","Region","IsRenewable","AgreementType"),
    on="PlantKey", how="left"
).withColumn("CapacityFactorPct",
             F.round(F.col("AvgPowerMW") / F.col("NameplateCapacity") * 100, 3))

(scada_enriched.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema","true")
    .partitionBy("PlantKey","Year")
    .saveAsTable(f"{SILVER_DB}.scada_hourly"))

print(f"scada_hourly (silver): {scada_enriched.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 3. Clean Daily Operations

# COMMAND ----------
ops_raw = spark.table(f"{BRONZE_DB}.fact_plant_operations_daily_raw")

ops_silver = (ops_raw
    .withColumn("DateKey",                   F.col("DateKey").cast(IntegerType()))
    .withColumn("PlantKey",                  F.col("PlantKey").cast(IntegerType()))
    .withColumn("GrossGenerationMWh",        F.col("GrossGenerationMWh").cast(DoubleType()))
    .withColumn("NetGenerationMWh",          F.col("NetGenerationMWh").cast(DoubleType()))
    .withColumn("EnergyExportedMWh",         F.col("EnergyExportedMWh").cast(DoubleType()))
    .withColumn("AvailabilityPct",           F.col("AvailabilityPct").cast(DoubleType()))
    .withColumn("CapacityFactorPct",         F.col("CapacityFactorPct").cast(DoubleType()))
    .withColumn("CurtailmentPct",            F.col("CurtailmentPct").cast(DoubleType()))
    .withColumn("PlannedDowntimeHours",      F.col("PlannedDowntimeHours").cast(DoubleType()))
    .withColumn("ForcedDowntimeHours",       F.col("ForcedDowntimeHours").cast(DoubleType()))
    .withColumn("Scope1EmissionsTonnesCO2e", F.col("Scope1EmissionsTonnesCO2e").cast(DoubleType()))
    .withColumn("CO2AvoidedTonnes",          F.col("CO2AvoidedTonnes").cast(DoubleType()))
    .withColumn("FullDate",
                F.to_date(F.col("DateKey").cast(StringType()), "yyyyMMdd"))
    .withColumn("Year",  F.year("FullDate"))
    .withColumn("Month", F.month("FullDate"))
    .withColumn("YearMonth", F.date_format("FullDate","yyyy-MM"))
    .dropDuplicates(["DateKey","PlantKey"])
    # Rolling 7-day availability
    .join(dim_plant_silver.select("PlantKey","NameplateCapacity","PrimaryTechnology",
                                  "Region","Country","IsRenewable"),
          on="PlantKey", how="left")
)

# 7-day rolling availability per plant
w7  = Window.partitionBy("PlantKey").orderBy("DateKey").rowsBetween(-6, 0)
w30 = Window.partitionBy("PlantKey").orderBy("DateKey").rowsBetween(-29, 0)

ops_silver = (ops_silver
    .withColumn("AvailabilityPct_7d",  F.round(F.avg("AvailabilityPct").over(w7),  3))
    .withColumn("AvailabilityPct_30d", F.round(F.avg("AvailabilityPct").over(w30), 3))
    .withColumn("GenMWh_7d",           F.round(F.sum("NetGenerationMWh").over(w7),  3))
    .withColumn("GenMWh_30d",          F.round(F.sum("NetGenerationMWh").over(w30), 3))
    .drop("_ingested_at","_pipeline_run_id","_ingested_by","_source_file")
)

(ops_silver.write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema","true")
    .partitionBy("Year","PlantKey")
    .saveAsTable(f"{SILVER_DB}.fact_plant_operations_daily"))

print(f"fact_plant_operations_daily (silver): {ops_silver.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 4. Clean Outage Events

# COMMAND ----------
outage_raw = spark.table(f"{BRONZE_DB}.fact_outage_raw")

outage_silver = (outage_raw
    .withColumn("OutageID",    F.col("OutageID").cast(IntegerType()))
    .withColumn("PlantKey",    F.col("PlantKey").cast(IntegerType()))
    .withColumn("AssetKey",    F.col("AssetKey").cast(IntegerType()))
    .withColumn("StartDateTime", F.to_timestamp("StartDateTime"))
    .withColumn("EndDateTime",   F.to_timestamp("EndDateTime"))
    .withColumn("DurationHours", F.col("DurationHours").cast(DoubleType()))
    .withColumn("CapacityLostMW",       F.col("CapacityLostMW").cast(DoubleType()))
    .withColumn("EstimatedEnergyLostMWh",F.col("EstimatedEnergyLostMWh").cast(DoubleType()))
    .withColumn("Year",  F.year("StartDateTime"))
    .withColumn("Month", F.month("StartDateTime"))
    .withColumn("IsForced",  F.when(F.col("OutageType")=="Forced", 1).otherwise(0))
    .withColumn("IsPlanned", F.when(F.col("OutageType")=="Planned",1).otherwise(0))
    .withColumn("IsCritical",F.when(F.col("Severity")=="Critical",1).otherwise(0))
    .dropDuplicates(["OutageID"])
    .join(dim_plant_silver.select("PlantKey","PlantCode","Country","Region","PrimaryTechnology"),
          on="PlantKey", how="left")
    .drop("_ingested_at","_pipeline_run_id","_ingested_by","_source_file")
)

outage_silver.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"{SILVER_DB}.fact_outage")
print(f"fact_outage (silver): {outage_silver.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 5. Clean Maintenance Work Orders

# COMMAND ----------
maint_raw = spark.table(f"{BRONZE_DB}.fact_maintenance_work_order_raw")

maint_silver = (maint_raw
    .withColumn("WorkOrderID",  F.col("WorkOrderID").cast(IntegerType()))
    .withColumn("PlantKey",     F.col("PlantKey").cast(IntegerType()))
    .withColumn("AssetKey",     F.col("AssetKey").cast(IntegerType()))
    .withColumn("OpenedDate",   F.to_date("OpenedDate","yyyy-MM-dd"))
    .withColumn("TargetCloseDate", F.to_date("TargetCloseDate","yyyy-MM-dd"))
    .withColumn("ClosedDate",
                F.when(F.col("ClosedDate") == "", F.lit(None))
                 .otherwise(F.to_date("ClosedDate","yyyy-MM-dd")))
    .withColumn("ActualLabourHours",       F.col("ActualLabourHours").cast(DoubleType()))
    .withColumn("TotalMaintenanceCostZAR", F.col("TotalMaintenanceCostZAR").cast(DoubleType()))
    .withColumn("IsPreventive",            F.col("IsPreventive").cast(IntegerType()))
    .withColumn("IsOverdue",
                F.when(
                    (F.col("WorkOrderStatus").isin("Open","In Progress")) &
                    (F.col("TargetCloseDate") < F.current_date()), F.lit(1)
                ).otherwise(F.lit(0)))
    .withColumn("DaysToClose",
                F.when(F.col("ClosedDate").isNotNull(),
                    F.datediff("ClosedDate","OpenedDate")).otherwise(F.lit(None)))
    .withColumn("Year",  F.year("OpenedDate"))
    .withColumn("Month", F.month("OpenedDate"))
    .dropDuplicates(["WorkOrderID"])
    .join(dim_plant_silver.select("PlantKey","PlantCode","Country","Region"),
          on="PlantKey", how="left")
    .drop("_ingested_at","_pipeline_run_id","_ingested_by","_source_file")
)

maint_silver.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"{SILVER_DB}.fact_maintenance_work_order")
print(f"fact_maintenance_work_order (silver): {maint_silver.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 6. Clean Energy Sales Monthly

# COMMAND ----------
sales_raw = spark.table(f"{BRONZE_DB}.fact_energy_sales_monthly_raw")

sales_silver = (sales_raw
    .withColumn("PlantKey",            F.col("PlantKey").cast(IntegerType()))
    .withColumn("EnergySoldMWh",       F.col("EnergySoldMWh").cast(DoubleType()))
    .withColumn("ContractedTariffUSD", F.col("ContractedTariffUSD").cast(DoubleType()))
    .withColumn("RevenueUSD",          F.col("RevenueUSD").cast(DoubleType()))
    .withColumn("USDZAR_Rate",         F.col("USDZAR_Rate").cast(DoubleType()))
    .withColumn("RevenueZAR",          F.col("RevenueZAR").cast(DoubleType()))
    .withColumn("SettlementCollectionPct",F.col("SettlementCollectionPct").cast(DoubleType()))
    .withColumn("CollectedRevenueZAR", F.col("CollectedRevenueZAR").cast(DoubleType()))
    .withColumn("MonthDate",           F.to_date("YearMonth","yyyy-MM"))
    .withColumn("Year",  F.year("MonthDate"))
    .withColumn("Month", F.month("MonthDate"))
    .withColumn("RevPerMWh_ZAR",
                F.round(F.col("RevenueZAR") / F.col("EnergySoldMWh"), 2))
    .dropDuplicates(["YearMonth","PlantKey"])
    .join(dim_plant_silver.select("PlantKey","PlantCode","Country","Region",
                                  "PrimaryTechnology","IsRenewable","AgreementType"),
          on="PlantKey", how="left")
    .drop("_ingested_at","_pipeline_run_id","_ingested_by","_source_file")
)

sales_silver.write.format("delta").mode("overwrite").option("overwriteSchema","true") \
    .saveAsTable(f"{SILVER_DB}.fact_energy_sales_monthly")
print(f"fact_energy_sales_monthly (silver): {sales_silver.count():,} rows")

# COMMAND ----------
# MAGIC %md ### 7. Validate Silver Layer

# COMMAND ----------
silver_tables = spark.sql(f"SHOW TABLES IN {SILVER_DB}").collect()
validation = []
for tbl in silver_tables:
    t = tbl["tableName"]
    cnt  = spark.sql(f"SELECT COUNT(*) AS c FROM {SILVER_DB}.{t}").collect()[0]["c"]
    nulls = spark.sql(f"SELECT COUNT(*) AS c FROM {SILVER_DB}.{t} WHERE PlantKey IS NULL").collect()[0]["c"]
    validation.append({"table": t, "row_count": cnt, "null_plantkeys": nulls,
                        "status": "PASS" if cnt > 0 and nulls == 0 else "WARN"})

vdf = spark.createDataFrame(validation)
display(vdf.orderBy("row_count", ascending=False))

print("\nSilver transformation complete.")

# COMMAND ----------
# MAGIC %md ### 8. Meter Data Quality — Raw / Clean / Impute Pipeline
# MAGIC
# MAGIC **Why this step exists:** The dirty data injector seeded realistic SCADA issues into
# MAGIC the Bronze layer: 57 K null sensor dropouts, 4.5 K fault-code 999.9 readings, 5.4 K
# MAGIC out-of-range power values, 3.6 K frequency spikes, 2.4 K stale/frozen readings.
# MAGIC
# MAGIC This step:
# MAGIC 1. Builds a complete hourly time-spine (all plant × hour combinations 2020–2024)
# MAGIC 2. Left-joins actual readings → detects missing intervals
# MAGIC 3. Flags outliers with IQR method (per plant × hour-of-day)
# MAGIC 4. Imputes: forward-fill ≤ 2 hours; plant × hour-of-day median for longer gaps
# MAGIC 5. Writes `FactMeterReadingHourly` with raw / clean / quality columns preserved
# MAGIC 6. Writes `FactDataQualityEvent` — one row per issue, immutable audit log

# COMMAND ----------
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.types import DoubleType, StringType, IntegerType, TimestampType

IQR_MULTIPLIER   = 2.5   # number of IQRs beyond Q1/Q3 to flag outlier
MAX_FFILL_HOURS  = 2     # forward-fill gaps ≤ this many consecutive missing hours

# Build hourly time spine: 2020-01-01 00:00 → 2024-12-31 23:00
hour_spine = (
    spark.range(0, 17 * 5 * 365 * 24 + 17 * 24)   # generous upper bound
    .selectExpr("(id * 3600) AS sec_offset")
    .withColumn("HourTimestamp",
                (F.to_timestamp(F.lit("2020-01-01 00:00:00"))
                 + F.expr("make_interval(0,0,0,0,0,CAST(sec_offset AS INT))")).cast(TimestampType()))
    .filter(F.col("HourTimestamp") <= F.lit("2024-12-31 23:00:00"))
)

# Cross join spine with plant list (PlantKey 1–17, operating plants only)
plant_keys = (dim_plant_silver
    .filter(F.col("IsOperating") == 1)
    .select("PlantKey","NameplateCapacity")
)
full_spine = hour_spine.crossJoin(plant_keys)

# Bring in the Silver hourly SCADA aggregation
scada_h = spark.table(f"{SILVER_DB}.scada_hourly").select(
    "HourTimestamp","PlantKey",
    F.col("EnergyMWh").alias("RawEnergyMWh"),
    "AvgPowerMW","NameplateCapacity","DataQualityScore","GoodReadingCount","TotalReadingCount"
)

# Left join to detect missing intervals
spine_joined = (
    full_spine.alias("s")
    .join(scada_h.alias("h"),
          (F.col("s.HourTimestamp") == F.col("h.HourTimestamp")) &
          (F.col("s.PlantKey")      == F.col("h.PlantKey")),
          how="left")
    .select(
        F.col("s.HourTimestamp"),
        F.col("s.PlantKey"),
        F.col("s.NameplateCapacity").alias("CapacityMW"),
        F.col("h.RawEnergyMWh"),
        F.col("h.DataQualityScore")
    )
)

# ── Outlier detection (IQR per plant × hour-of-day) ──────────────────────
w_plant_hour = Window.partitionBy(
    "PlantKey",
    F.hour(F.col("HourTimestamp"))
)

spine_flagged = (spine_joined
    .withColumn("HourOfDay", F.hour("HourTimestamp"))
    .withColumn("Q1",  F.percentile_approx("RawEnergyMWh", 0.25).over(w_plant_hour))
    .withColumn("Q3",  F.percentile_approx("RawEnergyMWh", 0.75).over(w_plant_hour))
    .withColumn("IQR", F.col("Q3") - F.col("Q1"))
    .withColumn("IsOutlier",
        F.when(
            F.col("RawEnergyMWh").isNotNull() & (
                (F.col("RawEnergyMWh") < F.col("Q1") - IQR_MULTIPLIER * F.col("IQR")) |
                (F.col("RawEnergyMWh") > F.col("Q3") + IQR_MULTIPLIER * F.col("IQR")) |
                (F.col("RawEnergyMWh") < 0) |
                (F.col("RawEnergyMWh") > F.col("CapacityMW") * 1.15)   # >115% capacity = impossible
            ), F.lit(1)
        ).otherwise(F.lit(0))
    )
    .withColumn("IsMissing",
        F.when(F.col("RawEnergyMWh").isNull(), F.lit(1)).otherwise(F.lit(0))
    )
    .drop("Q1","Q3","IQR")
)

# ── Imputation ───────────────────────────────────────────────────────────
w_time_ordered = Window.partitionBy("PlantKey").orderBy("HourTimestamp")

# Null out outlier values so they get imputed the same way as missing
spine_to_impute = spine_flagged.withColumn(
    "ValueForImpute",
    F.when((F.col("IsMissing") == 1) | (F.col("IsOutlier") == 1), F.lit(None))
     .otherwise(F.col("RawEnergyMWh"))
)

# Forward fill (last observation carried forward, max 2 hours)
spine_ffill = (spine_to_impute
    .withColumn("LOCF",  F.last("ValueForImpute", ignorenulls=True)
                          .over(w_time_ordered
                                .rowsBetween(-MAX_FFILL_HOURS, 0)))
    .withColumn("ConsecutiveNulls",
                F.sum(F.when(F.col("ValueForImpute").isNull(), 1).otherwise(0))
                 .over(w_time_ordered.rowsBetween(-MAX_FFILL_HOURS, 0)))
    .withColumn("FFillValue",
                F.when(F.col("ConsecutiveNulls") <= MAX_FFILL_HOURS,
                       F.col("LOCF")).otherwise(F.lit(None)))
)

# Plant × hour-of-day median (fallback for longer gaps)
hourly_median = (spine_flagged
    .filter(F.col("IsMissing") == 0)
    .filter(F.col("IsOutlier") == 0)
    .groupBy("PlantKey","HourOfDay")
    .agg(F.percentile_approx("RawEnergyMWh", 0.5).alias("HourlyMedianMWh"))
)

spine_imputed = (spine_ffill
    .join(hourly_median, on=["PlantKey","HourOfDay"], how="left")
    .withColumn("CleanEnergyMWh",
        F.when(F.col("ValueForImpute").isNotNull(), F.col("ValueForImpute"))
         .when(F.col("FFillValue").isNotNull(),      F.col("FFillValue"))
         .when(F.col("HourlyMedianMWh").isNotNull(), F.col("HourlyMedianMWh"))
         .otherwise(F.lit(0.0))
    )
    .withColumn("IsImputed",
        F.when(
            ((F.col("IsMissing") == 1) | (F.col("IsOutlier") == 1)) &
             F.col("CleanEnergyMWh").isNotNull(), F.lit(1)
        ).otherwise(F.lit(0))
    )
    .withColumn("ImputationMethod",
        F.when(F.col("IsImputed") == 0, F.lit(None))
         .when(F.col("FFillValue").isNotNull(), F.lit("ForwardFill"))
         .when(F.col("HourlyMedianMWh").isNotNull(), F.lit("HourlyMedian"))
         .otherwise(F.lit("Zero"))
    )
    .withColumn("QualityStatus",
        F.when(F.col("IsMissing") == 1, F.lit("MISSING"))
         .when(F.col("IsOutlier") == 1, F.lit("OUTLIER"))
         .when(F.col("IsImputed") == 1, F.lit("IMPUTED"))
         .when(F.col("DataQualityScore") < 75, F.lit("SUSPECT"))
         .otherwise(F.lit("GOOD"))
    )
    .withColumn("DateKey",
                F.date_format("HourTimestamp","yyyyMMdd").cast(IntegerType()))
    .withColumn("TimeKey",
                F.hour("HourTimestamp"))
    .withColumn("MeterKey",    F.col("PlantKey"))   # one revenue meter per plant (MeterKey=PlantKey, see V2 DDL seed)
    .withColumn("SourceSystem", F.lit("SCADA"))
    .withColumn("IsSynthetic",  F.lit(1))
)

# Write FactMeterReadingHourly to Silver
(spine_imputed
    .select("DateKey","TimeKey","PlantKey","MeterKey",
            "RawEnergyMWh","CleanEnergyMWh","QualityStatus",
            "IsMissing","IsOutlier","IsImputed","ImputationMethod",
            "SourceSystem","IsSynthetic")
    .write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema","true")
    .partitionBy("PlantKey")
    .saveAsTable(f"{SILVER_DB}.fact_meter_reading_hourly")
)
print(f"fact_meter_reading_hourly (silver): {spine_imputed.count():,} rows")

# ── FactDataQualityEvent audit log ──────────────────────────────────────
import datetime

dq_events = (
    spine_flagged
    .filter((F.col("IsMissing") == 1) | (F.col("IsOutlier") == 1))
    .withColumn("DateKey",
                F.date_format("HourTimestamp","yyyyMMdd").cast(IntegerType()))
    .withColumn("TimeKey", F.hour("HourTimestamp"))
    .withColumn("MeterKey", F.col("PlantKey"))
    .withColumn("EventType",
        F.when(F.col("IsMissing") == 1, F.lit("MISSING"))
         .when(
             (F.col("RawEnergyMWh") < 0) |
             (F.col("RawEnergyMWh") > F.col("CapacityMW") * 1.15),
             F.lit("IMPOSSIBLE_VALUE"))
         .otherwise(F.lit("OUTLIER"))
    )
    .withColumn("AffectedColumn",    F.lit("EnergyMWh"))
    .withColumn("RawValue",          F.col("RawEnergyMWh").cast(StringType()))
    .withColumn("CorrectedValue",    F.lit(None).cast(StringType()))  # populated after imputation pass
    .withColumn("QualityRule",
        F.when(F.col("IsMissing") == 1,
               F.lit("Interval absent from SCADA — no reading received"))
         .when(F.col("RawEnergyMWh") < 0,
               F.lit("Negative power reading — physically impossible"))
         .when(F.col("RawEnergyMWh") > F.col("CapacityMW") * 1.15,
               F.concat(F.lit("Power exceeds 115% nameplate ("),
                        F.round(F.col("CapacityMW"),0).cast(StringType()),
                        F.lit(" MW)")))
         .otherwise(F.lit("IQR outlier: reading outside Q1-2.5*IQR / Q3+2.5*IQR range"))
    )
    .withColumn("ResolutionStatus",  F.lit("OPEN"))
    .withColumn("DetectedByProcess", F.lit("Silver_Transform_02"))
    .withColumn("DetectedAt",        F.lit(datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")))
    .withColumn("IsSynthetic",       F.lit(1))
    .select("DateKey","TimeKey","PlantKey","MeterKey",
            "EventType","AffectedColumn","RawValue","CorrectedValue",
            "QualityRule","ResolutionStatus","DetectedByProcess",
            "DetectedAt","IsSynthetic")
)

(dq_events
    .write
    .format("delta")
    .mode("overwrite")
    .option("overwriteSchema","true")
    .partitionBy("PlantKey")
    .saveAsTable(f"{SILVER_DB}.fact_data_quality_event")
)

total_issues  = dq_events.count()
missing_cnt   = dq_events.filter(F.col("EventType") == "MISSING").count()
outlier_cnt   = dq_events.filter(F.col("EventType") == "OUTLIER").count()
impossible_cnt= dq_events.filter(F.col("EventType") == "IMPOSSIBLE_VALUE").count()

print(f"\nfact_data_quality_event (silver): {total_issues:,} events logged")
print(f"  MISSING:          {missing_cnt:,}")
print(f"  OUTLIER:          {outlier_cnt:,}")
print(f"  IMPOSSIBLE_VALUE: {impossible_cnt:,}")
print(f"\nImputation summary:")
print(spark.table(f"{SILVER_DB}.fact_meter_reading_hourly")
      .groupBy("QualityStatus","ImputationMethod")
      .count()
      .orderBy("QualityStatus")
      .toPandas().to_string(index=False))

print("\nSilver transformation complete.")
dbutils.notebook.exit("SUCCESS")
