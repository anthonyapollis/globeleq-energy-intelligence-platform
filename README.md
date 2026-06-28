# Globeleq Energy Intelligence Platform

**Full-stack Azure Databricks data engineering + ML portfolio project**
Synthetic SCADA telemetry from 19 African IPP power plants · 3M+ rows · 5 ML models

---

## Project Overview

Globeleq operates utility-scale power plants across seven African nations. This platform
ingests 15-minute SCADA telemetry, applies a Medallion Architecture (Bronze → Silver → Gold)
on Azure Databricks, and surfaces predictive ML models for operations, maintenance, and
commercial decision-making.

| Metric | Value |
|---|---|
| Total rows generated | **3,024,807** |
| SCADA telemetry rows | **2,981,664** (15-min intervals, 17 plants × 5 years) |
| Plants | **19** across **7 countries** (17 operating · 2 under construction) |
| Operating capacity | **1,794 MW** · Construction pipeline: **485 MW** |
| Date range | **2020–2024** (5 years) |
| ML models | **8** registered in MLflow (5 operational + 3 forecasting) |
| Annual portfolio revenue | **~R139M** (synthetic; reflects contracted PPA tariff scale) |
| Portfolio availability (operating fleet) | **~92%** (82.7% incl. under-construction plants) |

---

## Stack

- **Azure Databricks** — PySpark notebooks, Delta Lake, MLflow
- **Azure Data Factory** — Copy Activities, ForEach, IfCondition, Teams webhook
- **Azure Data Lake Gen2** — ADLS raw/bronze/silver/gold containers
- **Azure SQL Server** — GlobeleqEnergyDW (27 tables: 17 core + 10 V2 upgrade · 6 BI views)
- **Python** — Data generation, ML (XGBoost, LightGBM, sklearn), dirty-data injection
- **Power BI** — 111 DAX measures across 9 report pages, Databricks SQL endpoint
- **openpyxl** — 8-sheet Excel report with charts

---

## Directory Structure

```
Globeleq_Energy_Intelligence_Platform/
├── data/
│   ├── raw/                        ← Original dim/fact CSVs + SQL DDL
│   ├── generated/                  ← Synthetic 3M+ row datasets
│   └── processed/                  ← Gold layer output (populated by Databricks)
├── notebooks/
│   ├── 01_bronze_ingest.py         ← ADF-triggered, raw CSV → Delta Bronze
│   ├── 02_silver_transform.py      ← Type casting, enrichment, rolling windows
│   ├── 03_gold_kpis.py             ← Executive KPIs, ML feature store
│   └── 04_ml_energy_intelligence.py← 5 ML models + MLflow tracking
├── pipelines/
│   └── adf_globeleq_pipeline.json  ← Full ADF pipeline definition
├── reports/
│   ├── generate_excel_report.py    ← Generates 8-sheet Excel workbook
│   ├── Globeleq_Energy_Intelligence_Report.xlsx
│   └── charts/                     ← 13 publication-quality PNGs (4.7 MB total)
├── scripts/
│   ├── generate_synthetic_data.py  ← Vectorised data generator (3M+ rows, ~2.5 min)
│   ├── inject_dirty_data.py        ← Injects 35 realistic DQ patterns (83K dirty rows)
│   ├── generate_charts.py          ← 13 ML + operational charts (correlation, ROC, residuals)
│   ├── data_insights.py            ← Portfolio analytics summary
│   └── reconcile.py                ← Numbers reconciliation across all tables
├── ebook/
│   └── globeleq_energy_intelligence_ebook.html
└── data/raw/
    ├── globeleq_energy_dw.sql              ← Core DDL: 17 tables (9 dims + 2 bridges + 6 facts + DimDate)
    ├── globeleq_energy_dw_v2_upgrade.sql   ← V2: 10 tables + 6 BI views (bi schema)
    ├── Globeleq_PowerBI_Measures.dax       ← Original 32 measures
    └── Globeleq_PowerBI_Measures_v2.dax    ← V2: 111 measures, 9 report pages
```

---

## Generated Datasets

| File | Rows | Size | Description |
|---|---|---|---|
| `scada_telemetry_15min.csv` | 2,981,664 | 382 MB | 15-min SCADA per plant |
| `fact_plant_operations_daily_5yr.csv` | 34,713 | 2.6 MB | Daily generation KPIs |
| `fact_outage_5yr.csv` | 1,656 | — | Outage events |
| `fact_maintenance_work_order_5yr.csv` | 3,878 | — | Maintenance WOs |
| `fact_energy_sales_monthly_5yr.csv` | 1,020 | — | Monthly revenue |
| `fact_hse_incident_5yr.csv` | 1,516 | — | HSE incidents |
| `fact_fx_rate_monthly_5yr.csv` | 360 | — | USD/ZAR + other pairs |

---

## ML Models

**Operational ML models (MLflow Registry):**

| # | Model | Algorithm | Key Metric |
|---|---|---|---|
| 1 | Energy Yield Forecaster | XGBoost Regressor | R²=0.998, MAE=62 MWh, RMSE=151 MWh |
| 2 | Plant Availability Tier Classifier | LightGBM Classifier | AUC=0.85, AP=0.97 |
| 3 | Maintenance Cost Estimator | Random Forest | R²=0.999, MAE=R103, OOB=0.999 |
| 4 | Curtailment Anomaly Detector | Isolation Forest | Anomaly rate=5.0% (1,553/31,059) |
| 5 | Portfolio Revenue Forecaster | LightGBM Regressor | R²=0.93, MAPE=3.1% |

**Forecasting model registry (V2 — RMSE-selected, not MAPE):**

| # | Model | Family | Selection |
|---|---|---|---|
| 6 | Weekly Seasonal Profile | Seasonal Decomposition | Baseline |
| 7 | Robust Dynamic Regression | MM-Estimator Regression | Challenger |
| **8** | **Technology-Aware Weather GBM** | **Gradient Boosting** | **Selected** (lowest RMSE) |

---

## Running Locally

```bash
# 1. Generate synthetic data (~2.5 min)
python scripts/generate_synthetic_data.py

# 2. Generate Excel report
python reports/generate_excel_report.py

# 3. Serve the ebook
python -m http.server 8770 --directory ebook
# Open http://localhost:8770/globeleq_energy_intelligence_ebook.html

# 4. Upload notebooks to Databricks Repos and run via ADF
# See pipelines/adf_globeleq_pipeline.json for full pipeline definition
```

---

## Data Sources

- `dim_plant.csv` and agreement/organisation data derived from the Globeleq corporate brochure.
- All operational fact data is **synthetic** (`IsSynthetic=1`) — not real Globeleq operational data.
- Terra Firma Data Analyst assignment solution included for reference.

---

## Author

**Anthony Apollis** — Data Engineer & ML Practitioner
[github.com/anthonyapollis](https://github.com/anthonyapollis) · anthony.apollis@gmail.com
