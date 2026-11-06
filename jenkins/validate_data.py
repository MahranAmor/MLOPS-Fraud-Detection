"""
Validation bloquante des nouvelles données, AVANT la détection de dérive et
tout ré-entraînement.

La dérive (drift_detection.py) mesure si la distribution a changé ; la
validation vérifie que les données sont exploitables. Des données corrompues
(colonnes manquantes, valeurs nulles, coordonnées impossibles, catégories
inconnues) ne doivent jamais atteindre l'entraînement : le script sort alors
avec le code 1 et le pipeline Jenkins s'arrête.

Sortie : artifacts/jenkins/data_validation.json
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
REFERENCE_DATA_PATH = BASE_DIR / "data" / "raws" / "fraud_600k.csv"
NEW_DATA_PATH = BASE_DIR / "data" / "raws" / "new_data.csv"
REPORT_PATH = BASE_DIR / "artifacts" / "jenkins" / "data_validation.json"

REQUIRED_COLUMNS = ['trans_date_trans_time', 'category', 'amt', 'gender', 'city_pop',
                    'lat', 'long', 'merch_lat', 'merch_long', 'dob', 'is_fraud']
MIN_ROWS = int(os.getenv("MIN_NEW_ROWS", "1000"))


def validate(df, known_categories, min_rows=MIN_ROWS):
    """Retourne la liste des erreurs bloquantes (vide si les données sont valides)."""
    errors = []
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return [f"colonnes manquantes : {missing}"]   # les contrôles suivants n'auraient pas de sens

    if len(df) < min_rows:
        errors.append(f"{len(df)} lignes, minimum attendu {min_rows}")

    nulls = df[REQUIRED_COLUMNS].isna().sum()
    for col, n in nulls[nulls > 0].items():
        errors.append(f"{col} : {n} valeurs manquantes")

    if (df['amt'] < 0).any():
        errors.append(f"amt : {(df['amt'] < 0).sum()} montants négatifs")
    if (df['city_pop'] < 0).any():
        errors.append(f"city_pop : {(df['city_pop'] < 0).sum()} populations négatives")
    for col, limit in [('lat', 90), ('merch_lat', 90), ('long', 180), ('merch_long', 180)]:
        out = (df[col].abs() > limit).sum()
        if out:
            errors.append(f"{col} : {out} valeurs hors de [-{limit}, {limit}]")

    bad_target = ~df['is_fraud'].isin([0, 1])
    if bad_target.any():
        errors.append(f"is_fraud : {bad_target.sum()} valeurs différentes de 0/1")
    bad_gender = ~df['gender'].isin(['M', 'F'])
    if bad_gender.any():
        errors.append(f"gender : {bad_gender.sum()} valeurs différentes de M/F")

    unknown = sorted(set(df['category'].dropna().astype(str)) - set(known_categories))
    if unknown:
        errors.append(f"category : catégories inconnues du modèle {unknown}")

    for col in ['trans_date_trans_time', 'dob']:
        unparsable = pd.to_datetime(df[col], errors='coerce').isna().sum()
        if unparsable:
            errors.append(f"{col} : {unparsable} dates illisibles")
    return errors


def main():
    print("=" * 50)
    print("🧪 Validation des nouvelles données")
    print("=" * 50)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not NEW_DATA_PATH.exists():
        print(f"ℹ️  {NEW_DATA_PATH.name} absent : rien à valider (pas de ré-entraînement possible).")
        REPORT_PATH.write_text(json.dumps({"status": "no_data", "errors": []}, indent=2))
        return

    known_categories = pd.read_csv(REFERENCE_DATA_PATH, usecols=['category'])['category'].astype(str).unique()
    df = pd.read_csv(NEW_DATA_PATH)
    print(f"📂 {len(df)} lignes, {df.shape[1]} colonnes")

    errors = validate(df, known_categories)
    REPORT_PATH.write_text(json.dumps({"status": "failed" if errors else "passed",
                                       "rows": len(df), "errors": errors},
                                      indent=2, ensure_ascii=False))
    if errors:
        print("❌ Données invalides — pipeline arrêté :")
        for err in errors:
            print(f"   - {err}")
        sys.exit(1)
    print("✅ Données valides.")


if __name__ == "__main__":
    main()
