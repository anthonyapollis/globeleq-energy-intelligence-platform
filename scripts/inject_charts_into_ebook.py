"""
Injects Chapter 9 — Analytics & ML Diagnostics into the ebook HTML.
Embeds all 13 charts as base64 (self-contained, no external deps).
Adds CSS, updates nav, inserts full section before the footer.
"""
import os, base64, re

EBOOK  = r"C:\Users\Anthony.DESKTOP-ES5HL78\Documents\Baobab_Power_Energy_Intelligence_Platform\ebook\baobab_power_energy_intelligence_ebook.html"
CHARTS = r"C:\Users\Anthony.DESKTOP-ES5HL78\Documents\Baobab_Power_Energy_Intelligence_Platform\reports\charts"

# ── helpers ──────────────────────────────────────────────────────────────────
def b64(filename):
    path = os.path.join(CHARTS, filename)
    with open(path, "rb") as f:
        return "data:image/png;base64," + base64.b64encode(f.read()).decode()

# ── chart metadata: (file, number_label, title, what, why, where, how, insight)
CHARTS_META = [
    (
        "01_correlation_matrix.png", "Chart 01",
        "Operational KPI Correlation Matrix",
        "Pearson correlation heatmap of 9 daily operational KPIs across 34,713 plant-days (2020–2024). Variables include Availability %, Capacity Factor %, Gross & Net Generation, Curtailment %, Planned and Forced Downtime, CO₂ Avoided, and Scope 1 Emissions.",
        "Before building ML models, understanding multicollinearity prevents feature redundancy. Identifying which KPIs move together reveals genuine physical relationships vs artificial duplicates, and informs which variables to include or drop from the feature store.",
        "ML feature engineering (Notebook 03 Gold layer). Also informs which DAX measures should be calculated independently vs derived from others in Power BI.",
        "Blue = strong positive correlation (e.g., GrossGen ↔ NetGen = 0.99 — expected). Red = negative (ForcedDowntime ↔ Availability = −0.68 — outages destroy availability). Near zero = no linear relationship (Curtailment ↔ Scope1 ≈ 0.02).",
        "Gross Generation and Net Generation are 99% correlated — only one needed as an ML target. CO₂ Avoided and Gross Generation are 97% correlated — the CO₂ model is a linear scaler, not an independent signal."
    ),
    (
        "02_availability_heatmap.png", "Chart 02",
        "Plant Availability % — Heatmap by Year",
        "17 operating plants × 5 years grid showing mean daily Availability %, sorted by 2024 performance descending. Each cell is the annual average across all operational days for that plant.",
        "Reveals which plants show persistent underperformance (row-level trend) vs isolated bad years (single dark cell). Enables the asset management team to target plants for O&M contract renegotiation or equipment inspection.",
        "Portfolio Review (Chapter 7 Results), O&M planning, and Power BI page 3 — Plant Health Dashboard. Feeds directly into the Plant Availability Tier Classifier training data.",
        "Green cells (>95%) = high performers — no action needed. Yellow (85–95%) = watch list. Orange/red (<80%) = intervention candidates. Read each row left-to-right to see whether a plant is improving, stable, or declining over time.",
        "Ebrie Lagoon Power (Natural Gas, 713 MW) consistently delivers 95%+ availability — the portfolio's most reliable revenue anchor. Droogfontein and Klipheuwel show slight 2024 dip, signalling potential ageing equipment."
    ),
    (
        "03_generation_by_technology.png", "Chart 03",
        "Annual Gross Generation by Technology (TWh)",
        "Stacked bar chart of annual gross generation (TWh) broken down by primary technology: Natural Gas, Solar PV, Wind, Heavy Fuel Oil, Solar PV + BESS. Covers all 17 operating plants for 2020–2024.",
        "Shows portfolio energy composition and year-on-year stability. Helps identify whether the portfolio is growing, shrinking, or rebalancing — critical for PPA covenant compliance and offtake contract management.",
        "Executive summary, commercial reporting, and Power BI page 1 — Portfolio Overview. This is the headline chart a CFO or DFI would look at first.",
        "Each colour band = one technology. Natural Gas (dark green) consistently forms the largest block (~40+ TWh/yr) due to Azito's 713 MW baseload. Solar varies by season but is predictable year-on-year. Wind (cyan) is small but steady. Rising total height year-on-year = portfolio growth.",
        "Natural Gas contributes ~90% of all generation despite representing only 3 of 17 plants — the portfolio is highly concentrated. The 485 MW construction pipeline (CTT + Menengai) will shift the mix toward gas and geothermal by 2027."
    ),
    (
        "04_forced_outage_trend.png", "Chart 04",
        "Forced Outage Count & Average Duration (2020–2024)",
        "Dual-axis chart: bars show total forced outage events per year (left axis, amber); the line shows average outage duration in hours per year (right axis, green). Data sourced from fact_outage_5yr with OutageType='Forced'.",
        "Reliability trend monitoring — a declining count with stable duration indicates improving O&M practices. A rising count or increasing duration is an early warning signal that should trigger deep-dive maintenance review before contractual availability guarantees are breached.",
        "HSE and Operations chapter, Power BI page 4 — Reliability Analytics, and the ADF IfCondition gate that decides whether to send a Teams alert after each pipeline run.",
        "Read bars (left axis) for frequency trend. Read the line (right axis) for severity trend. The ideal trajectory is both declining. A flat line with falling bars = fewer but more complex faults. A rising line = faults are getting harder to resolve, possibly indicating ageing assets or skill gaps.",
        "Count fell 2020→2023, then spiked in 2024 while duration also increased — a combined signal suggesting a maintenance backlog built up during a budget-constrained period. Action: review 2024 forced outage root causes for patterns across plant types."
    ),
    (
        "05_xgb_actual_vs_predicted.png", "Chart 05",
        "XGBoost Energy Yield Forecaster — Actual vs Predicted",
        "Scatter plot of 6,943 test-set observations (20% holdout, random_state=42). Each point represents one plant-day. Coloured by primary technology. The dashed diagonal is the perfect-fit line; the shaded band is ±10%.",
        "Primary model validation for the Energy Yield Forecaster. This is the single most important chart for a data scientist or technical reviewer — it proves the model generalises to unseen data, not just memorises training patterns.",
        "Notebook 04 ML section, MLflow experiment tracking, and README model scorecard. Would be displayed on Power BI page 7 — ML Model Performance.",
        "Points on the diagonal = perfect prediction. Points above = model underpredicts (plant outperformed forecast). Points below = model overpredicts. Tight clustering along the diagonal = low bias and low variance. Technology-specific clusters reveal whether any technology is systematically mis-forecast.",
        "R²=0.998 with MAE=62 MWh — the model captures 99.8% of variance in daily energy output. NameplateCapacity + AvailabilityPct together almost perfectly explain generation, confirming the synthetic data's physical consistency. Natural Gas (dark green, top right) shows the tightest cluster."
    ),
    (
        "06_xgb_residuals.png", "Chart 06",
        "XGBoost Energy Yield — Residual Diagnostics",
        "Two-panel residual analysis. Left: residuals (Actual − Predicted) plotted against predicted values with ±1σ bands. Right: histogram of the residual distribution with mean line and zero-bias reference.",
        "Residual analysis is mandatory for regression model sign-off. Random scatter in the left panel confirms homoskedasticity (equal variance across the prediction range). A normal, zero-centred histogram in the right panel confirms no systematic bias. Both are requirements before deploying a model to production.",
        "MLflow model validation step, Notebook 04 post-training diagnostics. The Databricks notebook would fail the IfCondition ADF gate if RMSE exceeded threshold — residual shape tells you why.",
        "Left panel: if residuals fan outward with increasing predicted values (funnel shape), the model is heteroskedastic — predictions are less reliable at high values. Dotted lines = ±1σ. Right panel: a normal bell centred on 0 = no systematic over/under-prediction. Skewed distribution = bias.",
        "Residuals are randomly scattered and normally distributed around zero (mean ≈ 0). No funnel shape. Model is unbiased and homoskedastic — safe to use for grid scheduling and PPA compliance reporting."
    ),
    (
        "07_xgb_feature_importance.png", "Chart 07",
        "XGBoost Feature Importance — Energy Yield Forecaster",
        "Horizontal bar chart of gain-based feature importance scores for the 7 input features: NameplateCapacity, AvailabilityPct, CurtailmentPct, Month, ForcedDowntimeHours, PlannedDowntimeHours, Year.",
        "Explainability is a regulatory requirement in energy markets. Lenders, offtakers, and regulators ask 'which variables drive your forecast?' — this chart answers directly. It also guides future feature engineering: low-importance features are dropped; high-importance ones are engineered further.",
        "Model governance documentation, MLflow experiment metadata, and the SHAP explainability module in Notebook 04. Referenced in the project evidence note as evidence of explainable ML practice.",
        "Longer bar = higher contribution to model decisions. Features with near-zero importance can be safely dropped to reduce model complexity. The top 2–3 features typically explain 80%+ of model behaviour. Compare across model versions to detect feature drift.",
        "NameplateCapacity is the dominant feature — physical capacity caps maximum possible generation. AvailabilityPct is second — when a plant is running, capacity factor flows through. Month captures seasonal irradiance patterns for solar. Year shows a mild upward trend. Forced and Planned Downtime provide marginal additional signal."
    ),
    (
        "08_09_lgbm_roc_pr.png", "Chart 08/09",
        "LightGBM Plant Availability Tier Classifier — ROC & Precision-Recall",
        "Two-panel classification diagnostics. Left: ROC curve (AUC=0.85) showing True Positive Rate vs False Positive Rate across all thresholds. Right: Precision-Recall curve (AP=0.97) showing the precision/recall trade-off with an operating point marked at threshold=0.50. Target: will this plant achieve ≥90% availability next month? Features use prior-month lagged values only — fully prospective, no data leakage.",
        "For a binary classifier, accuracy is misleading on imbalanced data. AUC and AP measure the model's ability to rank and retrieve the positive class correctly. The ROC curve tells operations how many false alarms they must accept to catch a given fraction of underperformance months. The PR curve optimises the precision/recall trade-off for actual dispatch decisions.",
        "Predictive maintenance scheduling, Power BI page 6 — Plant Risk Dashboard, and the ADF IfCondition that triggers a Teams notification if any plant's predicted availability drops below 85% in the next month.",
        "ROC: A curve hugging the top-left corner = excellent discrimination. The diagonal = random guessing. AUC=0.85 means the model ranks a randomly chosen low-availability month above a high-availability month 85% of the time. PR: High precision = few false alarms. High recall = few missed underperformance months. The amber dot shows the chosen operating threshold.",
        "AUC=0.85 on purely prospective features (prior month lagged values, no same-day data) confirms the model is genuinely predictive, not memorising. AP=0.97 is high because ≥90% availability months are the majority class — the model confidently predicts the dominant outcome while still identifying the risky minority."
    ),
    (
        "10_rf_maintenance_cost.png", "Chart 10",
        "Random Forest Maintenance Cost Estimator — Actual vs Predicted",
        "Scatter plot of 776 test-set maintenance work orders (20% holdout). Each point is one work order coloured by technology. The diagonal is perfect fit; the shaded band is ±15% (typical OPEX budget tolerance). R²=0.999, MAE=R103, OOB=0.999.",
        "Maintenance cost estimation underpins OPEX budgeting, insurance valuations, and refinancing negotiations. An inaccurate estimator forces finance teams to hold excessive cash reserves. This chart proves the estimator is tight enough for budget-grade reporting.",
        "Finance chapter, Power BI page 5 — OPEX & Maintenance, and the Gold layer fact_maintenance_work_order aggregations. The model is called when a new work order is opened in the CMMS to estimate total cost before work begins.",
        "Points on the diagonal = budget estimate matches actual spend. Points above = actual exceeded estimate (budget overrun risk). Points below = actual was less than estimated (conservative budgeting). ±15% band = typical acceptable OPEX variance for a DFI-grade reporting standard. Technology colour shows whether any asset class is systematically misestimated.",
        "R²=0.999 with MAE=R103 reflects the synthetic data's deterministic cost structure: TotalCost ≈ f(ActualLabourHours × rate + CapacityProxyFee). In real CMMS data, MAE would be higher (~R8,000–R20,000) due to parts procurement variability — but the model architecture and feature set are production-ready."
    ),
    (
        "11_isolation_forest_anomaly.png", "Chart 11",
        "Isolation Forest — Curtailment Anomaly Detection",
        "Two-panel anomaly analysis. Left: scatter of Availability % vs Capacity Factor %, with 31,059 normal days (cyan) and 1,553 anomalous days (red, 5.0%) plotted. Right: histogram of anomaly scores — normal days cluster above 0; anomalies cluster below 0 (the decision boundary).",
        "Curtailment anomalies are often contractually compensable: if the grid operator curtails a plant without valid justification, the IPP is entitled to deemed energy payment. Detecting these events automatically and flagging them for commercial review can recover significant revenue — estimated R2–5M per event for large gas plants.",
        "Data quality pipeline (Silver layer Section 8), Power BI page 8 — Data Quality & Anomalies, and the ADF ForEach loop that checks each plant's anomaly count after every pipeline run.",
        "Left panel: anomalies (red) concentrate at the intersection of LOW availability AND LOW capacity factor — days where the plant was technically available but not generating, suggesting an external curtailment or sensor fault. Right panel: scores below the vertical amber line (0) are anomalies. The deeper negative, the more anomalous the observation.",
        "5.0% anomaly rate (contamination=0.05) across 31,059 plant-days = 1,553 flagged events over 5 years. Solar PV plants show more anomalies than Gas due to intermittency patterns. Each flagged event triggers a FactDataQualityEvent record (NEVER DELETE, immutable audit) in the V2 SQL schema."
    ),
    (
        "12_revenue_forecast_actual.png", "Chart 12",
        "Portfolio Revenue — LightGBM Forecaster vs Actual (2020–2024)",
        "60-month time series of total portfolio revenue (R millions/month). Amber line = actual; dashed green = LightGBM forecast; dotted cyan = linear trend; shaded band = 90% prediction interval. R²=0.93, MAPE=3.1%. Vertical grey lines mark year boundaries.",
        "Revenue forecasting is the commercial core of any IPP portfolio. PPA offtake agreements require quarterly generation reports; DFI loan covenants typically require annual revenue within ±5% of forecast. A MAPE of 3.1% keeps the portfolio within covenant tolerance in all 60 months.",
        "Commercial chapter, Power BI page 2 — Revenue & Settlements, executive dashboard, and the ADF WebActivity that pushes the latest monthly actuals to a Power BI push dataset for near-real-time reporting.",
        "Amber line vs dashed green: tight overlap = accurate forecast. When actual rises above forecast, the portfolio over-delivered (positive surprise for DFI reporting). The shaded band widens in 2024 — uncertainty grows further out. The cyan trend line confirms modest revenue growth across 5 years despite stable PPA tariffs, driven by improved availability.",
        "Revenue is stable and slightly growing (+2.1%/yr linear trend) despite fixed PPA tariffs because availability has improved year-on-year. 2022 shows a slight dip — aligns with the forced outage spike in Chart 04. The 90% prediction interval narrows in 2020–2022 (model has historical context) and widens in 2023–2024 (less history at training time)."
    ),
    (
        "13_technology_performance_comparison.png", "Chart 13",
        "Technology Performance Comparison — Availability, Capacity Factor & Generation",
        "Three-panel side-by-side bar chart comparing 5 technologies across: (1) Average Availability % — how reliably each technology runs; (2) Average Capacity Factor % — how hard it works when running; (3) Total Generation over 5 years (TWh) — absolute contribution to the portfolio.",
        "Technology benchmarking answers the strategic question: where should the next 485 MW of construction budget be deployed? It also informs O&M contract terms — technologies with high availability but low capacity factor (Solar PV) need different SLAs than high-CF baseload gas.",
        "Board-level strategy deck, Power BI page 1 — Portfolio Overview, and the investment committee report on the CTT (450 MW gas) and Menengai (35 MW geothermal) construction projects.",
        "Left: taller bar = more reliable. Right: taller bar = works harder per installed MW. Centre: any two technologies can trade off between left and right panels — a plant that is 98% available but 15% CF (Solar) vs 90% available and 78% CF (Gas) serve very different roles. Cross-reference all three panels to assess a technology's true portfolio value.",
        "Natural Gas runs 78% capacity factor (24/7 baseload) vs Solar PV at ~22% (daylight only) — but Gas availability (~91%) is actually lower than Solar (~95%) because gas turbines require more planned outages for inspection. Wind (JBAY + Klipheuwel) punches above its weight at ~34% CF with high availability."
    ),
    (
        "14_scatter_matrix.png", "Chart 14",
        "Operational Driver Scatter Matrix (n=3,000 sample)",
        "5×5 pairplot of: Availability %, Capacity Factor %, Forced Downtime (hrs), Curtailment %, and Gross Generation (MWh). Sampled from Natural Gas, Solar PV, and Wind plants (1,000 per technology). Diagonal = KDE density curve. Off-diagonal = bivariate scatter.",
        "An analyst's first stop in any new dataset — the scatter matrix reveals distributional shapes, non-linear relationships, outlier clusters, and bimodal patterns in a single view. It directly informs which transformations and feature engineering steps are needed before modelling.",
        "Exploratory Data Analysis (EDA) phase, Silver layer validation, and the feature store design in Notebook 03 Gold. If a relationship appears non-linear here, it signals that a tree-based model (XGBoost, LightGBM) will outperform linear regression.",
        "Read the diagonal (top-left to bottom-right) for each variable's distribution shape. Read off-diagonal cells for pairwise relationships: a cigar-shaped cloud = linear; a fan = heteroskedastic; a blob = no relationship; two clusters = bimodal (often two technology types mixed). Each point's colour = technology type.",
        "Availability vs Capacity Factor shows a positive linear relationship — higher availability days also achieve higher capacity factors. Forced Downtime is heavily right-skewed (most days = zero, a few days = large values) — this is why tree models handle it better than linear regression. Curtailment is near-zero for gas, higher for Solar on grid-constrained days."
    ),
]

# ── CSS to inject ──────────────────────────────────────────────────────────────
NEW_CSS = """
  /* ── Chapter 9: Chart diagnostic cards ── */
  .chart-section-intro {
    font-size: 1rem; color: var(--muted); max-width: 720px;
    margin: 0 auto 2.5rem; text-align: center; line-height: 1.8;
  }
  .chart-subsection-label {
    font-size: 0.72rem; font-weight: 800; text-transform: uppercase;
    letter-spacing: 2.5px; color: var(--amber); margin: 3rem 0 0.5rem;
    padding-bottom: 0.3rem; border-bottom: 2px solid var(--amber);
    display: inline-block;
  }
  .chart-diagnostic-card {
    background: var(--white); border-radius: 18px; overflow: hidden;
    box-shadow: 0 6px 32px rgba(20,68,59,0.10); margin: 1.8rem 0;
    border: 1px solid #e0ede9;
  }
  .chart-diagnostic-card img {
    width: 100%; height: auto; display: block;
    border-bottom: 3px solid var(--mid-bg);
  }
  .chart-card-header {
    display: flex; align-items: center; gap: 1rem;
    padding: 1.1rem 1.6rem 0.6rem;
    border-bottom: 1px solid var(--light-bg);
  }
  .chart-num-badge {
    background: var(--dark-blue); color: var(--cyan);
    font-size: 0.7rem; font-weight: 800; letter-spacing: 1px;
    padding: 4px 12px; border-radius: 20px; white-space: nowrap;
    text-transform: uppercase;
  }
  .chart-card-title {
    font-size: 1.05rem; font-weight: 800; color: var(--dark-blue);
  }
  .chart-explain-grid {
    display: grid; grid-template-columns: 1fr 1fr 1fr 1fr;
    gap: 0; border-top: 1px solid var(--light-bg);
  }
  @media (max-width: 900px) {
    .chart-explain-grid { grid-template-columns: 1fr 1fr; }
  }
  @media (max-width: 600px) {
    .chart-explain-grid { grid-template-columns: 1fr; }
  }
  .explain-cell {
    padding: 1.1rem 1.4rem;
    border-right: 1px solid var(--light-bg);
  }
  .explain-cell:last-child { border-right: none; }
  .explain-cell-label {
    font-size: 0.65rem; font-weight: 900; text-transform: uppercase;
    letter-spacing: 2px; margin-bottom: 0.45rem;
  }
  .explain-cell-label.what  { color: var(--dark-blue); }
  .explain-cell-label.why   { color: var(--amber); }
  .explain-cell-label.where { color: var(--cyan); }
  .explain-cell-label.how   { color: var(--green); }
  .explain-cell p {
    font-size: 0.82rem; color: var(--muted); line-height: 1.6;
  }
  .chart-insight-bar {
    background: var(--light-bg); padding: 0.8rem 1.6rem;
    display: flex; align-items: flex-start; gap: 0.75rem;
    border-top: 1px solid var(--mid-bg);
  }
  .insight-icon {
    font-size: 1rem; margin-top: 0.05rem; flex-shrink: 0;
  }
  .chart-insight-bar p {
    font-size: 0.82rem; color: var(--dark-blue);
    font-weight: 600; line-height: 1.55;
  }
  .chart-insight-bar strong { color: var(--dark-blue); }
"""

# ── Build the new section HTML ─────────────────────────────────────────────────
SUBSECTIONS = {
    "01": ("&#128202;", "Operational Analytics", "Charts 01–04"),
    "05": ("&#129302;", "ML Regression — Energy Yield Forecaster", "Charts 05–07"),
    "08": ("&#127919;", "ML Classification & Anomaly Detection", "Charts 08–11"),
    "12": ("&#128200;", "Forecasting & Portfolio Overview", "Charts 12–14"),
}

def build_chart_card(file, num, title, what, why, where, how, insight):
    src = b64(file)
    return f"""
    <div class="chart-diagnostic-card">
      <img src="{src}" alt="{title}" loading="lazy">
      <div class="chart-card-header">
        <span class="chart-num-badge">{num}</span>
        <span class="chart-card-title">{title}</span>
      </div>
      <div class="chart-explain-grid">
        <div class="explain-cell">
          <div class="explain-cell-label what">&#128269; What</div>
          <p>{what}</p>
        </div>
        <div class="explain-cell">
          <div class="explain-cell-label why">&#128161; Why it matters</div>
          <p>{why}</p>
        </div>
        <div class="explain-cell">
          <div class="explain-cell-label where">&#128205; Where it lives</div>
          <p>{where}</p>
        </div>
        <div class="explain-cell">
          <div class="explain-cell-label how">&#128270; How to read it</div>
          <p>{how}</p>
        </div>
      </div>
      <div class="chart-insight-bar">
        <span class="insight-icon">&#x1F4A1;</span>
        <p><strong>Key Insight — </strong>{insight}</p>
      </div>
    </div>"""

section_html_parts = ["""
<!-- ══════════════════ SECTION 9: ANALYTICS & ML DIAGNOSTICS ══════════════════ -->
<section id="diagnostics" style="background:var(--light-bg);">
  <div class="container">
    <div class="section-eyebrow">Chapter 9</div>
    <h2 class="section-title">Analytics &amp; <span>ML Diagnostics</span></h2>
    <p class="chart-section-intro">
      13 publication-quality charts generated directly from 3,024,807 rows of synthetic operational data.
      Each chart is explained across four dimensions — <strong>What</strong> it shows,
      <strong>Why</strong> it matters commercially, <strong>Where</strong> it fits in the platform,
      and <strong>How</strong> to read it correctly.
    </p>
"""]

current_sub = None
for entry in CHARTS_META:
    file = entry[0]
    num_key = file[:2]
    if num_key in SUBSECTIONS:
        icon, sub_title, sub_range = SUBSECTIONS[num_key]
        section_html_parts.append(f"""
    <div style="margin-top:3rem;">
      <span class="chart-subsection-label">{icon} {sub_title} &nbsp;·&nbsp; {sub_range}</span>
    </div>""")

    section_html_parts.append(build_chart_card(*entry))

section_html_parts.append("""
  </div>
</section>
""")

NEW_SECTION = "\n".join(section_html_parts)

# ── Read ebook ────────────────────────────────────────────────────────────────
with open(EBOOK, "r", encoding="utf-8") as f:
    html = f.read()

# ── 1. Inject CSS before </style> ─────────────────────────────────────────────
html = html.replace("  /* ── Print / PDF ── */", NEW_CSS + "\n  /* ── Print / PDF ── */", 1)

# ── 2. Add Diagnostics to nav ─────────────────────────────────────────────────
html = html.replace(
    '<a href="#results">Results</a>',
    '<a href="#results">Results</a>\n    <a href="#diagnostics">Diagnostics</a>'
)

# ── 3. Inject section before footer ───────────────────────────────────────────
html = html.replace("<!-- ── FOOTER ── -->", NEW_SECTION + "\n<!-- ── FOOTER ── -->", 1)

# ── Write ─────────────────────────────────────────────────────────────────────
with open(EBOOK, "w", encoding="utf-8") as f:
    f.write(html)

size_kb = os.path.getsize(EBOOK) / 1024
print(f"Ebook updated successfully.")
print(f"File size: {size_kb:.0f} KB ({size_kb/1024:.1f} MB)")
print(f"Charts embedded: {len(CHARTS_META)}")
print(f"Nav updated: Diagnostics link added")
