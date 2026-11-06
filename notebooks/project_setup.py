"""
Configuration commune aux notebooks du projet.

- localise la racine du dépôt (dossier contenant .dvc/ ou .git) ;
- charge le fichier .env (identifiants DagsHub / MLflow, jamais commités) ;
- configure MLflow : serveur distant si MLFLOW_TRACKING_URI est défini,
  sinon base SQLite locale (mlflow.db) + artefacts dans mlruns/ ;
- fournit les versions Git et DVC à enregistrer dans chaque run MLflow.
"""
import os
import re
import subprocess
from pathlib import Path


def find_project_root(start=None):
    here = Path(start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / '.dvc').is_dir() or (candidate / '.git').exists():
            return candidate
    return here


ROOT = find_project_root()
DATA_DIR = ROOT / 'data' / 'raws'
ARTIFACTS_DIR = ROOT / 'artifacts'
PREPROCESSING_DIR = ARTIFACTS_DIR / 'preprocessing'
MODELING_DIR = ARTIFACTS_DIR / 'modeling'
REGISTRY_DIR = ARTIFACTS_DIR / 'mlflow'


def load_env():
    """Charge ROOT/.env s'il existe (python-dotenv). Retourne True si un fichier a été lu."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    return load_dotenv(ROOT / '.env')


def env_flag(name, default=False):
    """Lit un booléen dans l'environnement : 1/true/yes/oui -> True."""
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'oui'}


def env_int(name, default):
    value = os.getenv(name)
    return int(value) if value not in (None, '') else default


def git_commit():
    """Hash du commit courant (None hors d'un dépôt Git)."""
    try:
        out = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() or None
    except (OSError, subprocess.SubprocessError):
        return None


def dvc_versions():
    """Hash md5 des répertoires suivis par DVC (data.dvc, artifacts.dvc).

    Enregistrer ces hash dans MLflow permet de savoir avec quelle version
    exacte des données un modèle a été entraîné.
    """
    versions = {}
    for dvc_file in sorted(ROOT.glob('*.dvc')):
        if not dvc_file.is_file():   # le glob inclut aussi le dossier caché .dvc/
            continue
        match = re.search(r'md5:\s*([0-9a-f]+)', dvc_file.read_text())
        if match:
            versions[f'dvc_{dvc_file.stem}_md5'] = match.group(1)
    return versions


def mask_uri(uri):
    """Masque un éventuel mot de passe dans une URI (affichage seulement)."""
    return re.sub(r'//([^:/@]+):([^@]+)@', r'//\1:***@', uri)


def setup_mlflow(experiment_name=None):
    """Configure MLflow et sélectionne l'expérience.

    Variables lues (fichier .env ou environnement) :
      MLFLOW_TRACKING_URI       ex. https://dagshub.com/<owner>/<repo>.mlflow
      MLFLOW_TRACKING_USERNAME  utilisateur DagsHub
      MLFLOW_TRACKING_PASSWORD  token DagsHub
      MLFLOW_EXPERIMENT_NAME    défaut : fraud_detection

    Sans MLFLOW_TRACKING_URI, le suivi est local : ROOT/mlflow.db (métadonnées,
    Model Registry compris) et ROOT/mlruns/ (artefacts).
    """
    import mlflow

    load_env()
    uri = os.getenv('MLFLOW_TRACKING_URI')
    is_local = not uri
    if is_local:
        uri = f"sqlite:///{(ROOT / 'mlflow.db').as_posix()}"
    mlflow.set_tracking_uri(uri)

    name = experiment_name or os.getenv('MLFLOW_EXPERIMENT_NAME', 'fraud_detection')
    if mlflow.get_experiment_by_name(name) is None:
        kwargs = {'artifact_location': (ROOT / 'mlruns').as_uri()} if is_local else {}
        mlflow.create_experiment(name, **kwargs)
    experiment = mlflow.set_experiment(name)

    print(f"MLflow tracking URI : {mask_uri(uri)}" + ("  (mode local)" if is_local else ""))
    print(f"Expérience          : {experiment.name} (id={experiment.experiment_id})")
    return experiment


# Les options des notebooks (QUICK_RUN, MLFLOW_*...) sont disponibles dès l'import
load_env()
