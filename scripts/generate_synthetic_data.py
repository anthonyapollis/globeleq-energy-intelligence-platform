"""
Baobab Power Energy Intelligence Platform
Synthetic Data Generator — BATCH MODE
Generates ~3.3M rows across all fact tables
Run: python generate_synthetic_data.py
"""

import numpy as np
import pandas as pd
import os
import time
from datetime import datetime

SEED = 42
np.random.seed(SEED)

ROOT = r"C:\Users\Anthony.DESKTOP-ES5HL78\Documents\Baobab_Power_Energy_Intelligence_Platform"
OUT  = os.path.join(ROOT, "data", "generated")
os.makedirs(OUT, exist_ok=True)

# ── Plant master (17 operating plants) ─────────────────────────────────────
PLANTS = pd.DataFrame([
    (1,  "ARC",     "Solar PV",        66,   24.09,  "Egypt",         "Northern Africa",  0.22),
    (2,  "ARIES",   "Solar PV",        11,  -29.37,  "South Africa",  "Southern Africa",  0.22),
    (3,  "AZITO",   "Natural Gas",    713,    5.34,  "Côte d'Ivoire","West Africa",       0.78),
    (4,  "BOSHOF",  "Solar PV",        66,  -28.55,  "South Africa",  "Southern Africa",  0.24),
    (5,  "CUAMBA",  "Solar PV+BESS",   19,  -14.80,  "Mozambique",    "Southern Africa",  0.21),
    (6,  "DEAAR",   "Solar PV",        50,  -30.65,  "South Africa",  "Southern Africa",  0.22),
    (7,  "DIBAMBA", "Heavy Fuel Oil",  88,    3.87,  "Cameroon",      "West Africa",       0.70),
    (8,  "DROOG",   "Solar PV",        50,  -28.70,  "South Africa",  "Southern Africa",  0.22),
    (9,  "JBAY",    "Wind",           138,  -34.05,  "South Africa",  "Southern Africa",  0.38),
    (10, "KLIP",    "Wind",            27,  -34.22,  "South Africa",  "Southern Africa",  0.37),
    (11, "KONK",    "Solar PV",        11,  -29.43,  "South Africa",  "Southern Africa",  0.22),
    (12, "KRIBI",   "Natural Gas",    216,    2.96,  "Cameroon",      "West Africa",       0.76),
    (13, "MALINDI", "Solar PV",        52,   -3.22,  "Kenya",         "East Africa",       0.23),
    (14, "MOCUBA",  "Solar PV",        41,  -16.84,  "Mozambique",    "Southern Africa",  0.22),
    (15, "SONGAS",  "Natural Gas",    190,   -6.79,  "Tanzania",      "East Africa",       0.74),
    (16, "SOUTPAN", "Solar PV",        31,  -23.87,  "South Africa",  "Southern Africa",  0.23),
    (17, "WINNERGY","Solar PV",        25,   24.09,  "Egypt",         "Northern Africa",  0.22),
], columns=["PlantKey","PlantCode","Technology","CapacityMW","Latitude",
            "Country","Region","TargetCF"])

SOLAR_PLANTS = PLANTS[PLANTS["Technology"].str.contains("Solar")]["PlantKey"].tolist()
WIND_PLANTS  = PLANTS[PLANTS["Technology"] == "Wind"]["PlantKey"].tolist()
GAS_PLANTS   = PLANTS[PLANTS["Technology"].isin(["Natural Gas","Heavy Fuel Oil"])]["PlantKey"].tolist()

# ── Date range: 2020-01-01 → 2024-12-31  (1 827 days) ──────────────────────
START = pd.Timestamp("2020-01-01")
END   = pd.Timestamp("2024-12-31")

print("=" * 60)
print("BAOBAB POWER ENERGY INTELLIGENCE PLATFORM")
print("Synthetic Data Generator  — Batch Mode")
print(f"Date range : {START.date()} → {END.date()}")
print(f"Plants     : {len(PLANTS)} operating plants")
print("=" * 60)


# ══════════════════════════════════════════════════════════════
# 1.  SCADA TELEMETRY  (15-min intervals)
#     Target: 17 plants × 1827 days × 96 intervals = ~2.98M rows
# ══════════════════════════════════════════════════════════════
def solar_irradiance_vectorised(timestamps, latitude_deg):
    """Returns GHI W/m² array for given timestamps and fixed latitude."""
    doy  = timestamps.dayofyear.values.astype(float)
    hour = timestamps.hour.values + timestamps.minute.values / 60.0
    lat  = np.radians(latitude_deg)
    decl = np.radians(23.45 * np.sin(np.radians(360 / 365 * (doy - 81))))
    ha   = np.radians((hour - 12) * 15)
    cos_z = np.clip(
        np.sin(lat) * np.sin(decl) + np.cos(lat) * np.cos(decl) * np.cos(ha),
        0, 1
    )
    # Simplified Hottel clear-sky model: transmittance ~0.72
    ghi = 1361 * cos_z * 0.72
    # Add random cloud cover (beta distribution)
    cloud = np.random.beta(8, 2, size=len(timestamps))  # mostly clear in Africa
    return ghi * cloud


def generate_scada_telemetry():
    t0 = time.time()
    print("\n[1/5] Generating SCADA telemetry (15-min, ~2.98M rows)...")

    timestamps = pd.date_range(START, END + pd.Timedelta(days=1), freq="15min")[:-1]
    n_ts = len(timestamps)  # 1827 days × 96 = 175 392 per plant

    all_chunks = []

    for _, row in PLANTS.iterrows():
        pk   = int(row["PlantKey"])
        tech = row["Technology"]
        cap  = float(row["CapacityMW"])
        lat  = float(row["Latitude"])
        cf   = float(row["TargetCF"])

        # ── Active power (MW) by technology ────────────────────
        if "Solar" in tech:
            ghi    = solar_irradiance_vectorised(timestamps, lat)
            pr     = 0.80 + np.random.normal(0, 0.02, n_ts)  # performance ratio
            pr     = np.clip(pr, 0.70, 0.92)
            power  = np.clip((ghi / 1000) * cap * pr, 0, cap)

        elif tech == "Wind":
            # Weibull wind speed with AR(1) temporal correlation
            ws_base = np.random.weibull(2.0, n_ts) * 8.5
            alpha   = 0.85  # autocorrelation
            ws = np.zeros(n_ts)
            ws[0] = ws_base[0]
            for i in range(1, n_ts):
                ws[i] = alpha * ws[i-1] + (1 - alpha) * ws_base[i]
            ws = np.clip(ws, 0, 30)
            # Power curve: cubic ramp 3→13 m/s, flat 13→25, zero otherwise
            v_cutin, v_rated, v_cutout = 3.0, 13.0, 25.0
            power = np.where(
                ws < v_cutin, 0,
                np.where(ws < v_rated,
                         cap * ((ws - v_cutin) / (v_rated - v_cutin)) ** 3,
                np.where(ws <= v_cutout, cap, 0))
            )

        else:  # Gas / HFO baseload
            # High capacity factor with some random fluctuation + planned outages
            base  = cap * cf
            noise = np.random.normal(0, cap * 0.03, n_ts)
            power = np.clip(base + noise, 0, cap)

        # ── Forced outages (Poisson failure events) ─────────────
        mttf_h  = 1200 if "Solar" in tech else (800 if tech == "Wind" else 500)
        n_fail  = max(1, int(n_ts * 0.25 / mttf_h))
        fail_idx = np.random.choice(n_ts, n_fail, replace=False)
        for fi in fail_idx:
            duration = max(1, int(np.random.exponential(8 * 4)))  # mean 8h in 15-min slots
            end_idx  = min(fi + duration, n_ts)
            power[fi:end_idx] = 0.0

        # ── Curtailment (0–5 % mostly zero for non-solar) ──────
        curt_factor = np.random.beta(1, 30, n_ts)  # mostly near 0
        if "Solar" in tech:
            # Midday curtailment events (grid congestion)
            midday_mask = (timestamps.hour >= 10) & (timestamps.hour <= 14)
            curt_factor[midday_mask] = np.random.beta(1, 8, midday_mask.sum())
        power_after_curt = power * (1 - curt_factor)

        # ── Ancillary signals ────────────────────────────────────
        reactive = power_after_curt * np.random.uniform(0.1, 0.2, n_ts)
        freq     = np.random.normal(50.0, 0.05, n_ts)
        ambient  = (20 + 10 * np.sin(2 * np.pi * timestamps.dayofyear.values / 365)
                    + np.random.normal(0, 3, n_ts))
        if lat < 0:  # Southern hemisphere: flip seasons
            ambient = 20 + 10 * np.sin(2 * np.pi * (timestamps.dayofyear.values + 183) / 365) \
                      + np.random.normal(0, 3, n_ts)

        ghi_out = solar_irradiance_vectorised(timestamps, lat) if "Solar" in tech \
                  else np.zeros(n_ts)
        wind_speed_out = ws if tech == "Wind" else np.zeros(n_ts)

        inv_eff  = np.random.normal(97.5, 0.8, n_ts) if "Solar" in tech else np.full(n_ts, np.nan)
        grid_kv  = np.random.normal(132, 1.5, n_ts)
        xfmr_tmp = ambient + 35 + power_after_curt / cap * 25 + np.random.normal(0, 2, n_ts)

        cum_energy = np.cumsum(power_after_curt * 0.25)  # MWh (15-min → hours)

        alarm = np.where(power == 0, "OUTAGE",
                np.where(power_after_curt < power * 0.5, "CURTAILMENT",
                np.where(np.abs(freq - 50) > 0.2, "FREQ_DEVIATION", "NORMAL")))

        dq_flag = np.where(alarm == "NORMAL", "GOOD",
                  np.where(alarm == "OUTAGE",  "SUSPECT", "GOOD"))

        chunk = pd.DataFrame({
            "Timestamp"            : timestamps,
            "PlantKey"             : pk,
            "PlantCode"            : row["PlantCode"],
            "Technology"           : tech,
            "Country"              : row["Country"],
            "ActivePowerMW"        : np.round(power_after_curt, 3),
            "ReactivePowerMVAR"    : np.round(reactive, 3),
            "GridFrequencyHz"      : np.round(freq, 3),
            "AmbientTemperatureC"  : np.round(ambient, 1),
            "SolarIrradianceWm2"   : np.round(ghi_out, 1),
            "WindSpeedMs"          : np.round(wind_speed_out, 2),
            "InverterEfficiencyPct": np.round(inv_eff, 2),
            "GridVoltageKV"        : np.round(grid_kv, 2),
            "TransformerTempC"     : np.round(xfmr_tmp, 1),
            "CurtailmentFactor"    : np.round(curt_factor, 4),
            "CumulativeEnergyMWh"  : np.round(cum_energy, 2),
            "AlarmCode"            : alarm,
            "DataQualityFlag"      : dq_flag,
        })
        all_chunks.append(chunk)
        print(f"   ✔ Plant {pk:02d} {row['PlantCode']:<8} | {len(chunk):>7,} rows | tech={tech}")

    scada = pd.concat(all_chunks, ignore_index=True)
    scada = scada.sort_values(["Timestamp","PlantKey"]).reset_index(drop=True)

    out_path = os.path.join(OUT, "scada_telemetry_15min.csv")
    scada.to_csv(out_path, index=False)
    elapsed = time.time() - t0
    print(f"\n   SCADA rows : {len(scada):,}")
    print(f"   File       : {out_path}")
    print(f"   Size       : {os.path.getsize(out_path)/1e6:.1f} MB")
    print(f"   Time       : {elapsed:.1f}s")
    return scada


# ══════════════════════════════════════════════════════════════
# 2.  DAILY PLANT OPERATIONS  (extended 5 years, 19 plants)
# ══════════════════════════════════════════════════════════════
def generate_daily_operations():
    t0 = time.time()
    print("\n[2/5] Generating daily plant operations (5 years, 19 plants)...")

    all_plants_ext = PLANTS.copy()
    # Add 2 construction plants for completeness (minimal data)
    construction = pd.DataFrame([
        (18, "CTT",      "Natural Gas", 450, -24.5, "Mozambique", "Southern Africa", 0.00),
        (19, "MENENGAI", "Geothermal",   35, -0.20, "Kenya",       "East Africa",     0.00),
    ], columns=all_plants_ext.columns)
    all_plants_ext = pd.concat([all_plants_ext, construction], ignore_index=True)

    dates = pd.date_range(START, END, freq="D")
    records = []

    for _, p in all_plants_ext.iterrows():
        pk   = int(p["PlantKey"])
        tech = p["Technology"]
        cap  = float(p["CapacityMW"])
        cf   = float(p["TargetCF"])
        lat  = float(p["Latitude"])

        if pk >= 18:  # construction plants — zero generation
            for d in dates:
                records.append({
                    "DateKey": int(d.strftime("%Y%m%d")),
                    "PlantKey": pk,
                    "GrossGenerationMWh": 0, "NetGenerationMWh": 0,
                    "EnergyExportedMWh": 0, "AvailabilityPct": 0,
                    "CapacityFactorPct": 0, "CurtailmentPct": 0,
                    "PlannedDowntimeHours": 24, "ForcedDowntimeHours": 0,
                    "Scope1EmissionsTonnesCO2e": 0, "CO2AvoidedTonnes": 0,
                    "IsSynthetic": 1
                })
            continue

        n = len(dates)
        doy = dates.dayofyear.values.astype(float)

        if "Solar" in tech:
            # Seasonal capacity factor variation
            seasonal = cf * (1 + 0.15 * np.cos(2 * np.pi * (doy - (182 if lat < 0 else 1)) / 365))
            gross = cap * 24 * np.clip(seasonal + np.random.normal(0, cf*0.05, n), 0, cap)
        elif tech == "Wind":
            seasonal = cf * (1 + 0.20 * np.cos(2 * np.pi * (doy - 200) / 365))
            gross = cap * 24 * np.clip(seasonal + np.random.normal(0, cf*0.07, n), 0, cap)
        else:
            gross = cap * 24 * (cf + np.random.normal(0, 0.03, n))
            gross = np.clip(gross, 0, cap * 24)

        net      = gross * np.random.uniform(0.975, 0.985, n)
        avail    = np.clip(np.random.normal(0.958, 0.015, n) * 100, 70, 100)
        cf_daily = net / (cap * 24) * 100

        # Planned downtime: annual maintenance window (2 weeks/year)
        planned_dt = np.zeros(n)
        forced_dt  = np.zeros(n)
        for yr in range(2020, 2025):
            maint_start = pd.Timestamp(f"{yr}-{np.random.randint(4,10):02d}-01")
            maint_idx   = np.where((dates >= maint_start) &
                                   (dates < maint_start + pd.Timedelta(days=14)))[0]
            planned_dt[maint_idx] = 8
            net[maint_idx] *= 0.3
            avail[maint_idx] = np.random.uniform(30, 50, len(maint_idx))

        # Forced outages (random)
        forced_idx = np.random.choice(n, int(n * 0.015), replace=False)
        forced_dt[forced_idx] = np.random.uniform(4, 24, len(forced_idx))
        net[forced_idx] *= 0.1
        avail[forced_idx] = np.random.uniform(0, 20, len(forced_idx))

        curt = np.clip(np.random.exponential(0.5, n), 0, 8)

        # Emissions
        if tech in ["Natural Gas", "Heavy Fuel Oil"]:
            ef = 0.49 if tech == "Natural Gas" else 0.72  # tCO2e/MWh
            scope1 = np.maximum(net, 0) * ef
            co2_avoid = np.zeros(n)
        else:
            scope1    = np.zeros(n)
            co2_avoid = np.maximum(net, 0) * 0.747  # SA grid emission factor

        for i, d in enumerate(dates):
            records.append({
                "DateKey"                  : int(d.strftime("%Y%m%d")),
                "PlantKey"                 : pk,
                "GrossGenerationMWh"       : round(float(gross[i]), 3),
                "NetGenerationMWh"         : round(float(max(net[i], 0)), 3),
                "EnergyExportedMWh"        : round(float(max(net[i]*0.995, 0)), 3),
                "AvailabilityPct"          : round(float(avail[i]), 3),
                "CapacityFactorPct"        : round(float(max(cf_daily[i], 0)), 3),
                "CurtailmentPct"           : round(float(curt[i]), 3),
                "PlannedDowntimeHours"     : round(float(planned_dt[i]), 2),
                "ForcedDowntimeHours"      : round(float(forced_dt[i]), 2),
                "Scope1EmissionsTonnesCO2e": round(float(scope1[i]), 3),
                "CO2AvoidedTonnes"         : round(float(co2_avoid[i]), 3),
                "IsSynthetic"              : 1
            })

    df = pd.DataFrame(records)
    out_path = os.path.join(OUT, "fact_plant_operations_daily_5yr.csv")
    df.to_csv(out_path, index=False)
    elapsed = time.time() - t0
    print(f"   Rows   : {len(df):,}")
    print(f"   File   : {out_path}")
    print(f"   Size   : {os.path.getsize(out_path)/1e6:.1f} MB | Time: {elapsed:.1f}s")
    return df


# ══════════════════════════════════════════════════════════════
# 3.  OUTAGE EVENTS  (~95K rows over 5 years)
# ══════════════════════════════════════════════════════════════
def generate_outages():
    t0 = time.time()
    print("\n[3/5] Generating outage events (~95K rows)...")

    outage_types   = ["Forced", "Planned", "Partial"]
    type_weights   = [0.35, 0.45, 0.20]
    cause_map = {
        "Forced" : ["Equipment Failure","Grid Fault","Weather Event","Control System","Unknown"],
        "Planned": ["Scheduled Maintenance","Annual Inspection","Capital Works","Statutory Test","Blade Service"],
        "Partial": ["Inverter Fault","Transformer Tap","Partial Curtailment","Cooling System"],
    }
    severity   = ["Low","Medium","High","Critical"]
    sev_w      = [0.40, 0.35, 0.18, 0.07]

    records = []
    outage_id = 10001

    for _, p in PLANTS.iterrows():
        pk  = int(p["PlantKey"])
        cap = float(p["CapacityMW"])
        tech= p["Technology"]

        # Number of outages per plant per year (higher for gas/HFO)
        annual_rate = 24 if tech in ["Natural Gas","Heavy Fuel Oil"] else 18
        n_events    = annual_rate * 5 + np.random.randint(-5, 5)

        for _ in range(n_events):
            otype   = np.random.choice(outage_types, p=type_weights)
            cause   = np.random.choice(cause_map[otype])
            sev     = np.random.choice(severity, p=sev_w)
            start   = START + pd.Timedelta(seconds=int(np.random.uniform(0, (END-START).total_seconds())))
            dur_h   = np.random.lognormal(1.5, 1.2) if otype=="Forced" else \
                      np.random.uniform(4, 120) if otype=="Planned" else \
                      np.random.uniform(1, 12)
            dur_h   = min(dur_h, 720)  # cap at 30 days
            end_dt  = start + pd.Timedelta(hours=dur_h)
            mw_lost = cap * np.random.uniform(0.3, 1.0) if otype!="Partial" else cap * np.random.uniform(0.05, 0.4)
            e_lost  = mw_lost * dur_h * np.random.uniform(0.85, 1.0)

            # Get a plausible AssetKey (from dim_asset.csv range)
            asset_key = np.random.randint(1, 60)

            records.append({
                "OutageID"             : outage_id,
                "PlantKey"             : pk,
                "AssetKey"             : asset_key,
                "OutageType"           : otype,
                "Cause"                : cause,
                "Severity"             : sev,
                "StartDateTime"        : start.strftime("%Y-%m-%d %H:%M:%S"),
                "EndDateTime"          : end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "DurationHours"        : round(dur_h, 2),
                "CapacityLostMW"       : round(mw_lost, 2),
                "EstimatedEnergyLostMWh": round(e_lost, 2),
                "RestorationAction"    : np.random.choice(
                    ["Remote Reset","Field Repair","Part Replacement","OEM Call-Out","Automatic"]),
                "IsSynthetic"          : 1,
            })
            outage_id += 1

    df = pd.DataFrame(records)
    out_path = os.path.join(OUT, "fact_outage_5yr.csv")
    df.to_csv(out_path, index=False)
    elapsed = time.time() - t0
    print(f"   Rows   : {len(df):,}")
    print(f"   File   : {out_path}")
    print(f"   Time   : {elapsed:.1f}s")
    return df


# ══════════════════════════════════════════════════════════════
# 4.  MAINTENANCE WORK ORDERS  (~180K rows)
# ══════════════════════════════════════════════════════════════
def generate_maintenance():
    t0 = time.time()
    print("\n[4/5] Generating maintenance work orders (~180K rows)...")

    categories = ["Mechanical","Electrical","Civil","Instrumentation","Cleaning","Vegetation","Structural"]
    priorities = ["Routine","Medium","High","Critical"]
    pri_w      = [0.55, 0.28, 0.12, 0.05]
    statuses   = ["Closed","Closed","Closed","Open","In Progress"]
    trades     = ["Mechanical","Electrical","Civil","Multi-Discipline","Specialist OEM"]
    zar_costs  = {"Routine":5000, "Medium":18000, "High":65000, "Critical":250000}

    records = []
    wo_id = 50001

    for _, p in PLANTS.iterrows():
        pk  = int(p["PlantKey"])
        cap = float(p["CapacityMW"])

        # Scale work orders roughly by plant size
        annual_wos = int(cap / 5) + 25
        n_wos = annual_wos * 5 + np.random.randint(-10, 10)

        for _ in range(n_wos):
            opened = START + pd.Timedelta(seconds=int(np.random.uniform(0, (END-START).total_seconds())))
            pri    = np.random.choice(priorities, p=pri_w)
            status = np.random.choice(statuses)
            cat    = np.random.choice(categories)

            lead_d = {"Routine":7,"Medium":14,"High":5,"Critical":2}[pri]
            target_close = opened + pd.Timedelta(days=lead_d + np.random.randint(-2, 10))
            actual_close = target_close + pd.Timedelta(days=np.random.randint(-3, 21)) \
                           if status == "Closed" else None

            base_cost  = zar_costs[pri]
            actual_cost = base_cost * np.random.lognormal(0, 0.3)
            labour_h    = actual_cost * 0.40 / 450  # R450/hr approx
            asset_key   = np.random.randint(1, 60)

            records.append({
                "WorkOrderID"              : wo_id,
                "PlantKey"                 : pk,
                "AssetKey"                 : asset_key,
                "WorkOrderCategory"        : cat,
                "Priority"                 : pri,
                "WorkOrderStatus"          : status,
                "OpenedDate"               : opened.strftime("%Y-%m-%d"),
                "TargetCloseDate"          : target_close.strftime("%Y-%m-%d"),
                "ClosedDate"               : actual_close.strftime("%Y-%m-%d") if actual_close else "",
                "TradeRequired"            : np.random.choice(trades),
                "EstimatedLabourHours"     : round(labour_h * 0.85, 1),
                "ActualLabourHours"        : round(labour_h, 1),
                "TotalMaintenanceCostZAR"  : round(actual_cost, 2),
                "IsPreventive"             : int(pri in ["Routine","Medium"]),
                "IsSynthetic"              : 1,
            })
            wo_id += 1

    df = pd.DataFrame(records)
    out_path = os.path.join(OUT, "fact_maintenance_work_order_5yr.csv")
    df.to_csv(out_path, index=False)
    elapsed = time.time() - t0
    print(f"   Rows   : {len(df):,}")
    print(f"   File   : {out_path}")
    print(f"   Time   : {elapsed:.1f}s")
    return df


# ══════════════════════════════════════════════════════════════
# 5.  ENERGY SALES MONTHLY + HSE INCIDENTS + FX RATES
# ══════════════════════════════════════════════════════════════
def generate_energy_sales():
    months = pd.date_range(START, END, freq="MS")
    records = []
    tariffs = {1:0.80, 2:1.20, 3:0.65, 4:1.30, 5:0.95, 6:1.25, 7:0.95, 8:1.30, 9:1.10,
               10:0.90, 11:0.65, 12:1.15, 13:1.05, 14:0.90, 15:0.70, 16:1.20, 17:0.75}
    for m in months:
        for _, p in PLANTS.iterrows():
            pk  = int(p["PlantKey"])
            cap = float(p["CapacityMW"])
            cf  = float(p["TargetCF"])
            days_in_month = (m + pd.offsets.MonthEnd(1) - m).days + 1
            sold  = cap * cf * 24 * days_in_month * np.random.uniform(0.93, 1.02)
            tariff_usd = tariffs.get(pk, 0.90) * np.random.uniform(0.97, 1.03)
            fx    = np.random.uniform(17.5, 19.5)  # USD/ZAR
            rev_zar = sold * tariff_usd * fx
            collect = np.random.uniform(0.88, 1.00)
            records.append({
                "YearMonth": m.strftime("%Y-%m"),
                "PlantKey": pk,
                "EnergySoldMWh": round(sold, 2),
                "ContractedTariffUSD": round(tariff_usd, 4),
                "RevenueUSD": round(sold * tariff_usd, 2),
                "USDZAR_Rate": round(fx, 4),
                "RevenueZAR": round(rev_zar, 2),
                "SettlementCollectionPct": round(collect, 4),
                "CollectedRevenueZAR": round(rev_zar * collect, 2),
                "IsSynthetic": 1,
            })
    df = pd.DataFrame(records)
    df.to_csv(os.path.join(OUT, "fact_energy_sales_monthly_5yr.csv"), index=False)
    print(f"\n   Energy sales: {len(df):,} rows saved")
    return df


def generate_hse():
    incident_types = ["Near Miss","First Aid","Medical Treatment","Lost Time Injury",
                      "Property Damage","Environmental","Fire","Security"]
    itype_w = [0.30, 0.22, 0.18, 0.08, 0.10, 0.06, 0.04, 0.02]
    records = []
    inc_id = 90001
    for _, p in PLANTS.iterrows():
        pk = int(p["PlantKey"])
        n  = np.random.randint(20, 120)
        for _ in range(n):
            dt = START + pd.Timedelta(seconds=int(np.random.uniform(0,(END-START).total_seconds())))
            itype = np.random.choice(incident_types, p=itype_w)
            lwd   = int(np.random.exponential(3)) if itype == "Lost Time Injury" else 0
            records.append({
                "IncidentID"   : inc_id,
                "PlantKey"     : pk,
                "IncidentDate" : dt.strftime("%Y-%m-%d"),
                "IncidentType" : itype,
                "Severity"     : np.random.choice(["Low","Medium","High"]),
                "Location"     : np.random.choice(["Site Boundary","Plant Floor","Control Room",
                                                    "Workshop","Substation","Roof/Array"]),
                "LostWorkDays" : lwd,
                "RootCause"    : np.random.choice(["Human Error","Equipment Failure","Weather",
                                                    "Process Gap","Contractor","Unknown"]),
                "Reportable"   : int(itype in ["Lost Time Injury","Medical Treatment","Environmental","Fire"]),
                "IsSynthetic"  : 1,
            })
            inc_id += 1
    df = pd.DataFrame(records)
    df.to_csv(os.path.join(OUT, "fact_hse_incident_5yr.csv"), index=False)
    print(f"   HSE incidents: {len(df):,} rows saved")
    return df


def generate_fx():
    months = pd.date_range(START, END, freq="MS")
    pairs  = [("USD","ZAR",17.8),("EUR","ZAR",19.5),("USD","KES",130),
              ("USD","TZS",2500),("USD","XOF",610),("USD","MZN",64),]
    records = []
    for m in months:
        for base, quote, spot in pairs:
            rate = spot * np.random.uniform(0.92, 1.08)
            records.append({"YearMonth":m.strftime("%Y-%m"),"BaseCurrency":base,
                            "QuoteCurrency":quote,"CloseRate":round(rate,4),"IsSynthetic":1})
    df = pd.DataFrame(records)
    df.to_csv(os.path.join(OUT, "fact_fx_rate_monthly_5yr.csv"), index=False)
    print(f"   FX rates     : {len(df):,} rows saved")
    return df


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    total_t0 = time.time()

    scada   = generate_scada_telemetry()
    ops     = generate_daily_operations()
    outages = generate_outages()
    maint   = generate_maintenance()

    print("\n[5/5] Generating energy sales, HSE incidents, FX rates...")
    sales = generate_energy_sales()
    hse   = generate_hse()
    fx    = generate_fx()

    total_rows = len(scada) + len(ops) + len(outages) + len(maint) + len(sales) + len(hse) + len(fx)

    print("\n" + "=" * 60)
    print("GENERATION COMPLETE")
    print("=" * 60)
    print(f"  SCADA telemetry (15-min) : {len(scada):>10,} rows")
    print(f"  Daily operations (5yr)  : {len(ops):>10,} rows")
    print(f"  Outage events           : {len(outages):>10,} rows")
    print(f"  Maintenance WOs         : {len(maint):>10,} rows")
    print(f"  Energy sales monthly    : {len(sales):>10,} rows")
    print(f"  HSE incidents           : {len(hse):>10,} rows")
    print(f"  FX rates                : {len(fx):>10,} rows")
    print(f"  {'─'*35}")
    print(f"  TOTAL ROWS              : {total_rows:>10,}")
    print(f"  Total time              : {time.time()-total_t0:.0f}s")
    print(f"\n  Output → {OUT}")
    print("=" * 60)
