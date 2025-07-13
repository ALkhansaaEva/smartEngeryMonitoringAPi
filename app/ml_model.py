import os
import json
import warnings
import pandas as pd
import joblib
from pathlib import Path
from typing import Any, Dict
warnings.filterwarnings("ignore", category=UserWarning, message="Model file.*not found.*")
warnings.filterwarnings("ignore", category=UserWarning, message="Thresholds file.*not found.*")
# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
MODELS_DIR  = Path(os.getenv("ML_MODELS_DIR", BASE_DIR / "ml_models"))
THRESH_FILE = Path(os.getenv("THRESHOLDS_FILE", BASE_DIR / "thresholds.json"))

# ── Constants ──────────────────────────────────────────────────────────────────
APPLIANCE_COLS = [f"Appliance{i}" for i in range(1, 10)]
FEATURE_BASE   = ["Aggregate", "dayofweek", "is_weekend"]

# ── Load thresholds ────────────────────────────────────────────────────────────
if THRESH_FILE.exists():
    with open(THRESH_FILE, "r") as f:
        THRESHOLDS = json.load(f)
else:
    warnings.warn(f"Thresholds file '{THRESH_FILE.name}' not found. Using 1000W default.")
    THRESHOLDS = {appl: 1000 for appl in APPLIANCE_COLS}

# ── Load models ────────────────────────────────────────────────────────────────
MODELS: Dict[str, Any] = {}
for appl in APPLIANCE_COLS:
    path = MODELS_DIR / f"{appl}_pipeline.joblib"
    if path.exists():
        MODELS[appl] = joblib.load(path)
    else:
        warnings.warn(f"Model file '{path.name}' not found. Appliance '{appl}' will use threshold-only fallback.")
        MODELS[appl] = None

def clean_and_engineer(df: pd.DataFrame) -> pd.DataFrame:
    # Convert timestamp or Time column
    if "timestamp" in df.columns:
        df["Time"] = pd.to_datetime(df.pop("timestamp"))
    else:
        df["Time"] = pd.to_datetime(df["Time"])
    # Drop Unix if present
    df = df.drop(columns=[c for c in ("Unix",) if c in df], errors="ignore")

    # Day-of-week and weekend flag
    df["dayofweek"]  = df["Time"].dt.dayofweek
    df["is_weekend"] = df["dayofweek"] >= 5

    # Roll features: mean = current value, std = 0
    for appl in APPLIANCE_COLS:
        df[f"{appl}_roll_mean"] = df[appl]
        df[f"{appl}_roll_std"]  = 0.0

    return df

def predict_actions(data: Dict[str, Any]) -> Dict[str, str]:
    """
    Predict ON/OFF for each appliance channel given a single reading dict.

    data must include:
      - 'timestamp' (ISO string) or 'Time' (datetime)
      - 'Aggregate': float
      - Any subset of 'Appliance1'..'Appliance9'.

    Missing appliance keys default to 0.0.
    """
    # ── Ensure every channel is present (missing → 0.0) ──────────────────────────
    for appl in APPLIANCE_COLS:
        data.setdefault(appl, 0.0)

    # 1) Build DataFrame
    df = pd.DataFrame([data])

    # 2) Clean & feature-engineer
    df_feat = clean_and_engineer(df)

    # 3) Predict for each appliance
    actions: Dict[str, str] = {}
    for appl in APPLIANCE_COLS:
        model = MODELS.get(appl)
        X = df_feat[FEATURE_BASE + [f"{appl}_roll_mean", f"{appl}_roll_std"]]

        if model:
            try:
                pred = model.predict(X)[0]
            except Exception as e:
                warnings.warn(f"Error in model for {appl}: {e} – using threshold fallback")
                val  = float(data.get(appl, 0.0))
                pred = 1 if val > THRESHOLDS[appl] else 0
        else:
            # threshold-only fallback
            val  = float(data.get(appl, 0.0))
            pred = 1 if val > THRESHOLDS[appl] else 0

        actions[appl] = "OFF" if pred == 1 else "ON"

    return actions