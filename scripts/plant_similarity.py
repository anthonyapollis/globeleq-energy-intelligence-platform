"""Content-based "similar plants" recommender for the Aquila Energy
Intelligence Platform.

There's no "customer purchase history" concept in a power-plant portfolio
- the natural equivalent of "customers who bought X also bought Y" here
is operational risk triage: if one plant's availability or capacity
factor moves, which plants have a similar profile (technology, size,
region) and might be worth a second look too. Built from real dim_plant
attributes (technology, nameplate capacity, region) joined with real
aggregated daily operations (avg availability %, avg capacity factor %)
from fact_plant_operations_daily.csv - not fabricated.
"""
import json
import os

import numpy as np
import pandas as pd
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.preprocessing import StandardScaler

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "data", "raw")
OUT_DIR = os.path.join(BASE, "data", "processed")
TOP_K = 3


def main():
    plants = pd.read_csv(os.path.join(RAW, "dim_plant.csv"), encoding="utf-8-sig")
    ops = pd.read_csv(os.path.join(RAW, "fact_plant_operations_daily.csv"), encoding="utf-8-sig")

    ops_agg = ops.groupby("PlantKey").agg(
        avg_availability_pct=("AvailabilityPct", "mean"),
        avg_capacity_factor_pct=("CapacityFactorPct", "mean"),
        days_of_data=("DateKey", "count"),
    ).reset_index()

    df = plants.merge(ops_agg, on="PlantKey", how="left")
    # plants under construction have no operations data yet - keep them in the
    # catalogue (visible in the UI) but exclude from similarity scoring, since
    # 0-filling their availability/capacity-factor would fabricate a signal
    scored = df.dropna(subset=["avg_availability_pct", "avg_capacity_factor_pct"]).reset_index(drop=True)
    print(f"{len(df)} plants total, {len(scored)} with operations data to score "
          f"({len(df) - len(scored)} under construction, excluded from scoring)")

    num_features = scored[["NameplateCapacity", "avg_availability_pct", "avg_capacity_factor_pct"]].to_numpy()
    num_features = StandardScaler().fit_transform(num_features)
    tech_oh = pd.get_dummies(scored["PrimaryTechnology"], prefix="tech").to_numpy()
    region_oh = pd.get_dummies(scored["Region"], prefix="region").to_numpy()
    X = np.hstack([num_features * 1.5, tech_oh, region_oh])

    sim = cosine_similarity(X)
    np.fill_diagonal(sim, -1)

    results = []
    for i, row in scored.iterrows():
        top = np.argsort(-sim[i])[:TOP_K]
        results.append({
            "code": row["PlantCode"],
            "name": row["PlantName"],
            "country": row["Country"],
            "technology": row["PrimaryTechnology"],
            "capacity_mw": float(row["NameplateCapacity"]),
            "avg_availability_pct": round(float(row["avg_availability_pct"]), 1),
            "avg_capacity_factor_pct": round(float(row["avg_capacity_factor_pct"]), 1),
            "similar": [
                {"code": scored.loc[j, "PlantCode"], "name": scored.loc[j, "PlantName"],
                 "similarity": round(float(sim[i, j]), 3),
                 "avg_availability_pct": round(float(scored.loc[j, "avg_availability_pct"]), 1)}
                for j in top
            ],
        })

    same_tech = sum(
        1 for i, row in scored.iterrows()
        if scored.loc[int(np.argsort(-sim[i])[0]), "PrimaryTechnology"] == row["PrimaryTechnology"]
    )
    metrics = {
        "model": "Content-based nearest-neighbour similarity (cosine) over real plant attributes + real ops data",
        "plants_total": len(df),
        "plants_scored": len(scored),
        "plants_under_construction_excluded": len(df) - len(scored),
        "features": ["NameplateCapacity", "avg_availability_pct", "avg_capacity_factor_pct",
                     "PrimaryTechnology (one-hot)", "Region (one-hot)"],
        "diagnostic_nearest_neighbour_same_technology_pct": round(100 * same_tech / len(scored), 1),
        "note": "19 plants is too few for a held-out accuracy claim - this is a similarity tool for "
                "operational risk triage (\"which plants look like this one\"), not a validated prediction.",
    }
    print(json.dumps(metrics, indent=2))

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "plant_similarity.json"), "w") as f:
        json.dump({"metrics": metrics, "plants": results}, f, indent=2)
    print(f"wrote {os.path.join(OUT_DIR, 'plant_similarity.json')}")


if __name__ == "__main__":
    main()
