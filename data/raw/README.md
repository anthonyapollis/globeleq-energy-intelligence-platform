# Globeleq Energy Portfolio Data Model

## Scope
This model represents an African independent power producer that invests in, develops, owns,
operates and maintains utility-scale power assets. It covers:

- Portfolio and plant master data
- Geography and technology
- Power purchase, tolling and concession agreements
- Owners, off-takers, government partners, lenders, EPC and O&M parties
- Daily generation, availability, capacity factor, curtailment and emissions
- Battery operation
- Monthly energy sales and conversion to ZAR
- Outages and maintenance work orders
- Construction schedule and cost performance
- HSE incidents

## Source versus synthetic data
- `dim_plant.csv`, agreement descriptions and key organisations are based on the supplied brochure.
- All operational and financial fact files are synthetic and marked with `IsSynthetic = 1`.
- Project statuses and forecast dates in the brochure are a historical snapshot. Verify them before production use.
- The brochure appears to contain a typo for Soutpan annual generation (`60 Wh`); the model uses `60 GWh`
  because that unit is consistent with the surrounding plant descriptions.

## Files
- `globeleq_energy_dw.sql`: SQL Server warehouse DDL, seed dimensions, views and indexes.
- `Globeleq_PowerBI_Measures.dax`: Power BI measures.
- `globeleq_erd.mmd`: Mermaid ERD.
- Dimension and fact CSV files for ETL testing.
- `globeleq_energy_model.zip`: complete package.

## Recommended Power BI model
Use one-to-many, single-direction relationships:

- `DimDate[DateKey]` -> daily fact date keys.
- `DimDate[DateKey]` -> monthly fact month keys.
- `DimPlant[PlantKey]` -> every fact table.
- `DimAsset[AssetKey]` -> outage and maintenance facts.
- Keep fact-to-fact relationships disabled.

## Business grains
- Plant operations: one row per plant per day.
- Battery operation: one row per battery plant per day.
- Energy sales: one row per plant per month.
- Outage: one row per outage event.
- Maintenance: one row per work order.
- Construction: one row per project per month.
- HSE: one row per incident.

## Appropriate executive KPIs
Operational: availability, capacity factor, generation, curtailment, forced outage rate, energy lost.
Commercial: energy sold, realised tariff, revenue in ZAR, settlement collection, PPA delivery.
Maintenance: open backlog, critical backlog, MTTR, maintenance cost, planned versus corrective work.
Projects: actual progress, schedule variance, cost variance, MW under construction.
ESG/HSE: renewable generation share, emissions intensity, CO2 avoided, LTIs and lost work days.

Product-sales KPIs such as units sold, basket size and product margin are not suitable here. The business
sells contracted electricity and manages long-lived infrastructure assets, so asset performance and
contract delivery are the core measures.
