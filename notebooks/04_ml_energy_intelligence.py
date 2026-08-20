# Databricks notebook source
# MAGIC %md
# MAGIC # Baobab Power Energy Intelligence Platform
# MAGIC ## Notebook 04 — ML: Energy Intelligence Suite
# MAGIC **Purpose:** Train, evaluate and register 5 ML models using MLflow on the Gold feature store.
# MAGIC
# MAGIC | # | Model | Algorithm | Target | Business Value |
# MAGIC |---|---|---|---|---|
# MAGIC | 1 | **Energy Yield Forecaster** | XGBoost Regressor | NetGenerationMWh (t+1 day) | Scheduling & trading |
# MAGIC | 2 | **Forced Outage Predictor** | LightGBM Classifier | ForcedOutage_Next7d | Predictive maintenance |
# MAGIC | 3 | **Maintenance Cost Estimator** | Random Forest Regressor | TotalMaintenanceCostZAR | OPEX budgeting |
# MAGIC | 4 | **Curtailment Anomaly Detector** | Isolation Forest | CurtailmentPct outlier | Grid curtailment alerts |
# MAGIC | 5 | **Portfolio Revenue Forecaster** | LightGBM Regressor | RevenueZAR (t+1 month) | Investor reporting |

# COMMAND ----------
# MAGIC %pip install xgboost lightgbm shap

# COMMAND ----------
import mlflow
import mlflow.sklearn
import mlflow.xgboost
import mlflow.lightgbm

import numpy as np
import pandas as pd
from pyspark.sql import functions as F

from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.preprocessing import LabelEncoder, StandardScaler
from sklearn.ensemble import RandomForestRegressor, IsolationForest
from sklearn.metrics import (mean_absolute_error, mean_squared_error, r2_score,
                              roc_auc_score, classification_report, average_precision_score)
import xgboost as xgb
import lightgbm as lgb
import shap

mlflow.set_registry_uri("databricks")
EXPERIMENT_NAME = "/Users/anthony.apollis@gmail.com/baobab_power_energy_intelligence"
mlflow.set_experiment(EXPERIMENT_NAME)

GOLD_DB = "gold"
SEED    = 42
np.random.seed(SEED)

print("Libraries loaded. MLflow experiment:", EXPERIMENT_NAME)

# COMMAND ----------
# MAGIC %md ### Helper functions

# COMMAND ----------
def rmse(y_true, y_pred):
    return np.sqrt(mean_squared_error(y_true, y_pred))

def log_regression_metrics(y_true, y_pred, prefix=""):
    mae  = mean_absolute_error(y_true, y_pred)
    rms  = rmse(y_true, y_pred)
    r2   = r2_score(y_true, y_pred)
    mape = np.mean(np.abs((y_true - y_pred) / np.maximum(np.abs(y_true), 1))) * 100
    mlflow.log_metrics({f"{prefix}MAE": mae, f"{prefix}RMSE": rms,
                        f"{prefix}R2": r2, f"{prefix}MAPE": mape})
    return {"MAE": mae, "RMSE": rms, "R2": r2, "MAPE": mape}

def print_metrics(name, metrics):
    print(f"\n  [{name}]")
    for k, v in metrics.items():
        print(f"    {k:<12}: {v:.4f}")

# COMMAND ----------
# MAGIC %md ### 1. Load Feature Store

# COMMAND ----------
feat = spark.table(f"{GOLD_DB}.ml_feature_store_daily").toPandas()

# Encode categorical
le_tech   = LabelEncoder()
le_region = LabelEncoder()
feat["Tech_Enc"]   = le_tech.fit_transform(feat["PrimaryTechnology"].fillna("Unknown"))
feat["Region_Enc"] = le_region.fit_transform(feat["Region"].fillna("Unknown"))

feat = feat.dropna(subset=["NetGenerationMWh","AvailabilityPct"])
print(f"Feature store loaded: {len(feat):,} rows, {feat.shape[1]} columns")
print(f"Date range         : {feat['FullDate'].min()} → {feat['FullDate'].max()}")
print(f"Plants             : {feat['PlantKey'].nunique()}")

# COMMAND ----------
# MAGIC %md ---
# MAGIC ## Model 1: Energy Yield Forecaster (XGBoost Regressor)
# MAGIC **Business question:** "Given yesterday's plant performance and weather patterns,
# MAGIC what will tomorrow's net generation be?"

# COMMAND ----------
MODEL1_FEATURES = [
    "PlantKey","Tech_Enc","Region_Enc","NameplateCapacity","Month",
    "AvailabilityPct","CapacityFactorPct","CurtailmentPct",
    "Avail_Lag1","Avail_Lag7","Gen_Lag1","GenMWh_7d","GenMWh_30d",
    "ForcedOut_Lag1","ForcedOut_Lag7","PlannedDowntimeHours","IsRenewable",
]
TARGET1 = "NetGenerationMWh"

df1 = feat[MODEL1_FEATURES + [TARGET1]].dropna()
X1, y1 = df1[MODEL1_FEATURES].values, df1[TARGET1].values
X1_tr, X1_te, y1_tr, y1_te = train_test_split(X1, y1, test_size=0.2, random_state=SEED)

xgb_params = {
    "n_estimators"    : 500,
    "max_depth"       : 6,
    "learning_rate"   : 0.05,
    "subsample"       : 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "reg_alpha"       : 0.1,
    "reg_lambda"      : 1.0,
    "random_state"    : SEED,
    "n_jobs"          : -1,
}

with mlflow.start_run(run_name="energy_yield_xgboost") as run1:
    mlflow.log_params(xgb_params)
    mlflow.log_param("model_version", "1.0")
    mlflow.log_param("target", TARGET1)
    mlflow.log_param("features", MODEL1_FEATURES)

    model1 = xgb.XGBRegressor(**xgb_params)
    model1.fit(X1_tr, y1_tr,
               eval_set=[(X1_te, y1_te)],
               verbose=100)

    y1_pred = model1.predict(X1_te)
    metrics1 = log_regression_metrics(y1_te, y1_pred)
    print_metrics("Energy Yield Forecaster — XGBoost", metrics1)

    # Feature importance
    fi1 = pd.Series(model1.feature_importances_, index=MODEL1_FEATURES).sort_values(ascending=False)
    mlflow.log_text(fi1.to_string(), "feature_importance.txt")

    # SHAP values (sample 500 for speed)
    explainer1  = shap.TreeExplainer(model1)
    shap_vals1  = explainer1.shap_values(X1_te[:500])
    shap.summary_plot(shap_vals1, X1_te[:500], feature_names=MODEL1_FEATURES, show=False)
    import matplotlib.pyplot as plt
    plt.tight_layout()
    plt.savefig("/tmp/shap_model1.png", dpi=100, bbox_inches="tight")
    mlflow.log_artifact("/tmp/shap_model1.png")
    plt.close()

    mlflow.xgboost.log_model(model1, "model",
        registered_model_name="baobab_power_energy_yield_forecaster")

    print(f"\n  Run ID: {run1.info.run_id}")

# COMMAND ----------
# MAGIC %md ---
# MAGIC ## Model 2: Forced Outage Predictor (LightGBM Classifier)
# MAGIC **Business question:** "What is the probability of a forced outage in the
# MAGIC next 7 days so we can dispatch maintenance proactively?"

# COMMAND ----------
MODEL2_FEATURES = [
    "PlantKey","Tech_Enc","Region_Enc","NameplateCapacity","Month",
    "AvailabilityPct","CapacityFactorPct","CurtailmentPct",
    "ForcedDowntimeHours","PlannedDowntimeHours",
    "Avail_Lag1","Avail_Lag7","Gen_Lag1",
    "ForcedOut_Lag1","ForcedOut_Lag7",
    "AvailabilityPct_7d","AvailabilityPct_30d","IsRenewable",
]
TARGET2 = "ForcedOutage_Next7d"

df2 = feat[MODEL2_FEATURES + [TARGET2]].dropna()
X2, y2 = df2[MODEL2_FEATURES].values, df2[TARGET2].values
X2_tr, X2_te, y2_tr, y2_te = train_test_split(X2, y2, test_size=0.2,
                                               stratify=y2, random_state=SEED)

pos_rate = y2.mean()
scale_pos = (1 - pos_rate) / max(pos_rate, 0.001)

lgb_params = {
    "n_estimators"    : 600,
    "max_depth"       : 5,
    "learning_rate"   : 0.03,
    "num_leaves"      : 31,
    "min_child_samples": 30,
    "subsample"       : 0.8,
    "colsample_bytree": 0.8,
    "scale_pos_weight": scale_pos,
    "class_weight"    : "balanced",
    "random_state"    : SEED,
    "n_jobs"          : -1,
    "verbose"         : -1,
}

with mlflow.start_run(run_name="forced_outage_lgbm_classifier") as run2:
    mlflow.log_params(lgb_params)
    mlflow.log_param("target", TARGET2)
    mlflow.log_param("class_balance", f"pos_rate={pos_rate:.3f}, scale={scale_pos:.2f}")

    model2 = lgb.LGBMClassifier(**lgb_params)
    model2.fit(X2_tr, y2_tr,
               eval_set=[(X2_te, y2_te)],
               callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(100)])

    y2_prob = model2.predict_proba(X2_te)[:, 1]
    y2_pred = (y2_prob >= 0.35).astype(int)  # Optimised threshold for recall

    auc  = roc_auc_score(y2_te, y2_prob)
    ap   = average_precision_score(y2_te, y2_prob)
    mlflow.log_metrics({"AUC_ROC": auc, "AveragePrecision": ap})

    clf_report = classification_report(y2_te, y2_pred, output_dict=True)
    mlflow.log_metric("F1_Positive",  clf_report.get("1", clf_report.get("1.0",{})).get("f1-score", 0))
    mlflow.log_metric("Precision_Pos",clf_report.get("1", clf_report.get("1.0",{})).get("precision", 0))
    mlflow.log_metric("Recall_Pos",   clf_report.get("1", clf_report.get("1.0",{})).get("recall", 0))

    fi2 = pd.Series(model2.feature_importances_, index=MODEL2_FEATURES).sort_values(ascending=False)
    mlflow.log_text(fi2.to_string(), "feature_importance.txt")

    print(f"\n  [Forced Outage Predictor — LightGBM]")
    print(f"    AUC-ROC          : {auc:.4f}")
    print(f"    Average Precision: {ap:.4f}")
    print(f"    Class report:\n{classification_report(y2_te, y2_pred)}")

    mlflow.lightgbm.log_model(model2, "model",
        registered_model_name="baobab_power_forced_outage_predictor")

# COMMAND ----------
# MAGIC %md ---
# MAGIC ## Model 3: Maintenance Cost Estimator (Random Forest Regressor)
# MAGIC **Business question:** "Given plant characteristics and recent operational history,
# MAGIC what will this month's maintenance cost be?"

# COMMAND ----------
monthly = spark.table(f"{GOLD_DB}.plant_monthly_kpis").toPandas()
monthly["Tech_Enc"]   = le_tech.transform(
    monthly["PrimaryTechnology"].map(
        lambda x: x if x in le_tech.classes_ else le_tech.classes_[0]))
monthly["Region_Enc"] = le_region.transform(
    monthly["Region"].map(
        lambda x: x if x in le_region.classes_ else le_region.classes_[0]))

MODEL3_FEATURES = [
    "PlantKey","Tech_Enc","Region_Enc","NameplateCapacity",
    "Month","Year","AvailabilityPct","CapacityFactorPct",
    "CurtailmentPct","ForcedOutageCount","TotalOutageHours",
    "NetGenMWh","PlannedDowntimeHours","IsRenewable",
]
TARGET3 = "MaintenanceCostZAR"

df3 = monthly[MODEL3_FEATURES + [TARGET3]].dropna()
df3 = df3[df3[TARGET3] > 0]
X3, y3 = df3[MODEL3_FEATURES].values, df3[TARGET3].values
X3_tr, X3_te, y3_tr, y3_te = train_test_split(X3, y3, test_size=0.2, random_state=SEED)

rf_params = {
    "n_estimators"     : 400,
    "max_depth"        : 12,
    "min_samples_leaf" : 5,
    "max_features"     : "sqrt",
    "random_state"     : SEED,
    "n_jobs"           : -1,
}

with mlflow.start_run(run_name="maintenance_cost_rf") as run3:
    mlflow.log_params(rf_params)
    mlflow.log_param("target", TARGET3)

    model3 = RandomForestRegressor(**rf_params)
    model3.fit(X3_tr, y3_tr)
    y3_pred = model3.predict(X3_te)

    metrics3 = log_regression_metrics(y3_te, y3_pred)
    print_metrics("Maintenance Cost Estimator — Random Forest", metrics3)

    fi3 = pd.Series(model3.feature_importances_, index=MODEL3_FEATURES).sort_values(ascending=False)
    mlflow.log_text(fi3.to_string(), "feature_importance.txt")

    # OOB score
    model3_oob = RandomForestRegressor(**{**rf_params, "oob_score": True})
    model3_oob.fit(X3_tr, y3_tr)
    mlflow.log_metric("OOB_R2", model3_oob.oob_score_)
    print(f"    OOB R² : {model3_oob.oob_score_:.4f}")

    mlflow.sklearn.log_model(model3, "model",
        registered_model_name="baobab_power_maintenance_cost_estimator")

# COMMAND ----------
# MAGIC %md ---
# MAGIC ## Model 4: Curtailment Anomaly Detector (Isolation Forest)
# MAGIC **Business question:** "Which plants are experiencing unusual curtailment
# MAGIC patterns that may indicate grid congestion or inverter faults?"

# COMMAND ----------
MODEL4_FEATURES = [
    "AvailabilityPct","CapacityFactorPct","CurtailmentPct",
    "NetGenMWh","ForcedDowntimeHours","TotalOutageHours",
    "Tech_Enc","Month","NameplateCapacity",
]

df4 = monthly[MODEL4_FEATURES + ["PlantKey","PlantCode","YearMonth","PrimaryTechnology"]].dropna()
X4  = df4[MODEL4_FEATURES].values

iso_params = {
    "n_estimators"    : 200,
    "contamination"   : 0.05,  # expect ~5% anomalous months
    "max_features"    : 1.0,
    "random_state"    : SEED,
}

with mlflow.start_run(run_name="curtailment_anomaly_isolation_forest") as run4:
    mlflow.log_params(iso_params)
    mlflow.log_param("target", "anomaly_score")

    scaler4  = StandardScaler()
    X4_scaled = scaler4.fit_transform(X4)

    model4 = IsolationForest(**iso_params)
    model4.fit(X4_scaled)

    scores4   = model4.decision_function(X4_scaled)  # higher = more normal
    labels4   = model4.predict(X4_scaled)              # -1 = anomaly, +1 = normal

    anomaly_rate = (labels4 == -1).mean()
    mlflow.log_metric("AnomalyRate", anomaly_rate)

    df4_out = df4.copy()
    df4_out["AnomalyScore"]  = scores4
    df4_out["IsAnomaly"]     = (labels4 == -1).astype(int)
    anomalies = df4_out[df4_out["IsAnomaly"] == 1].sort_values("AnomalyScore")

    print(f"\n  [Curtailment Anomaly Detector — Isolation Forest]")
    print(f"    Anomaly rate: {anomaly_rate:.3f} ({(labels4==-1).sum()} anomalous plant-months)")
    print(f"\n  Top anomalous plant-months:")
    print(anomalies[["PlantCode","YearMonth","CurtailmentPct","CapacityFactorPct","AnomalyScore"]].head(10).to_string())

    mlflow.log_text(
        anomalies[["PlantCode","YearMonth","CurtailmentPct","AnomalyScore"]].head(20).to_string(),
        "top_anomalies.txt"
    )
    # Save anomaly output to Gold
    spark.createDataFrame(df4_out).write.format("delta").mode("overwrite") \
        .option("overwriteSchema","true").saveAsTable("gold.curtailment_anomaly_scores")

    mlflow.sklearn.log_model(
        {"isolation_forest": model4, "scaler": scaler4}, "model",
        registered_model_name="baobab_power_curtailment_anomaly_detector"
    )

# COMMAND ----------
# MAGIC %md ---
# MAGIC ## Model 5: Portfolio Revenue Forecaster (LightGBM Regressor)
# MAGIC **Business question:** "Forecast next month's portfolio revenue for
# MAGIC investor reporting and cash-flow planning."

# COMMAND ----------
rev = spark.table(f"{GOLD_DB}.revenue_by_region_month").toPandas()

# Aggregate to portfolio level
port_rev = (monthly.groupby(["YearMonth","Year","Month"])
            .agg(
                TotalRevenueZAR   = ("RevenueZAR",       "sum"),
                TotalNetGenMWh    = ("NetGenMWh",         "sum"),
                TotalMaintCost    = ("MaintenanceCostZAR","sum"),
                AvgAvailability   = ("AvailabilityPct",   "mean"),
                TotalForcedOutages= ("ForcedOutageCount", "sum"),
            ).reset_index()
            .sort_values(["Year","Month"]))

# Lag features
port_rev["Rev_Lag1"]   = port_rev["TotalRevenueZAR"].shift(1)
port_rev["Rev_Lag3"]   = port_rev["TotalRevenueZAR"].shift(3)
port_rev["Rev_Lag12"]  = port_rev["TotalRevenueZAR"].shift(12)
port_rev["Gen_Lag1"]   = port_rev["TotalNetGenMWh"].shift(1)
port_rev["Avail_Lag1"] = port_rev["AvgAvailability"].shift(1)
port_rev["Target"]     = port_rev["TotalRevenueZAR"].shift(-1)  # next month

MODEL5_FEATURES = [
    "Month","Year","TotalNetGenMWh","TotalMaintCost","AvgAvailability",
    "TotalForcedOutages","Rev_Lag1","Rev_Lag3","Rev_Lag12","Gen_Lag1","Avail_Lag1",
]

df5 = port_rev[MODEL5_FEATURES + ["Target"]].dropna()
X5, y5 = df5[MODEL5_FEATURES].values, df5["Target"].values
split_idx = int(len(X5) * 0.8)
X5_tr, X5_te = X5[:split_idx], X5[split_idx:]
y5_tr, y5_te = y5[:split_idx], y5[split_idx:]

lgb5_params = {
    "n_estimators"  : 300,
    "max_depth"     : 4,
    "learning_rate" : 0.05,
    "num_leaves"    : 15,
    "min_child_samples": 5,
    "subsample"     : 0.9,
    "random_state"  : SEED,
    "verbose"       : -1,
}

with mlflow.start_run(run_name="portfolio_revenue_lgbm_regressor") as run5:
    mlflow.log_params(lgb5_params)
    mlflow.log_param("target", "TotalRevenueZAR_NextMonth")
    mlflow.log_param("train_months", split_idx)
    mlflow.log_param("test_months",  len(X5_te))

    model5 = lgb.LGBMRegressor(**lgb5_params)
    model5.fit(X5_tr, y5_tr, eval_set=[(X5_te, y5_te)],
               callbacks=[lgb.early_stopping(30, verbose=False), lgb.log_evaluation(50)])

    y5_pred = model5.predict(X5_te)
    metrics5 = log_regression_metrics(y5_te, y5_pred)
    print_metrics("Portfolio Revenue Forecaster — LightGBM", metrics5)

    fi5 = pd.Series(model5.feature_importances_, index=MODEL5_FEATURES).sort_values(ascending=False)
    print(f"\n  Top features:\n{fi5.head(6).to_string()}")
    mlflow.log_text(fi5.to_string(), "feature_importance.txt")

    # Next-month forecast
    latest = df5.iloc[[-1]].copy()
    next_month_rev = model5.predict(latest[MODEL5_FEATURES].values)[0]
    mlflow.log_metric("NextMonthRevForecast_ZAR", next_month_rev)
    print(f"\n  Next-month portfolio revenue forecast: R{next_month_rev:,.0f}")

    mlflow.lightgbm.log_model(model5, "model",
        registered_model_name="baobab_power_portfolio_revenue_forecaster")

# COMMAND ----------
# MAGIC %md ### Summary: All 5 Models Registered

# COMMAND ----------
print("\n" + "="*65)
print("BAOBAB POWER ML MODEL REGISTRY SUMMARY")
print("="*65)
models_summary = [
    ("Energy Yield Forecaster",     "XGBoost Regressor",    f"MAE={metrics1['MAE']:.1f} MWh  R²={metrics1['R2']:.4f}"),
    ("Forced Outage Predictor",     "LightGBM Classifier",  f"AUC={auc:.4f}  AP={ap:.4f}"),
    ("Maintenance Cost Estimator",  "Random Forest",        f"MAE=R{metrics3['MAE']:,.0f}  R²={metrics3['R2']:.4f}"),
    ("Curtailment Anomaly Detector","Isolation Forest",     f"Anomaly rate={anomaly_rate:.3f}"),
    ("Portfolio Revenue Forecaster","LightGBM Regressor",   f"MAE=R{metrics5['MAE']:,.0f}  R²={metrics5['R2']:.4f}"),
]
for i, (name, algo, metric) in enumerate(models_summary, 1):
    print(f"\n  {i}. {name}")
    print(f"     Algorithm : {algo}")
    print(f"     Metrics   : {metric}")
print("\n" + "="*65)

dbutils.notebook.exit({
    "model1_r2" : metrics1["R2"],
    "model2_auc": auc,
    "model3_r2" : metrics3["R2"],
    "model5_r2" : metrics5["R2"],
    "status"    : "SUCCESS"
})
