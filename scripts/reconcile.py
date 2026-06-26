import pandas as pd, warnings
warnings.filterwarnings('ignore')

ROOT = r'C:\Users\Anthony.DESKTOP-ES5HL78\Documents\Globeleq_Energy_Intelligence_Platform'
GEN  = ROOT + r'\data\generated'
RAW  = ROOT + r'\data\raw'

plants = pd.read_csv(RAW + r'\dim_plant.csv')
ops    = pd.read_csv(GEN + r'\fact_plant_operations_daily_5yr.csv')
sales  = pd.read_csv(GEN + r'\fact_energy_sales_monthly_5yr.csv')
outage = pd.read_csv(GEN + r'\fact_outage_5yr.csv')
maint  = pd.read_csv(GEN + r'\fact_maintenance_work_order_5yr.csv')
hse    = pd.read_csv(GEN + r'\fact_hse_incident_5yr.csv')
fx     = pd.read_csv(GEN + r'\fact_fx_rate_monthly_5yr.csv')

ops['FullDate'] = pd.to_datetime(ops['DateKey'].astype(str), format='%Y%m%d')
ops['Year']     = ops['FullDate'].dt.year
ops = ops.merge(
    plants[['PlantKey','PlantName','PrimaryTechnology','NameplateCapacity','ProjectStatus']],
    on='PlantKey', how='left'
)

op_plants  = plants[plants['ProjectStatus'] == 'Operating']
con_plants = plants[plants['ProjectStatus'] == 'In Construction']
op_mw  = op_plants['NameplateCapacity'].sum()
con_mw = con_plants['NameplateCapacity'].sum()

total_gross = ops['GrossGenerationMWh'].sum()
total_net   = ops['NetGenerationMWh'].sum()
total_rev   = sales['RevenueZAR'].sum()
ann_rev     = total_rev / 5

rows = {
    'scada_telemetry_15min':          2981664,
    'fact_plant_operations_daily':    len(ops),
    'fact_outage':                    len(outage),
    'fact_maintenance_work_order':    len(maint),
    'fact_energy_sales_monthly':      len(sales),
    'fact_hse_incident':              len(hse),
    'fact_fx_rate_monthly':           len(fx),
}
total_rows = sum(rows.values())

print("=== GLOBELEQ NUMBERS RECONCILIATION ===")
print()
print("--- PLANTS ---")
print("  Total plants in dim_plant.csv :", len(plants))
print("  Operating                     :", len(op_plants))
print("  Under Construction            :", len(con_plants))
print("  Operating capacity (MW)       :", round(op_mw, 1))
print("  Construction capacity (MW)    :", round(con_mw, 1))
print("  Countries                     :", plants['Country'].nunique())
print()

print("--- GENERATION ---")
print("  Gross generation 5yr (TWh)    :", round(total_gross/1e6, 3))
print("  Net generation 5yr (TWh)      :", round(total_net/1e6, 3))
print("  Annual avg gross (GWh/yr)     :", round(total_gross/5/1e3, 0))
print()

print("--- REVENUE ---")
print("  Total revenue 5yr (R M)       :", round(total_rev/1e6, 1))
print("  Annual avg revenue (R M/yr)   :", round(ann_rev/1e6, 1))
if 'RevenueUSD' in sales.columns:
    print("  Total revenue 5yr (USD M)     :", round(sales['RevenueUSD'].sum()/1e6, 1))
print()

print("--- ROW COUNTS ---")
for t, n in rows.items():
    print(f"  {t:<45} {n:>10,}")
print(f"  {'TOTAL':<45} {total_rows:>10,}")
print()

print("--- DISCREPANCIES (README vs Actual) ---")
readme_rows = 3024807
readme_rev  = 139
brochure_mw = 1794
brochure_con= 485

row_diff = total_rows - readme_rows
rev_diff = round(ann_rev/1e6 - readme_rev, 1)
mw_diff  = round(op_mw - brochure_mw, 1)
con_diff = round(con_mw - brochure_con, 1)

status = lambda d: "OK" if abs(d) < 1 else "FIX"

print(f"  Total rows    README:{readme_rows:,}  Actual:{total_rows:,}  Delta:{row_diff:+,}  [{status(row_diff)}]")
print(f"  Ann revenue   README:R{readme_rev}M  Actual:R{ann_rev/1e6:.0f}M  Delta:{rev_diff:+.0f}M  [{status(rev_diff)}]")
print(f"  Operating MW  Brochure:{brochure_mw}  Actual:{op_mw:.0f}  Delta:{mw_diff:+.0f}  [{status(mw_diff)}]")
print(f"  Constr MW     Brochure:{brochure_con}  Actual:{con_mw:.0f}  Delta:{con_diff:+.0f}  [{status(con_diff)}]")
print(f"  Plant count   README:19  Actual:{len(plants)}  [{'OK' if len(plants)==19 else 'FIX'}]")
print()

print("--- CO2 & ESG ---")
total_co2_avoided = ops['CO2AvoidedTonnes'].sum()
total_scope1      = ops['Scope1EmissionsTonnesCO2e'].sum()
ren_gen = ops[ops['PrimaryTechnology'].isin(['Solar PV','Wind','Geothermal','Solar PV + BESS'])]['GrossGenerationMWh'].sum()
print("  CO2 avoided 5yr (Mt)          :", round(total_co2_avoided/1e6, 3))
print("  Scope 1 emissions 5yr (kt)    :", round(total_scope1/1e3, 1))
print("  Renewable share               :", round(ren_gen/total_gross*100, 1), "%")
