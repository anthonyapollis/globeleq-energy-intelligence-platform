import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')

ROOT = r'C:\Users\Anthony.DESKTOP-ES5HL78\Documents\Globeleq_Energy_Intelligence_Platform'
GEN  = ROOT + r'\data\generated'
RAW  = ROOT + r'\data\raw'

ops    = pd.read_csv(GEN + r'\fact_plant_operations_daily_5yr.csv')
sales  = pd.read_csv(GEN + r'\fact_energy_sales_monthly_5yr.csv')
outage = pd.read_csv(GEN + r'\fact_outage_5yr.csv')
maint  = pd.read_csv(GEN + r'\fact_maintenance_work_order_5yr.csv')
hse    = pd.read_csv(GEN + r'\fact_hse_incident_5yr.csv')
plants = pd.read_csv(RAW  + r'\dim_plant.csv')

ops['FullDate'] = pd.to_datetime(ops['DateKey'].astype(str), format='%Y%m%d')
ops['Year']     = ops['FullDate'].dt.year
ops = ops.merge(plants[['PlantKey','PlantName','PrimaryTechnology','Country','NameplateCapacity']], on='PlantKey', how='left')

# ── PORTFOLIO OVERVIEW ──────────────────────────────────────────────────────
print("=== PORTFOLIO OVERVIEW ===")
total_twh = ops['GrossGenerationMWh'].sum() / 1e6
avg_avail = ops['AvailabilityPct'].mean()
avg_cf    = ops['CapacityFactorPct'].mean()
total_rev = sales['RevenueZAR'].sum() / 1e9
print(f"  Total energy generated (5yr) : {total_twh:.2f} TWh")
print(f"  Portfolio avg availability   : {avg_avail:.1f}%")
print(f"  Portfolio avg capacity factor: {avg_cf:.1f}%")

print(f"  Total revenue (5yr)          : R{total_rev:.2f}B")
print()

# ── AVAILABILITY BY TECHNOLOGY ──────────────────────────────────────────────
print("=== AVAILABILITY BY TECHNOLOGY ===")
tech_avail = ops.groupby('PrimaryTechnology').agg(
    AvgAvailability=('AvailabilityPct', 'mean'),
    AvgCF=('CapacityFactorPct', 'mean'),
    TotalGenMWh=('GrossGenerationMWh', 'sum')
).sort_values('AvgAvailability', ascending=False)
for t, row in tech_avail.iterrows():
    twh = row['TotalGenMWh'] / 1e6
    print(f"  {t:<18} Avail={row['AvgAvailability']:.1f}%  CF={row['AvgCF']:.1f}%  Gen={twh:.2f} TWh")
print()

# ── TOP 5 PLANTS ─────────────────────────────────────────────────────────────
print("=== TOP 5 PLANTS BY GENERATION ===")
plant_gen = ops.groupby('PlantName')['GrossGenerationMWh'].sum().sort_values(ascending=False).head(5)
for name, mwh in plant_gen.items():
    print(f"  {name:<30} {mwh/1e6:.3f} TWh")
print()

# ── WORST 5 PLANTS (availability) ─────────────────────────────────────────
print("=== BOTTOM 5 PLANTS BY AVAILABILITY ===")
worst = ops.groupby('PlantName')['AvailabilityPct'].mean().sort_values().head(5)
for name, a in worst.items():
    print(f"  {name:<30} {a:.1f}%")
print()

# ── OUTAGE ANALYSIS ──────────────────────────────────────────────────────────
print("=== OUTAGE ANALYSIS ===")
outage['StartDateTime'] = pd.to_datetime(outage['StartDateTime'])
outage['Year'] = outage['StartDateTime'].dt.year
forced  = outage[outage['OutageType'] == 'Forced']
planned = outage[outage['OutageType'] == 'Planned']
print(f"  Total outages       : {len(outage)}")
print(f"  Forced outages      : {len(forced)}  ({len(forced)/len(outage)*100:.1f}%)")
print(f"  Planned outages     : {len(planned)} ({len(planned)/len(outage)*100:.1f}%)")
print(f"  Avg forced duration : {forced['DurationHours'].mean():.1f} hrs")
print(f"  Avg planned duration: {planned['DurationHours'].mean():.1f} hrs")
energy_lost = outage['EstimatedEnergyLostMWh'].sum()
print(f"  Total energy lost   : {energy_lost:,.0f} MWh")

by_tech = outage.merge(plants[['PlantKey','PrimaryTechnology']], on='PlantKey', how='left')
fo_tech = by_tech[by_tech['OutageType']=='Forced'].groupby('PrimaryTechnology').size().sort_values(ascending=False)
print("  Forced outages by technology:")
for t, n in fo_tech.items():
    print(f"    {t:<18} {n}")
print()

# ── OUTAGE TREND YOY ─────────────────────────────────────────────────────────
print("=== FORCED OUTAGES YEAR-OVER-YEAR ===")
fo_yoy = forced.groupby('Year').size()
for yr, n in fo_yoy.items():
    print(f"  {yr}: {n}")
print()

# ── MAINTENANCE ──────────────────────────────────────────────────────────────
print("=== MAINTENANCE ===")
maint['OpenedDate'] = pd.to_datetime(maint['OpenedDate'])
maint['Year'] = maint['OpenedDate'].dt.year
avg_cost   = maint['TotalMaintenanceCostZAR'].mean()
total_cost = maint['TotalMaintenanceCostZAR'].sum() / 1e6
print(f"  Total work orders      : {len(maint)}")
print(f"  Avg cost per WO        : R{avg_cost:,.0f}")
print(f"  Total maintenance cost : R{total_cost:.1f}M (5yr)")
by_type = maint.groupby('WorkOrderCategory').agg(Count=('WorkOrderID','count'), Total=('TotalMaintenanceCostZAR','sum')).sort_values('Total', ascending=False)
for t, row in by_type.iterrows():
    print(f"  {t:<20} {int(row['Count']):>4} WOs   R{row['Total']/1e6:.1f}M")
print()

# ── REVENUE TREND ─────────────────────────────────────────────────────────────
print("=== ANNUAL REVENUE ===")
sales['MonthDate'] = pd.to_datetime(sales['YearMonth'])
sales['Year'] = sales['MonthDate'].dt.year
ann_rev = sales.groupby('Year')['RevenueZAR'].sum()
prev = None
for yr, rev in ann_rev.items():
    if prev:
        chg = (rev - prev) / prev * 100
        print(f"  {yr}: R{rev/1e6:.0f}M  ({chg:+.1f}%)")
    else:
        print(f"  {yr}: R{rev/1e6:.0f}M")
    prev = rev
print()

# ── REVENUE BY TECH ──────────────────────────────────────────────────────────
print("=== REVENUE BY TECHNOLOGY ===")
sales_m = sales.merge(plants[['PlantKey','PrimaryTechnology']], on='PlantKey', how='left')
rev_tech = sales_m.groupby('PrimaryTechnology')['RevenueZAR'].sum().sort_values(ascending=False)
total = rev_tech.sum()
for t, r in rev_tech.items():
    print(f"  {t:<18} R{r/1e6:.0f}M  ({r/total*100:.1f}%)")
print()

# ── HSE ───────────────────────────────────────────────────────────────────────
print("=== HSE INCIDENTS ===")
print(f"  Total incidents: {len(hse)}")
by_type = hse.groupby('IncidentType').size().sort_values(ascending=False)
for t, n in by_type.items():
    print(f"  {t:<28} {n}")
lti = hse[hse['IncidentType'] == 'Lost Time Injury']
print(f"  LTI avg lost work days: {lti['LostWorkDays'].mean():.1f}")
print()

# ── AVAILABILITY YOY ─────────────────────────────────────────────────────────
print("=== AVAILABILITY YEAR-OVER-YEAR ===")
yoy = ops.groupby('Year')['AvailabilityPct'].mean()
for yr, a in yoy.items():
    print(f"  {yr}: {a:.2f}%")
print()

# ── CO2 AVOIDED ───────────────────────────────────────────────────────────────
print("=== ESG: CO2 AVOIDED ===")
renewables = ops[ops['PrimaryTechnology'].isin(['Solar PV','Wind','Hydro'])]
co2_avoided = renewables['GrossGenerationMWh'].sum() * 0.747
print(f"  Renewable generation (5yr): {renewables['GrossGenerationMWh'].sum()/1e6:.2f} TWh")
print(f"  CO2 avoided (SA grid 0.747 tCO2e/MWh): {co2_avoided/1e6:.2f} Mt CO2e")
