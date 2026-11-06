"""
Publie le résultat de la détection de dérive vers l'API (stage Jenkins
« Publish Drift to Backend ») :
  - POST /update-drift-metrics  avec drift_summary.json ;
  - POST /upload-drift-report   avec drift_report.html (s'il existe).

Variables : API_URL (obligatoire) et API_ADMIN_TOKEN (si l'API l'exige,
envoyé dans l'en-tête X-API-Token).
"""
import json
import os
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
SUMMARY_PATH = BASE_DIR / "artifacts" / "jenkins" / "drift_summary.json"
REPORT_PATH = BASE_DIR / "artifacts" / "jenkins" / "drift_report.html"


def main():
    api_url = os.environ["API_URL"].rstrip("/")
    token = os.getenv("API_ADMIN_TOKEN")
    headers = {"X-API-Token": token} if token else {}

    if not SUMMARY_PATH.exists():
        sys.exit(f"❌ {SUMMARY_PATH} absent : drift_detection.py n'a pas tourné.")
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    payload = {
        "drift_detected": bool(summary.get("drift_detected", False)),
        "drift_score": float(summary.get("drift_score", 0.0)),
        "drifted_features_count": int(summary.get("drifted_features", 0)),
    }
    r = requests.post(f"{api_url}/update-drift-metrics", json=payload, headers=headers, timeout=30)
    print(f"POST /update-drift-metrics {payload} -> {r.status_code}")
    r.raise_for_status()

    if REPORT_PATH.exists():
        with open(REPORT_PATH, "rb") as f:
            r = requests.post(f"{api_url}/upload-drift-report", headers=headers, timeout=60,
                              files={"file": ("drift_report.html", f, "text/html")})
        print(f"POST /upload-drift-report -> {r.status_code}")
        r.raise_for_status()
    else:
        print("ℹ️  Pas de rapport HTML (aucune nouvelle donnée) : seul le statut est publié.")
    print("✅ Dérive publiée vers l'API.")


if __name__ == "__main__":
    main()
