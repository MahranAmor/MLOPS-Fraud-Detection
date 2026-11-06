"""
Test de scénario métier : 11 fraudes réelles du jeu de TEST (jamais vues à l'entraînement).

C'est une quality gate du pipeline Jenkins : le test échoue si le modèle détecte
moins de MIN_DETECTED fraudes (défaut 9 sur 11, soit un rappel minimal de 82 %).

Il applique la même règle de décision que l'API (api.resolve_threshold) :
FRAUD_THRESHOLD si défini, sinon le seuil de metadata.json, sinon 0,5.

Résultat écrit dans artifacts/jenkins/scenario_test.json ; jenkins/push_metrics.py
le pousse ensuite vers le Pushgateway (et non vers l'API : ces chiffres de CI ne
doivent pas se mélanger aux métriques du trafic réel).

    python test/test_fraud_scenario.py        # Jenkins : code 1 si la gate échoue
    pytest test/test_fraud_scenario.py        # ignoré si le modèle n'a pas été récupéré
"""
import json
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from api import InferencePreprocessor, resolve_threshold  # noqa: E402

MODEL_DIR = ROOT / "artifacts" / "mlflow" / "Best_Fraud_LightGBM"
MODEL_PATH = MODEL_DIR / "production.pkl"
METADATA_PATH = MODEL_DIR / "1.0.0" / "metadata.json"
RESULT_PATH = ROOT / "artifacts" / "jenkins" / "scenario_test.json"
MIN_DETECTED = int(os.getenv("MIN_DETECTED", "9"))

FRAUDS = [
    {'trans_date_trans_time': '2019-08-18 22:10:52', 'category': 'travel', 'amt': 11.39, 'gender': 'M', 'lat': 27.9611, 'long': -81.9398, 'dob': '1961-09-28', 'merch_lat': 27.400606, 'merch_long': -82.452533, 'zip': 0},
    {'trans_date_trans_time': '2019-02-07 17:44:29', 'category': 'home', 'amt': 392.42, 'gender': 'F', 'lat': 36.7558, 'long': -83.1838, 'dob': '1967-02-04', 'merch_lat': 35.93273, 'merch_long': -83.199834, 'zip': 0},
    {'trans_date_trans_time': '2019-05-27 00:05:59', 'category': 'gas_transport', 'amt': 8.29, 'gender': 'M', 'lat': 38.4921, 'long': -85.4524, 'dob': '1996-04-10', 'merch_lat': 38.028499, 'merch_long': -86.211533, 'zip': 0},
    {'trans_date_trans_time': '2019-04-29 00:59:29', 'category': 'grocery_pos', 'amt': 298.19, 'gender': 'F', 'lat': 39.8127, 'long': -120.6405, 'dob': '1967-05-27', 'merch_lat': 40.387359, 'merch_long': -120.874787, 'zip': 0},
    {'trans_date_trans_time': '2019-02-25 02:20:08', 'category': 'gas_transport', 'amt': 14.02, 'gender': 'F', 'lat': 40.9086, 'long': -73.8221, 'dob': '1937-04-16', 'merch_lat': 40.31936, 'merch_long': -74.24485899999999, 'zip': 0},
    {'trans_date_trans_time': '2019-02-04 22:16:37', 'category': 'grocery_pos', 'amt': 290.79, 'gender': 'M', 'lat': 34.5444, 'long': -102.1069, 'dob': '1980-07-30', 'merch_lat': 34.67073, 'merch_long': -102.423796, 'zip': 0},
    {'trans_date_trans_time': '2019-04-08 22:33:43', 'category': 'misc_net', 'amt': 818.46, 'gender': 'M', 'lat': 42.4999, 'long': -74.6117, 'dob': '1968-07-01', 'merch_lat': 42.655614, 'merch_long': -75.44143100000001, 'zip': 0},
    {'trans_date_trans_time': '2019-02-08 09:13:24', 'category': 'grocery_pos', 'amt': 299.18, 'gender': 'M', 'lat': 46.4959, 'long': -90.4383, 'dob': '1986-04-15', 'merch_lat': 47.276442, 'merch_long': -89.828935, 'zip': 0},
    {'trans_date_trans_time': '2019-05-06 22:33:13', 'category': 'kids_pets', 'amt': 21.68, 'gender': 'F', 'lat': 39.6251, 'long': -82.7552, 'dob': '1992-10-03', 'merch_lat': 39.663598, 'merch_long': -82.98897099999999, 'zip': 0},
    {'trans_date_trans_time': '2019-06-23 02:58:24', 'category': 'misc_net', 'amt': 752.39, 'gender': 'F', 'lat': 41.1573, 'long': -88.0619, 'dob': '1990-04-25', 'merch_lat': 41.679054, 'merch_long': -88.486789, 'zip': 0},
    {'trans_date_trans_time': '2019-04-17 22:00:30', 'category': 'shopping_net', 'amt': 993.93, 'gender': 'M', 'lat': 26.9379, 'long': -82.2388, 'dob': '1984-08-31', 'merch_lat': 26.78667, 'merch_long': -81.7518, 'zip': 0},
]


def run_scenario(min_detected=MIN_DETECTED):
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Modèle introuvable : {MODEL_PATH} (register_best_model.py ou dvc pull)")
    with open(MODEL_PATH, "rb") as f:
        model = pickle.load(f)
    metadata = json.loads(METADATA_PATH.read_text()) if METADATA_PATH.exists() else {}
    threshold = resolve_threshold(metadata)
    preprocessor = InferencePreprocessor()
    print(f"🎚️  Seuil de décision : {threshold:.3f} | quality gate : {min_detected}/{len(FRAUDS)}\n")

    X = preprocessor.preprocess_inference(pd.DataFrame(FRAUDS))
    if hasattr(model, "predict_proba"):
        proba = np.asarray(model.predict_proba(X))[:, 1]
        preds = (proba >= threshold).astype(int)
    else:
        proba, preds = None, np.asarray(model.predict(X)).astype(int)

    for i, pred in enumerate(preds, 1):
        p = "N/A" if proba is None else f"{proba[i - 1]:.4f}"
        print(f"Fraude {i:>2} : {'✅ DÉTECTÉE' if pred == 1 else '❌ RATÉE'} | proba={p}")

    detected = int(preds.sum())
    result = {"detected": detected, "total": len(FRAUDS), "detection_rate": detected / len(FRAUDS),
              "threshold": threshold, "min_detected": min_detected, "passed": detected >= min_detected}
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(result, indent=2))
    print(f"\n📊 {detected}/{len(FRAUDS)} fraudes détectées ({result['detection_rate']:.1%})")
    return result


def test_specific_fraud_case():
    import pytest
    if not MODEL_PATH.exists():
        pytest.skip("modèle absent : lancez `dvc pull artifacts/` pour ce test d'intégration")
    result = run_scenario()
    assert result["detected"] >= result["min_detected"], (
        f"Régression : {result['detected']}/{result['total']} fraudes détectées, "
        f"minimum {result['min_detected']}")


if __name__ == "__main__":
    outcome = run_scenario()
    if not outcome["passed"]:
        print(f"❌ Quality gate échouée : moins de {outcome['min_detected']} fraudes détectées.")
        sys.exit(1)
    print("✅ Quality gate réussie.")
