"""
Baobab Power Energy Intelligence Platform
Dirty Data Injector — realistic data quality issues for Bronze → Silver pipeline

Dirty patterns injected per table:
  SCADA telemetry   : null sensors, duplicates, stale readings, bad range values,
                      frequency spikes, fault codes (999.9), mixed timestamp formats
  Daily operations  : availability >100%, net > gross gen, null CF, duplicates
  Maintenance WOs   : close before open, zero cost, closed+no-date, corrupt priority
  Energy sales      : ZAR magnitude error (×1000), collection >1.0, duplicate months
  Outages           : end before start, zero duration, null cause
  HSE incidents     : future dates, null lost-work-days on LTI rows

Outputs:  data/dirty/<table>_dirty.csv   (used by Bronze layer)
          data/dirty/dirty_manifest.csv  (documents every injected issue)
"""

import numpy as np
import pandas as pd
import os, random, json
from datetime import datetime, timedelta

SEED = 99
np.random.seed(SEED)
random.seed(SEED)

ROOT    = r"C:\Users\Anthony.DESKTOP-ES5HL78\Documents\Baobab_Power_Energy_Intelligence_Platform"
SRC     = os.path.join(ROOT, "data", "generated")
OUT     = os.path.join(ROOT, "data", "dirty")
os.makedirs(OUT, exist_ok=True)

manifest = []   # track every injected issue

def log_issue(table, column, pattern, count):
    manifest.append({"table": table, "column": column,
                      "dirty_pattern": pattern, "rows_affected": count})
    print(f"   [{pattern:<35}] {count:>6,} rows  → {table}.{column}")

def pct_idx(df, pct):
    """Random row indices covering ~pct% of the dataframe."""
    n = max(1, int(len(df) * pct / 100))
    return np.random.choice(df.index, size=n, replace=False)


# ══════════════════════════════════════════════════════════════
# 1. SCADA TELEMETRY  (~3M rows — chunked to save RAM)
# ══════════════════════════════════════════════════════════════
def dirty_scada():
    print("\n[1/6] Injecting dirt into SCADA telemetry (~3M rows)…")
    src = os.path.join(SRC, "scada_telemetry_15min.csv")
    dst = os.path.join(OUT,  "scada_telemetry_15min_dirty.csv")

    chunk_size = 250_000
    first = True

    reader = pd.read_csv(src, chunksize=chunk_size)
    total_nulls = total_dupes = total_stale = total_range = total_freq = total_fault = 0

    for chunk in reader:
        n = len(chunk)

        # ── 1a. Null ActivePowerMW (sensor dropout: comm loss, inverter fault)
        null_idx = pct_idx(chunk, 1.4)
        chunk.loc[null_idx, "ActivePowerMW"] = np.nan
        total_nulls += len(null_idx)

        # ── 1b. Null SolarIrradianceWm2 for solar rows (pyranometer offline)
        solar_mask = chunk["Technology"].str.contains("Solar", na=False)
        solar_null = chunk[solar_mask].sample(frac=0.008, random_state=SEED).index
        chunk.loc[solar_null, "SolarIrradianceWm2"] = np.nan
        total_nulls += len(solar_null)

        # ── 1c. Transformer temp fault code (PT100 sensor: open circuit = 999.9)
        fault_idx = pct_idx(chunk, 0.15)
        chunk.loc[fault_idx, "TransformerTempC"] = 999.9
        total_fault += len(fault_idx)

        # ── 1d. Out-of-range ActivePowerMW (inverter miscalibration, negative clamp)
        range_idx = pct_idx(chunk, 0.18)
        # Half negative, half insanely high
        half = len(range_idx) // 2
        chunk.loc[range_idx[:half], "ActivePowerMW"] = (
            np.random.uniform(-15, -0.5, half)
        )
        # Use .loc with the second half indices separately to avoid ambiguity
        second_half = range_idx[half:]
        caps = chunk.loc[second_half, "Technology"].map(
            lambda t: 713 if "Gas" in str(t) else 150
        )
        chunk.loc[second_half, "ActivePowerMW"] = (
            caps.values * np.random.uniform(1.05, 1.25, len(second_half))
        )
        total_range += len(range_idx)

        # ── 1e. Grid frequency spikes (load shedding / islanding event)
        freq_idx = pct_idx(chunk, 0.12)
        chunk.loc[freq_idx, "GridFrequencyHz"] = (
            np.random.choice([47.2, 47.8, 52.3, 52.8, 53.1],
                             size=len(freq_idx))
        )
        total_freq += len(freq_idx)

        # ── 1f. Stale readings (frozen sensor: same value block of 4-12 intervals)
        stale_starts = pct_idx(chunk, 0.08)
        for si in stale_starts[:50]:   # cap iterations per chunk
            block = min(np.random.randint(4, 13), n - si - 1)
            if block > 0:
                frozen_val = chunk.at[si, "ActivePowerMW"]
                chunk.loc[si:si+block, "ActivePowerMW"]    = frozen_val
                chunk.loc[si:si+block, "DataQualityFlag"]  = "STALE"
                chunk.loc[si:si+block, "AlarmCode"]        = "SENSOR_FROZEN"
        total_stale += len(stale_starts)

        # ── 1g. Mixed timestamp format (some rows DD/MM/YYYY HH:MM instead of ISO)
        ts_idx = pct_idx(chunk, 0.05)
        chunk.loc[ts_idx, "Timestamp"] = pd.to_datetime(
            chunk.loc[ts_idx, "Timestamp"]
        ).dt.strftime("%d/%m/%Y %H:%M")   # wrong format

        # ── 1h. Duplicate rows (control system double-send on reconnect)
        dup_idx = pct_idx(chunk, 0.30)
        dupes = chunk.loc[dup_idx].copy()
        chunk = pd.concat([chunk, dupes], ignore_index=True)
        total_dupes += len(dup_idx)

        chunk.to_csv(dst, mode="a" if not first else "w",
                     header=first, index=False)
        first = False

    log_issue("scada_telemetry", "ActivePowerMW",       "null_sensor_dropout",   total_nulls)
    log_issue("scada_telemetry", "SolarIrradianceWm2",  "null_pyranometer",       0)  # included in nulls
    log_issue("scada_telemetry", "TransformerTempC",    "fault_code_999.9",       total_fault)
    log_issue("scada_telemetry", "ActivePowerMW",       "out_of_range_power",     total_range)
    log_issue("scada_telemetry", "GridFrequencyHz",     "frequency_spike",        total_freq)
    log_issue("scada_telemetry", "ActivePowerMW",       "stale_frozen_sensor",    total_stale)
    log_issue("scada_telemetry", "Timestamp",           "mixed_date_format",      0)
    log_issue("scada_telemetry", "*",                   "duplicate_row",          total_dupes)

    size_mb = os.path.getsize(dst) / 1e6
    print(f"   → Written {dst}  ({size_mb:.0f} MB)")


# ══════════════════════════════════════════════════════════════
# 2. DAILY OPERATIONS
# ══════════════════════════════════════════════════════════════
def dirty_daily_ops():
    print("\n[2/6] Injecting dirt into daily operations…")
    df = pd.read_csv(os.path.join(SRC, "fact_plant_operations_daily_5yr.csv"))
    n = len(df)

    # 2a. Availability > 100% (meter overcounting, ERP rounding)
    idx_avail = pct_idx(df, 0.4)
    df.loc[idx_avail, "AvailabilityPct"] = np.random.uniform(100.1, 105.0, len(idx_avail))
    log_issue("daily_ops", "AvailabilityPct", "availability_over_100pct", len(idx_avail))

    # 2b. NetGenerationMWh > GrossGenerationMWh (physical impossibility — data entry)
    idx_netgross = pct_idx(df, 0.3)
    df.loc[idx_netgross, "NetGenerationMWh"] = (
        df.loc[idx_netgross, "GrossGenerationMWh"] * np.random.uniform(1.01, 1.08, len(idx_netgross))
    )
    log_issue("daily_ops", "NetGenerationMWh", "net_exceeds_gross", len(idx_netgross))

    # 2c. Null CapacityFactorPct (meter read missed, data logger offline)
    idx_null_cf = pct_idx(df, 0.9)
    df.loc[idx_null_cf, "CapacityFactorPct"] = np.nan
    log_issue("daily_ops", "CapacityFactorPct", "null_missing_meter_read", len(idx_null_cf))

    # 2d. Negative EnergyExportedMWh (grid reversal / meter polarity)
    idx_neg = pct_idx(df, 0.15)
    df.loc[idx_neg, "EnergyExportedMWh"] = (
        -1 * np.random.uniform(0.1, 5.0, len(idx_neg))
    )
    log_issue("daily_ops", "EnergyExportedMWh", "negative_export_polarity", len(idx_neg))

    # 2e. Duplicate DateKey + PlantKey (double-push from SCADA historian)
    idx_dup = pct_idx(df, 0.2)
    df = pd.concat([df, df.loc[idx_dup]], ignore_index=True)
    log_issue("daily_ops", "DateKey+PlantKey", "duplicate_row", len(idx_dup))

    # 2f. CurtailmentPct > 100 (impossible — SCADA calculation bug)
    idx_curt = pct_idx(df, 0.08)
    df.loc[idx_curt, "CurtailmentPct"] = np.random.uniform(101, 150, len(idx_curt))
    log_issue("daily_ops", "CurtailmentPct", "curtailment_over_100pct", len(idx_curt))

    # 2g. Null DateKey (ETL NULL propagation from upstream)
    idx_nulldk = pct_idx(df, 0.05)
    df.loc[idx_nulldk, "DateKey"] = np.nan
    log_issue("daily_ops", "DateKey", "null_date_key", len(idx_nulldk))

    df.to_csv(os.path.join(OUT, "fact_plant_operations_daily_dirty.csv"), index=False)
    print(f"   → {len(df):,} rows (incl. dupes)")


# ══════════════════════════════════════════════════════════════
# 3. MAINTENANCE WORK ORDERS
# ══════════════════════════════════════════════════════════════
def dirty_maintenance():
    print("\n[3/6] Injecting dirt into maintenance work orders…")
    df = pd.read_csv(os.path.join(SRC, "fact_maintenance_work_order_5yr.csv"))
    df["OpenedDate"]    = pd.to_datetime(df["OpenedDate"])
    df["TargetCloseDate"] = pd.to_datetime(df["TargetCloseDate"])

    # 3a. ClosedDate before OpenedDate (date entry error: day/month transposition)
    closed_rows = df[df["ClosedDate"].notna() & (df["ClosedDate"] != "")].copy()
    idx_swap = closed_rows.sample(frac=0.04, random_state=SEED).index
    df.loc[idx_swap, "ClosedDate"] = (
        df.loc[idx_swap, "OpenedDate"] - pd.to_timedelta(
            np.random.randint(1, 30, len(idx_swap)), unit="D"
        )
    ).dt.strftime("%Y-%m-%d")
    log_issue("maintenance_wo", "ClosedDate", "close_before_open_date", len(idx_swap))

    # 3b. Zero TotalMaintenanceCostZAR (finance system sync failure)
    idx_zero = pct_idx(df, 5.0)
    df.loc[idx_zero, "TotalMaintenanceCostZAR"] = 0.0
    log_issue("maintenance_wo", "TotalMaintenanceCostZAR", "zero_cost_sync_failure", len(idx_zero))

    # 3c. Status = "Closed" but ClosedDate is null/blank (ERP workflow skip)
    closed_status = df[df["WorkOrderStatus"] == "Closed"].sample(frac=0.03, random_state=SEED).index
    df.loc[closed_status, "ClosedDate"] = ""
    log_issue("maintenance_wo", "ClosedDate", "closed_status_null_date", len(closed_status))

    # 3d. Corrupt priority value (free-text entry instead of picklist)
    bad_priority = ["urgent", "CRIT", "med", "3", "N/A", "TBD", "High Risk"]
    idx_pri = pct_idx(df, 1.5)
    df.loc[idx_pri, "Priority"] = np.random.choice(bad_priority, len(idx_pri))
    log_issue("maintenance_wo", "Priority", "corrupt_priority_free_text", len(idx_pri))

    # 3e. Negative ActualLabourHours (sign error in time sheet integration)
    idx_neg_hrs = pct_idx(df, 0.8)
    df.loc[idx_neg_hrs, "ActualLabourHours"] = (
        -1 * df.loc[idx_neg_hrs, "ActualLabourHours"].abs()
    )
    log_issue("maintenance_wo", "ActualLabourHours", "negative_labour_hours", len(idx_neg_hrs))

    # 3f. WorkOrderID duplicates (ERP import ran twice)
    idx_dup = pct_idx(df, 0.6)
    df = pd.concat([df, df.loc[idx_dup]], ignore_index=True)
    log_issue("maintenance_wo", "WorkOrderID", "duplicate_work_order", len(idx_dup))

    df.to_csv(os.path.join(OUT, "fact_maintenance_work_order_dirty.csv"), index=False)
    print(f"   → {len(df):,} rows (incl. dupes)")


# ══════════════════════════════════════════════════════════════
# 4. ENERGY SALES MONTHLY
# ══════════════════════════════════════════════════════════════
def dirty_energy_sales():
    print("\n[4/6] Injecting dirt into energy sales…")
    df = pd.read_csv(os.path.join(SRC, "fact_energy_sales_monthly_5yr.csv"))

    # 4a. RevenueZAR off by ×1000 (ZAR vs kZAR confusion in upstream system)
    idx_mag = pct_idx(df, 2.0)
    df.loc[idx_mag, "RevenueZAR"]          *= 1000
    df.loc[idx_mag, "CollectedRevenueZAR"] *= 1000
    log_issue("energy_sales", "RevenueZAR", "magnitude_error_x1000", len(idx_mag))

    # 4b. SettlementCollectionPct > 1.0 (overpayment / correction credit)
    idx_over = pct_idx(df, 1.2)
    df.loc[idx_over, "SettlementCollectionPct"] = np.random.uniform(1.01, 1.12, len(idx_over))
    log_issue("energy_sales", "SettlementCollectionPct", "collection_over_100pct", len(idx_over))

    # 4c. Negative EnergySoldMWh (meter reversal / credit note)
    idx_neg = pct_idx(df, 0.4)
    df.loc[idx_neg, "EnergySoldMWh"] = -1 * np.random.uniform(10, 500, len(idx_neg))
    log_issue("energy_sales", "EnergySoldMWh", "negative_energy_sold", len(idx_neg))

    # 4d. Duplicate YearMonth + PlantKey (double-billing)
    idx_dup = pct_idx(df, 1.0)
    df = pd.concat([df, df.loc[idx_dup]], ignore_index=True)
    log_issue("energy_sales", "YearMonth+PlantKey", "duplicate_billing_row", len(idx_dup))

    # 4e. Null YearMonth (ETL mapping failure on new plant go-live)
    idx_null_ym = pct_idx(df, 0.3)
    df.loc[idx_null_ym, "YearMonth"] = np.nan
    log_issue("energy_sales", "YearMonth", "null_year_month", len(idx_null_ym))

    df.to_csv(os.path.join(OUT, "fact_energy_sales_monthly_dirty.csv"), index=False)
    print(f"   → {len(df):,} rows (incl. dupes)")


# ══════════════════════════════════════════════════════════════
# 5. OUTAGES
# ══════════════════════════════════════════════════════════════
def dirty_outages():
    print("\n[5/6] Injecting dirt into outages…")
    df = pd.read_csv(os.path.join(SRC, "fact_outage_5yr.csv"))
    df["StartDateTime"] = pd.to_datetime(df["StartDateTime"])
    df["EndDateTime"]   = pd.to_datetime(df["EndDateTime"])

    # 5a. EndDateTime before StartDateTime (ctrl+C ctrl+V error in log sheet)
    idx_flip = pct_idx(df, 3.0)
    df.loc[idx_flip, ["StartDateTime","EndDateTime"]] = (
        df.loc[idx_flip, ["EndDateTime","StartDateTime"]].values
    )
    log_issue("outages", "EndDateTime", "end_before_start_datetime", len(idx_flip))

    # 5b. DurationHours = 0 (auto-close bug in CMMS)
    idx_zero = pct_idx(df, 2.5)
    df.loc[idx_zero, "DurationHours"] = 0.0
    log_issue("outages", "DurationHours", "zero_duration_outage", len(idx_zero))

    # 5c. Null Cause (technician skipped mandatory field)
    idx_null_cause = pct_idx(df, 8.0)
    df.loc[idx_null_cause, "Cause"] = np.nan
    log_issue("outages", "Cause", "null_cause_field", len(idx_null_cause))

    # 5d. EstimatedEnergyLostMWh negative (sign convention mismatch)
    idx_neg = pct_idx(df, 1.5)
    df.loc[idx_neg, "EstimatedEnergyLostMWh"] = (
        -1 * df.loc[idx_neg, "EstimatedEnergyLostMWh"].abs()
    )
    log_issue("outages", "EstimatedEnergyLostMWh", "negative_energy_lost", len(idx_neg))

    # 5e. OutageType = null (free-text entry before picklist enforced)
    idx_null_type = pct_idx(df, 2.0)
    df.loc[idx_null_type, "OutageType"] = np.nan
    log_issue("outages", "OutageType", "null_outage_type", len(idx_null_type))

    df.to_csv(os.path.join(OUT, "fact_outage_dirty.csv"), index=False)
    print(f"   → {len(df):,} rows")


# ══════════════════════════════════════════════════════════════
# 6. HSE INCIDENTS
# ══════════════════════════════════════════════════════════════
def dirty_hse():
    print("\n[6/6] Injecting dirt into HSE incidents…")
    df = pd.read_csv(os.path.join(SRC, "fact_hse_incident_5yr.csv"))
    df["IncidentDate"] = pd.to_datetime(df["IncidentDate"])

    # 6a. Future dates (data entry error — year typed as 2026/2027)
    idx_future = pct_idx(df, 2.0)
    df.loc[idx_future, "IncidentDate"] = (
        datetime(2026, 6, 25) + pd.to_timedelta(
            np.random.randint(1, 400, len(idx_future)), unit="D"
        )
    )
    log_issue("hse", "IncidentDate", "future_incident_date", len(idx_future))

    # 6b. LostWorkDays = null for LTI incidents (mandatory field missed)
    lti = df[df["IncidentType"] == "Lost Time Injury"].sample(frac=0.15, random_state=SEED).index
    df.loc[lti, "LostWorkDays"] = np.nan
    log_issue("hse", "LostWorkDays", "null_lti_lost_work_days", len(lti))

    # 6c. Null Severity (triage incomplete)
    idx_null_sev = pct_idx(df, 4.0)
    df.loc[idx_null_sev, "Severity"] = np.nan
    log_issue("hse", "Severity", "null_severity_triage", len(idx_null_sev))

    # 6d. Corrupt IncidentType (free-text before enforced picklist)
    bad_types = ["fall", "near miss", "INJURY", "property dmg", "fire/explosion"]
    idx_bad = pct_idx(df, 3.0)
    df.loc[idx_bad, "IncidentType"] = np.random.choice(bad_types, len(idx_bad))
    log_issue("hse", "IncidentType", "corrupt_incident_type_free_text", len(idx_bad))

    df.to_csv(os.path.join(OUT, "fact_hse_incident_dirty.csv"), index=False)
    print(f"   → {len(df):,} rows")


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import time
    t0 = time.time()
    print("=" * 60)
    print("BAOBAB POWER — DIRTY DATA INJECTOR")
    print("Injecting realistic data quality issues into all tables")
    print("=" * 60)

    dirty_scada()
    dirty_daily_ops()
    dirty_maintenance()
    dirty_energy_sales()
    dirty_outages()
    dirty_hse()

    # Write manifest
    mdf = pd.DataFrame(manifest)
    mdf.to_csv(os.path.join(OUT, "dirty_manifest.csv"), index=False)

    total_issues = mdf["rows_affected"].sum()
    print("\n" + "=" * 60)
    print("DIRTY DATA INJECTION COMPLETE")
    print("=" * 60)
    print(f"\n  Tables dirtied  : {mdf['table'].nunique()}")
    print(f"  Patterns applied: {len(mdf)}")
    print(f"  Total rows dirty: {total_issues:,}")
    print(f"\n  Dirty patterns summary:")
    for _, row in mdf.iterrows():
        print(f"    {row['table']:<20} | {row['dirty_pattern']:<38} | {row['rows_affected']:>7,}")
    print(f"\n  Manifest → {os.path.join(OUT, 'dirty_manifest.csv')}")
    print(f"  Output   → {OUT}")
    print(f"  Time     : {time.time()-t0:.1f}s")
    print("=" * 60)
