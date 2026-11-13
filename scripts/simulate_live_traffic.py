"""
Simulateur de trafic pour la page Live du frontend.

Rejoue des transactions réelles d'un CSV (format Kaggle : merchant, first, last,
amt, category, ...) en les envoyant une par une à POST /predict. Chaque
prédiction apparaît aussitôt sur http://fraud.local/live (flux GET /stream) et
alimente les métriques Prometheus (fraud_predictions_total, fraud_rate_current).

Exemples
    python scripts/simulate_live_traffic.py
    python scripts/simulate_live_traffic.py --csv data/raws/fraud_600k.csv --n 200 --fraud-share 0.2
    python scripts/simulate_live_traffic.py --api http://localhost:8000 --interval 0.5

--fraud-share sur-représente les fraudes (si la colonne is_fraud existe) : avec
0,58 % de fraudes dans les données réelles, une démo n'en montrerait presque aucune.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "data" / "raws" / "fraud_600k.csv"

# Champs attendus par TransactionInput (backend/src/api.py)
MODEL_FIELDS = ["trans_date_trans_time", "amt", "lat", "long", "merch_lat", "merch_long",
                "category", "gender", "state", "job", "dob"]


def load_transactions(csv_path: Path, n: int, fraud_share: float, seed: int) -> pd.DataFrame:
    # Pour un gros fichier, on ne lit que les lignes nécessaires à l'échantillon
    df = pd.read_csv(csv_path, nrows=200_000)
    missing = [c for c in MODEL_FIELDS if c not in df.columns]
    if missing:
        sys.exit(f"❌ Colonnes absentes de {csv_path.name} : {missing}")

    if "is_fraud" in df.columns and fraud_share > 0:
        frauds = df[df["is_fraud"] == 1]
        legit = df[df["is_fraud"] == 0]
        n_fraud = min(len(frauds), round(n * fraud_share))
        df = pd.concat([frauds.sample(n_fraud, random_state=seed),
                        legit.sample(n - n_fraud, random_state=seed)])
    else:
        df = df.sample(min(n, len(df)), random_state=seed)
    return df.sample(frac=1, random_state=seed)   # mélange


def to_payload(row: pd.Series) -> dict:
    payload = {field: row[field] for field in MODEL_FIELDS}
    payload["amt"] = float(payload["amt"])
    for field in ("lat", "long", "merch_lat", "merch_long"):
        payload[field] = float(payload[field])
    # Champs d'affichage (ignorés par le modèle)
    if "merchant" in row:
        payload["merchant"] = str(row["merchant"]).removeprefix("fraud_")
    if "first" in row and "last" in row:
        payload["name"] = f"{row['first']} {row['last']}"
    return payload


def post(api: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f"{api}/predict", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api", default="http://api.fraud.local", help="URL de l'API (défaut : %(default)s)")
    parser.add_argument("--csv", type=Path, default=DEFAULT_CSV, help="CSV source (défaut : data/raws/fraud_600k.csv)")
    parser.add_argument("--n", type=int, default=100, help="nombre de transactions (défaut : %(default)s)")
    parser.add_argument("--interval", type=float, default=1.0, help="secondes entre deux envois (défaut : %(default)s)")
    parser.add_argument("--fraud-share", type=float, default=0.2, help="part de fraudes réelles (défaut : %(default)s)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if not args.csv.exists():
        sys.exit(f"❌ {args.csv} introuvable — `dvc pull data/raws/fraud_600k.csv` ou --csv <fichier>")

    df = load_transactions(args.csv, args.n, args.fraud_share, args.seed)
    print(f"📡 {len(df)} transactions -> {args.api}/predict (une toutes les {args.interval}s). Ctrl+C pour arrêter.")
    print("   Ouvrir http://fraud.local/live pour les voir défiler.\n")

    detected = flagged = real_frauds = 0
    try:
        for i, (_, row) in enumerate(df.iterrows(), start=1):
            try:
                result = post(args.api, to_payload(row))
            except urllib.error.URLError as e:
                sys.exit(f"❌ API injoignable ({e}) — minikube tunnel lancé ? --api correct ?")
            is_fraud = result["predictions"][0] == 1
            proba = (result.get("probabilities") or [0])[0]
            truth = int(row["is_fraud"]) if "is_fraud" in row else None
            flagged += is_fraud
            if truth == 1:
                real_frauds += 1
                detected += is_fraud
            verdict = "🚨 FRAUDE" if is_fraud else "✅ ok    "
            label = "" if truth is None else ("  (fraude réelle)" if truth else "")
            print(f"[{i:>4}] {verdict} p={proba:.3f}  {row['amt']:>9.2f} $  {row['category']:<15}{label}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n⏹  Arrêt demandé.")

    print(f"\n📊 {flagged} transactions signalées ; fraudes réelles détectées : {detected}/{real_frauds}")


if __name__ == "__main__":
    main()
