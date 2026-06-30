"""
Model 9 — Solar Irradiance Yield Forecaster
LightGBM regressor predicting next-day solar generation (MWh)
Features: seasonality, lag, rolling averages, plant capacity, region
"""

import sys, warnings
sys.stdout.reconfigure(encoding='utf-8')
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
import lightgbm as lgb

# ── 1. Load data ──────────────────────────────────────────────────────────────
SOLAR_PLANT_KEYS = {1, 2, 4, 5, 6, 8, 11, 13, 14, 16, 17}

ops = pd.read_csv('data/generated/fact_plant_operations_daily_5yr.csv')
plants = pd.read_csv('data/raw/dim_plant.csv')
plants.columns = [c.lstrip('﻿') for c in plants.columns]

# Filter solar plants
solar_ops = ops[ops['PlantKey'].isin(SOLAR_PLANT_KEYS)].copy()
solar_plants = plants[plants['PlantKey'].isin(SOLAR_PLANT_KEYS)][
    ['PlantKey', 'PlantName', 'Country', 'Region', 'NameplateCapacity']
].copy()
solar_plants['NameplateCapacity'] = pd.to_numeric(solar_plants['NameplateCapacity'])

df = solar_ops.merge(solar_plants, on='PlantKey', how='left')

# ── 2. Parse dates + sort ─────────────────────────────────────────────────────
df['Date'] = pd.to_datetime(df['DateKey'].astype(str), format='%Y%m%d')
df = df.sort_values(['PlantKey', 'Date']).reset_index(drop=True)
df['GrossGenerationMWh'] = pd.to_numeric(df['GrossGenerationMWh'])
df['AvailabilityPct']    = pd.to_numeric(df['AvailabilityPct'])

# ── 3. Feature engineering ────────────────────────────────────────────────────
df['month']       = df['Date'].dt.month
df['day_of_year'] = df['Date'].dt.dayofyear
df['day_of_week'] = df['Date'].dt.dayofweek

# Cyclical encoding of seasonality
df['sin_doy'] = np.sin(2 * np.pi * df['day_of_year'] / 365)
df['cos_doy'] = np.cos(2 * np.pi * df['day_of_year'] / 365)
df['sin_month'] = np.sin(2 * np.pi * df['month'] / 12)
df['cos_month'] = np.cos(2 * np.pi * df['month'] / 12)

# Normalised generation (MWh per MWp) — removes plant-size bias
df['yield_per_mwp'] = df['GrossGenerationMWh'] / df['NameplateCapacity']

# Lag features (per plant)
for lag in [1, 2, 7, 14]:
    df[f'lag_{lag}'] = df.groupby('PlantKey')['yield_per_mwp'].shift(lag)

# Rolling averages (per plant)
for window in [7, 30]:
    df[f'roll_{window}d'] = (
        df.groupby('PlantKey')['yield_per_mwp']
          .transform(lambda x: x.shift(1).rolling(window, min_periods=3).mean())
    )

# Region encoding
region_map = {r: i for i, r in enumerate(df['Region'].unique())}
df['region_enc'] = df['Region'].map(region_map)

# ── 4. Target: next-day gross generation ─────────────────────────────────────
df['target'] = df.groupby('PlantKey')['GrossGenerationMWh'].shift(-1)
df = df.dropna(subset=['target', 'lag_1', 'lag_7', 'roll_7d', 'roll_30d'])

FEATURES = [
    'NameplateCapacity', 'region_enc', 'PlantKey',
    'month', 'day_of_year', 'day_of_week',
    'sin_doy', 'cos_doy', 'sin_month', 'cos_month',
    'AvailabilityPct',
    'lag_1', 'lag_2', 'lag_7', 'lag_14',
    'roll_7d', 'roll_30d',
    'yield_per_mwp',
]

X = df[FEATURES]
y = df['target']

# ── 5. Temporal train/test split (80/20 by date) ─────────────────────────────
split_date = df['Date'].quantile(0.80)
train_mask = df['Date'] <= split_date
X_train, X_test = X[train_mask], X[~train_mask]
y_train, y_test = y[train_mask], y[~train_mask]

print(f"Train rows : {len(X_train):,}  ({X_train['Date'].min() if 'Date' in X_train else ''} )")
print(f"Test rows  : {len(X_test):,}")

# ── 6. Train LightGBM regressor ──────────────────────────────────────────────
params = {
    'objective':        'regression',
    'metric':           'rmse',
    'learning_rate':    0.05,
    'num_leaves':       63,
    'min_child_samples': 20,
    'feature_fraction': 0.8,
    'bagging_fraction': 0.8,
    'bagging_freq':     5,
    'lambda_l1':        0.1,
    'lambda_l2':        0.1,
    'n_estimators':     500,
    'random_state':     42,
    'verbose':          -1,
}

model = lgb.LGBMRegressor(**params)
model.fit(
    X_train, y_train,
    eval_set=[(X_test, y_test)],
    callbacks=[lgb.early_stopping(50, verbose=False), lgb.log_evaluation(period=-1)],
)

# ── 7. Evaluate ───────────────────────────────────────────────────────────────
y_pred = model.predict(X_test)
y_pred = np.clip(y_pred, 0, None)   # generation can't be negative

r2   = r2_score(y_test, y_pred)
mae  = mean_absolute_error(y_test, y_pred)
rmse = np.sqrt(np.mean((y_test - y_pred) ** 2))

mask = y_test > 1
mape = np.mean(np.abs((y_test[mask] - y_pred[mask]) / y_test[mask])) * 100

print("\n=== Model 9: Solar Irradiance Yield Forecaster ===")
print(f"  R²    : {r2:.4f}")
print(f"  MAE   : {mae:.1f} MWh/day")
print(f"  RMSE  : {rmse:.1f} MWh/day")
print(f"  MAPE  : {mape:.1f}%")
print(f"  Trees : {model.best_iteration_}")

# ── 8. Feature importance (top 10) ───────────────────────────────────────────
fi = pd.Series(model.feature_importances_, index=FEATURES).sort_values(ascending=False)
print("\nTop 10 features:")
for feat, imp in fi.head(10).items():
    print(f"  {feat:<22} {imp:>6.0f}")

# ── 9. Per-plant accuracy summary ────────────────────────────────────────────
test_df = df[~train_mask].copy()
test_df['pred'] = y_pred
print("\nPer-plant MAPE:")
for pk, grp in test_df.groupby('PlantKey'):
    name = solar_plants.loc[solar_plants['PlantKey']==pk, 'PlantName'].values[0]
    g = grp[grp['target'] > 1]
    if len(g):
        pm = np.mean(np.abs((g['target'] - g['pred']) / g['target'])) * 100
        print(f"  {name:<30} MAPE={pm:.1f}%")

# ── 10. Save model ────────────────────────────────────────────────────────────
import os, joblib
os.makedirs('models', exist_ok=True)
joblib.dump(model, 'models/solar_yield_forecaster_lgbm.pkl')
print("\nModel saved to models/solar_yield_forecaster_lgbm.pkl")
print(f"\n[SUMMARY] R²={r2:.3f} | MAE={mae:.1f} MWh | RMSE={rmse:.1f} MWh | MAPE={mape:.1f}%")
