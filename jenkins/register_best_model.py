"""
Champion / challenger, promotion dans le registre MLflow et export du modèle servi.

    python3 jenkins/register_best_model.py                  # pipeline ML (après train_model.py)
    python3 jenkins/register_best_model.py --export-champion # pipeline de déploiement

Pipeline ML :
  1. le challenger est le meilleur run, selon val_pr_auc, du dernier lot
     d'entraînement (artifacts/jenkins/ct_batch.txt écrit par train_model.py ;
     à défaut, de toute l'expérience CT) ;
  2. le champion est la version du modèle enregistré qui porte l'alias « champion »
     (repli : la version au stage Production) ;
  3. le challenger n'est enregistré et promu que s'il bat le champion de plus de
     MIN_IMPROVEMENT (défaut 0) sur val_pr_auc ;
  4. le champion — nouveau ou conservé — est exporté localement (model.pkl,
     metadata.json, production.pkl) pour le test de scénario ;
  5. la décision est écrite dans artifacts/jenkins/promotion.json (détail) et
     promotion.txt (« true »/« false »), que le Jenkinsfile lit pour décider de
     déclencher, ou non, le déploiement.

Pipeline de déploiement : --export-champion télécharge le champion depuis le
registre. C'est le registre MLflow, pas le remote DVC, qui fait foi pour le
modèle servi.
"""
import argparse
import json
import os
import pickle
import shutil
import sys
from datetime import datetime
from pathlib import Path

import mlflow
import mlflow.sklearn
from dotenv import load_dotenv
from mlflow.tracking import MlflowClient

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')

EXPERIMENT_NAME = os.getenv("CT_EXPERIMENT_NAME", "continuous_training_pipeline")
REGISTERED_MODEL_NAME = os.getenv("MLFLOW_REGISTERED_MODEL", "Fraud_Detection_Production")
CHAMPION_ALIAS = "champion"
SELECTION_METRIC = "val_pr_auc"
MIN_IMPROVEMENT = float(os.getenv("MIN_IMPROVEMENT", "0.0"))

# Le nom du dossier est historique : il reste Best_Fraud_LightGBM quel que soit l'algorithme
EXPORT_ROOT = BASE_DIR / "artifacts" / "mlflow" / "Best_Fraud_LightGBM"
EXPORT_DIR = EXPORT_ROOT / "1.0.0"            # copié par backend/Dockerfile dans /app/model_registry
PROMOTION_FILE = BASE_DIR / "artifacts" / "jenkins" / "promotion.json"
CT_BATCH_FILE = BASE_DIR / "artifacts" / "jenkins" / "ct_batch.txt"


def decide_promotion(challenger_run_id, challenger_score, champion_run_id, champion_score,
                     min_improvement=MIN_IMPROVEMENT):
    """Règle champion/challenger. Retourne (promouvoir ?, raison)."""
    if champion_run_id is None:
        return True, "aucun champion enregistré"
    if challenger_run_id == champion_run_id:
        return False, "le meilleur run est déjà le champion"
    if champion_score is None:
        return True, f"le champion n'a pas de métrique {SELECTION_METRIC} : non comparable, remplacé"
    if challenger_score > champion_score + min_improvement:
        return True, (f"challenger {challenger_score:.4f} > champion {champion_score:.4f}"
                      f" + marge {min_improvement:.4f}")
    return False, (f"challenger {challenger_score:.4f} <= champion {champion_score:.4f}"
                   f" + marge {min_improvement:.4f}")


def find_challenger():
    experiment = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
    if experiment is None:
        sys.exit(f"❌ Expérience '{EXPERIMENT_NAME}' introuvable : lancez d'abord train_model.py.")
    filter_string = f"metrics.{SELECTION_METRIC} > 0"
    if CT_BATCH_FILE.exists():
        ct_batch = CT_BATCH_FILE.read_text().strip()
        filter_string += f" and tags.ct_batch = '{ct_batch}'"
        print(f"🔎 Challengers limités au lot d'entraînement {ct_batch}")
    runs = mlflow.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string=filter_string,
        order_by=[f"metrics.{SELECTION_METRIC} DESC"],
        max_results=1,
    )
    if runs.empty:
        sys.exit(f"❌ Aucun run avec la métrique {SELECTION_METRIC} dans '{EXPERIMENT_NAME}'.")
    return runs.iloc[0]


def find_champion(client):
    """Retourne la ModelVersion du champion, ou None s'il n'y en a pas encore."""
    try:
        return client.get_model_version_by_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS)
    except Exception:
        pass
    try:   # serveur sans prise en charge des alias : repli sur les stages
        versions = client.get_latest_versions(REGISTERED_MODEL_NAME, stages=["Production"])
        return versions[0] if versions else None
    except Exception:
        return None


def promote(client, run_id):
    version = mlflow.register_model(f"runs:/{run_id}/model", REGISTERED_MODEL_NAME)
    try:
        client.set_registered_model_alias(REGISTERED_MODEL_NAME, CHAMPION_ALIAS, version.version)
        print(f"🏷️  Alias '{CHAMPION_ALIAS}' -> version {version.version}")
    except Exception as exc:
        print(f"⚠️  Alias non pris en charge ({exc}) : passage au stage Production.")
        client.transition_model_version_stage(REGISTERED_MODEL_NAME, version.version,
                                              stage="Production", archive_existing_versions=True)
    return version


def export_model(client, model_version):
    """Écrit model.pkl, metadata.json et production.pkl pour l'API et les tests."""
    run = client.get_run(model_version.run_id)
    metrics, params = run.data.metrics, run.data.params
    algorithm = params.get("model_name") or run.data.tags.get("model_name", "inconnu")

    model = mlflow.sklearn.load_model(f"runs:/{model_version.run_id}/model")
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    with open(EXPORT_DIR / "model.pkl", "wb") as f:
        pickle.dump(model, f)
    shutil.copy2(EXPORT_DIR / "model.pkl", EXPORT_ROOT / "production.pkl")

    metadata = {
        "model_name": f"Best_Fraud_{algorithm}",
        "algorithm": algorithm,
        "registered_model": REGISTERED_MODEL_NAME,
        "version": str(model_version.version),
        "run_id": model_version.run_id,
        "selection_metric": SELECTION_METRIC,
        "threshold": float(metrics.get("val_best_threshold", 0.5)),
        "metrics": {k: float(v) for k, v in sorted(metrics.items()) if k.startswith(("val_", "test_"))},
        "exported_at": datetime.now().isoformat(timespec="seconds"),
    }
    (EXPORT_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    print(f"✅ Champion exporté : {metadata['model_name']} v{metadata['version']} "
          f"(seuil {metadata['threshold']:.3f}) -> {EXPORT_DIR}")
    return metadata


def run_ml_pipeline(client):
    challenger = find_challenger()
    challenger_id = challenger.run_id
    challenger_score = float(challenger[f"metrics.{SELECTION_METRIC}"])
    print(f"🥊 Challenger : {challenger.get('params.model_name', '?')} ({challenger_id}) "
          f"{SELECTION_METRIC}={challenger_score:.4f}")

    champion = find_champion(client)
    champion_score = None
    if champion is not None:
        champion_score = client.get_run(champion.run_id).data.metrics.get(SELECTION_METRIC)
        shown = "absent" if champion_score is None else f"{champion_score:.4f}"
        print(f"👑 Champion   : version {champion.version} ({champion.run_id}) {SELECTION_METRIC}={shown}")

    promoted, reason = decide_promotion(challenger_id, challenger_score,
                                        champion.run_id if champion else None, champion_score)
    print(("✅ PROMOTION : " if promoted else "⏸️  PAS DE PROMOTION : ") + reason)
    if promoted:
        champion = promote(client, challenger_id)

    metadata = export_model(client, champion)
    PROMOTION_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROMOTION_FILE.write_text(json.dumps({
        "promoted": promoted,
        "reason": reason,
        "challenger": {"run_id": challenger_id, SELECTION_METRIC: challenger_score},
        "champion": {"version": metadata["version"], "run_id": metadata["run_id"]},
    }, indent=2, ensure_ascii=False))
    PROMOTION_FILE.with_suffix(".txt").write_text("true" if promoted else "false")


def run_export_champion(client):
    champion = find_champion(client)
    if champion is None:
        if (EXPORT_DIR / "model.pkl").exists():
            print("⚠️  Aucun champion dans le registre : on garde le modèle récupéré par DVC.")
            return
        sys.exit("❌ Aucun champion dans le registre et aucun modèle local (dvc pull).")
    export_model(client, champion)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--export-champion", action="store_true",
                        help="télécharge le champion actuel sans rien enregistrer (pipeline de déploiement)")
    args = parser.parse_args()

    print(f"📡 MLflow : {mlflow.get_tracking_uri()}")
    client = MlflowClient()
    if args.export_champion:
        run_export_champion(client)
    else:
        run_ml_pipeline(client)


if __name__ == "__main__":
    main()
