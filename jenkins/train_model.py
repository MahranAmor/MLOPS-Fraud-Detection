"""
Entraînement continu (CT) — lancé par Jenkins quand une dérive est détectée.

Même protocole que le notebook 03 :
  - entraînement sur le train rééchantillonné par SMOTE ;
  - évaluation et seuil F1-optimal calculés sur un jeu de VALIDATION réel
    (jamais sur des données SMOTE, jamais sur le test) ;
  - métriques journalisées sous les mêmes noms (val_pr_auc, val_best_threshold...),
    pour que register_best_model.py compare les runs du notebook et ceux de Jenkins.

Le jeu de test n'est journalisé qu'à titre de rapport (test_*) : la sélection,
dans register_best_model.py, ne lit que val_pr_auc.

Limite connue : le script ré-entraîne sur artifacts/preprocessing/preprocessed_data.pkl,
pas sur data/raws/new_data.csv (voir README, « Limites connues »).
"""
import gzip
import os
import pickle
import re
import sys
from datetime import datetime
from pathlib import Path

import mlflow
import mlflow.sklearn
import numpy as np
from catboost import CatBoostClassifier
from dotenv import load_dotenv
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, average_precision_score, f1_score,
                             precision_recall_curve, precision_score, recall_score,
                             roc_auc_score)
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

DATA_PATH = BASE_DIR / "artifacts" / "preprocessing" / "preprocessed_data.pkl"
# Identifiant du lot d'entraînement, relu par register_best_model.py pour ne mettre en
# compétition que les modèles de CE lot (et non le meilleur run de tout l'historique)
CT_BATCH_FILE = BASE_DIR / "artifacts" / "jenkins" / "ct_batch.txt"
EXPERIMENT_NAME = os.getenv("CT_EXPERIMENT_NAME", "continuous_training_pipeline")
RANDOM_STATE = 42


def load_data(filepath):
    """Charge les données prétraitées (pickle compressé gzip ou pickle simple)."""
    print(f"Chargement des données depuis {filepath}...")
    if not filepath.exists():
        raise FileNotFoundError(f"Fichier de données non trouvé : {filepath}")
    try:
        with gzip.open(filepath, 'rb') as f:
            return pickle.load(f)
    except OSError:
        with open(filepath, 'rb') as f:
            return pickle.load(f)


def split_validation(data):
    """Retourne (X_val, y_val, X_test, y_test, origine de la validation).

    Le notebook 02 produit un X_val dédié. Un ancien artefact sans X_val est
    toléré : on coupe alors le test en deux moitiés stratifiées, pour ne jamais
    choisir un modèle sur les données qui servent à l'évaluer.
    """
    if 'X_val' in data and 'y_val' in data:
        return data['X_val'], data['y_val'], data['X_test'], data['y_test'], 'X_val'
    print("⚠️  X_val absent de preprocessed_data.pkl : validation = moitié stratifiée du test.")
    X_val, X_test, y_val, y_test = train_test_split(
        data['X_test'], data['y_test'], test_size=0.5,
        stratify=data['y_test'], random_state=RANDOM_STATE)
    return X_val, y_val, X_test, y_test, 'moitie_du_test'


def compute_metrics(y_true, proba, threshold=0.5):
    y_pred = (proba >= threshold).astype(int)
    return {
        'pr_auc': average_precision_score(y_true, proba),
        'roc_auc': roc_auc_score(y_true, proba),
        'precision': precision_score(y_true, y_pred, zero_division=0),
        'recall': recall_score(y_true, y_pred),
        'f1': f1_score(y_true, y_pred),
        'accuracy': accuracy_score(y_true, y_pred),
    }


def find_best_threshold(y_true, proba):
    """Seuil maximisant le F1 — calculé sur la validation, jamais sur le test."""
    precision, recall, thresholds = precision_recall_curve(y_true, proba)
    f1 = 2 * precision * recall / np.clip(precision + recall, 1e-12, None)
    best = int(np.argmax(f1[:-1]))   # le dernier point de la courbe n'a pas de seuil associé
    return float(thresholds[best]), float(f1[best])


def run_tags(validation_source):
    """Traçabilité : commit Git (fourni par Jenkins) et hash des données DVC."""
    tags = {'stage': 'continuous_training', 'validation_source': validation_source,
            'git_commit': os.getenv('GIT_COMMIT', 'inconnu')}
    for dvc_file in sorted(BASE_DIR.glob('*.dvc')):
        if dvc_file.is_file():
            match = re.search(r'md5:\s*([0-9a-f]+)', dvc_file.read_text())
            if match:
                tags[f'dvc_{dvc_file.stem}_md5'] = match.group(1)
    return tags


def candidate_models():
    return {
        'RandomForest': RandomForestClassifier(n_estimators=50, max_depth=10,
                                               random_state=RANDOM_STATE, n_jobs=-1),
        'XGBoost': XGBClassifier(n_estimators=100, random_state=RANDOM_STATE, n_jobs=-1,
                                 eval_metric='logloss'),
        'LightGBM': LGBMClassifier(n_estimators=100, random_state=RANDOM_STATE, n_jobs=-1, verbose=-1),
        'CatBoost': CatBoostClassifier(iterations=100, random_state=RANDOM_STATE, verbose=0),
    }


def train_and_track():
    try:
        data = load_data(DATA_PATH)
    except FileNotFoundError as e:
        print(f"❌ {e} — lancez `dvc pull artifacts/preprocessing/`.")
        sys.exit(1)   # code non nul : Jenkins doit s'arrêter, pas continuer sans modèle

    X_train, y_train = data['X_train'], data['y_train']
    X_val, y_val, X_test, y_test, validation_source = split_validation(data)
    print(f"Train {X_train.shape} | validation {X_val.shape} ({validation_source}) | test {X_test.shape}")

    mlflow.set_experiment(EXPERIMENT_NAME)
    run_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    ct_batch = os.getenv('BUILD_TAG') or f"local-{run_timestamp}"   # BUILD_TAG est fourni par Jenkins
    tags = {**run_tags(validation_source), 'ct_batch': ct_batch}
    models = candidate_models()
    print(f"🚀 Entraînement continu de {len(models)} modèles (expérience '{EXPERIMENT_NAME}')...")

    for name, model in models.items():
        with mlflow.start_run(run_name=f"{name}_CT_{run_timestamp}"):
            mlflow.set_tags({**tags, 'model_name': name})
            mlflow.log_params({'model_name': name, 'data_source': str(DATA_PATH.relative_to(BASE_DIR)),
                               'n_train_rows': len(X_train), 'n_features': X_train.shape[1]})
            mlflow.log_params({k: v for k, v in model.get_params().items()
                               if v is None or isinstance(v, (int, float, str, bool))})

            start = datetime.now()
            model.fit(X_train, y_train)
            duration = (datetime.now() - start).total_seconds()

            proba_val = model.predict_proba(X_val)[:, 1]
            val = compute_metrics(y_val, proba_val)
            threshold, f1_best = find_best_threshold(y_val, proba_val)
            mlflow.log_metrics({f'val_{k}': v for k, v in val.items()})
            mlflow.log_metrics({'val_best_threshold': threshold,
                                'val_f1_at_best_threshold': f1_best,
                                'training_time_seconds': duration})

            # Rapport seulement : la sélection ne lit jamais ces métriques
            test = compute_metrics(y_test, model.predict_proba(X_test)[:, 1], threshold)
            mlflow.log_metrics({f'test_{k}': v for k, v in test.items()})

            mlflow.sklearn.log_model(model, "model")
            print(f"  --> {name:<12} val PR-AUC {val['pr_auc']:.4f} | val ROC-AUC {val['roc_auc']:.4f} "
                  f"| seuil {threshold:.3f} | {duration:.1f}s")

    CT_BATCH_FILE.parent.mkdir(parents=True, exist_ok=True)
    CT_BATCH_FILE.write_text(ct_batch)
    print(f"\n✅ Entraînement continu terminé (lot {ct_batch}).")


if __name__ == "__main__":
    train_and_track()
