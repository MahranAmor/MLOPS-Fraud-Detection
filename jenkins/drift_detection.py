"""
Détection de dérive des données avec Evidently AI (stage Jenkins « Data Drift Detection »).

Compare data/raws/new_data.csv à la référence data/raws/fraud_600k.csv sur
6 features. La dérive est déclarée si la part de features dérivées dépasse
DRIFT_THRESHOLD (0,30, soit 2 features sur 6 ou plus).

Sorties (artifacts/jenkins/) :
  - drift_result.txt    « true » ou « false », lu par le Jenkinsfile ;
  - drift_summary.json  score et nombre de features dérivées (toujours écrit) ;
  - drift_report.html   rapport Evidently interactif (s'il y a de nouvelles données).

La publication vers l'API est faite ensuite par publish_drift.py.
"""
import json
import os
from pathlib import Path

import pandas as pd
from evidently import Report
from evidently.presets import DataDriftPreset

BASE_DIR = Path(__file__).resolve().parent.parent
REFERENCE_DATA_PATH = BASE_DIR / "data" / "raws" / "fraud_600k.csv"
NEW_DATA_PATH = BASE_DIR / "data" / "raws" / "new_data.csv"
OUTPUT_DIR = BASE_DIR / "artifacts" / "jenkins"
REPORT_PATH = OUTPUT_DIR / "drift_report.html"
FEATURES = ['amt', 'category', 'gender', 'city_pop', 'merch_lat', 'merch_long']
DRIFT_THRESHOLD = float(os.getenv("DRIFT_THRESHOLD", "0.3"))


def load_data(path, label):
    print(f"📂 Chargement {label} depuis {path}...")
    df = pd.read_csv(path, usecols=FEATURES)
    print(f"   ✅ {label} : {df.shape[0]} lignes")
    return df


def write_outputs(drift_detected, drift_share, drifted):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "drift_result.txt").write_text("true" if drift_detected else "false")
    (OUTPUT_DIR / "drift_summary.json").write_text(json.dumps({
        "drift_detected": drift_detected,
        "drift_score": round(float(drift_share), 4),
        "drifted_features": int(drifted),
        "features": FEATURES,
        "threshold": DRIFT_THRESHOLD,
    }, indent=2))
    print(f"\nDRIFT_DETECTED={'true' if drift_detected else 'false'}")


def main():
    print("=" * 50)
    print("🔍 Data Drift Detection - Evidently AI")
    print("=" * 50)

    if not NEW_DATA_PATH.exists():
        print(f"⚠️  {NEW_DATA_PATH.name} absent : pas de dérive mesurable.")
        write_outputs(False, 0.0, 0)
        return

    reference_df = load_data(REFERENCE_DATA_PATH, "Référence (fraud_600k)")
    new_df = load_data(NEW_DATA_PATH, "Nouvelles données")

    print("\n📊 Calcul du drift avec Evidently...")
    snapshot = Report([DataDriftPreset()]).run(new_df, reference_df)   # (current, reference)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot.save_html(str(REPORT_PATH))
    print(f"📄 Rapport HTML : {REPORT_PATH}")

    drift_share, drifted = 0.0, 0
    for metric in snapshot.dict().get('metrics', []):
        if 'DriftedColumnsCount' in metric.get('metric_name', ''):
            value = metric.get('value', {})
            drift_share = value.get('share', 0.0)
            drifted = int(value.get('count', 0))
            break

    print(f"\n📈 Features analysées : {len(FEATURES)} | dérivées : {drifted} "
          f"| part : {drift_share:.2%} | seuil : {DRIFT_THRESHOLD:.2%}")
    drift_detected = drift_share > DRIFT_THRESHOLD
    print("🚨 DRIFT DÉTECTÉ → ré-entraînement." if drift_detected
          else "✅ Pas de drift significatif → modèle conservé.")
    write_outputs(drift_detected, drift_share, drifted)


if __name__ == "__main__":
    main()
