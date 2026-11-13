"""
API FastAPI de détection de fraude bancaire.

Endpoints publics
    GET  /                 message d'accueil
    GET  /live             sonde de vie (le processus répond)
    GET  /health           sonde de disponibilité : 503 tant que modèle et processeurs ne sont pas chargés
    GET  /features         features attendues par le modèle
    GET  /model-info       métadonnées brutes du modèle chargé
    GET  /model-metadata   métadonnées résumées (page Monitoring)
    POST /predict          une transaction ou une liste de transactions (JSON)
    POST /predictCSV       fichier CSV -> CSV enrichi des colonnes predict et fraud_probability
    GET  /stream           flux temps réel (Server-Sent Events) des prédictions faites par /predict
    GET  /metrics          métriques Prometheus (format OpenMetrics)
    GET  /metrics-summary  synthèse des métriques pour le frontend
    GET  /drift-status     dernier résultat de dérive publié par Jenkins
    GET  /drift-report     rapport HTML Evidently publié par Jenkins

Endpoints réservés à Jenkins (en-tête X-API-Token exigé si API_ADMIN_TOKEN est défini)
    POST /update-drift-metrics
    POST /upload-drift-report

Variables d'environnement
    MODEL_REGISTRY_DIR   dossier contenant model.pkl et metadata.json
                         (défaut : <racine>/artifacts/mlflow/Best_Fraud_LightGBM/1.0.0)
    PROCESSORS_DIR       dossier des processeurs (lu par preprocessing.py)
    FRAUD_THRESHOLD      force le seuil de décision (sinon metadata.json, sinon 0.5)
    API_ADMIN_TOKEN      active la protection des endpoints d'écriture
    CORS_ORIGINS         origines autorisées, séparées par des virgules
    PROMETHEUS_URL       serveur Prometheus interrogé par /metrics-summary
    DRIFT_STATE_DIR      dossier lu au démarrage pour restaurer l'état de dérive
"""
import asyncio
import io
import itertools
import json
import os
import pickle
import secrets
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Union

import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from prometheus_client import Counter, Gauge, Histogram, make_asgi_app
from pydantic import BaseModel
from sklearn.exceptions import NotFittedError
from sklearn.utils.validation import check_is_fitted

from preprocessing import PreprocessingFraud

load_dotenv()

# Racine du dépôt : backend/src/api.py -> remonter de deux dossiers
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = REPO_ROOT / "artifacts" / "mlflow" / "Best_Fraud_LightGBM" / "1.0.0"
DEFAULT_DRIFT_STATE_DIR = REPO_ROOT / "artifacts" / "jenkins"
DEFAULT_PROMETHEUS_URL = "http://monitoring-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090"
DEFAULT_THRESHOLD = 0.5
FRAUD_RATE_WINDOW = 1000   # nombre de prédictions récentes utilisées pour fraud_rate_current
LIVE_REPLAY_SIZE = 20      # prédictions récentes renvoyées à un client qui ouvre /stream
LIVE_KEEPALIVE_S = 15      # commentaire SSE périodique : évite la coupure par l'Ingress (60 s)

app = FastAPI(
    title="Fraud Detection API",
    description="API de détection de transactions frauduleuses (modèle issu du registre MLflow)",
    version="2.0.0",
    root_path="/api",
)

cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,http://fraud.local")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Métriques Prometheus
# ============================================================================

# A. Performance du modèle
PREDICTIONS_TOTAL = Counter('fraud_predictions_total', 'Total des prédictions par résultat', ['result'])
FRAUD_RATE = Gauge('fraud_rate_current',
                   f'Taux de fraude sur les {FRAUD_RATE_WINDOW} dernières prédictions (0-1)')
PREDICTION_LATENCY = Histogram('fraud_prediction_latency_seconds',
                               'Latence des prédictions unitaires (/predict) en secondes',
                               buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0])
PREDICTION_ERRORS = Counter('fraud_prediction_errors_total', 'Total des erreurs de prédiction')
BATCH_TOTAL = Counter('fraud_batch_total', 'Total des prédictions batch CSV')

# B. Modèle servi
MODEL_VERSION = Gauge('fraud_model_version_info', 'Version du modèle en production', ['version', 'name', 'source'])
MODEL_LOADED_STATUS = Gauge('fraud_model_loaded', 'Modèle chargé : 1=oui, 0=non')
DECISION_THRESHOLD = Gauge('fraud_decision_threshold', 'Seuil de décision appliqué aux probabilités')

# C. Service HTTP
HTTP_REQUESTS_TOTAL = Counter('fraud_http_requests_total', 'Total des requêtes HTTP', ['method', 'endpoint', 'status'])
HTTP_REQUEST_LATENCY = Histogram('fraud_http_request_latency_seconds', 'Latence des requêtes HTTP',
                                 ['endpoint'], buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0, 10.0])

# D. Dérive (publiée par Jenkins)
DRIFT_SCORE = Gauge('fraud_drift_score', 'Score de drift Evidently (0-1)')
DRIFT_DETECTED_METRIC = Gauge('fraud_drift_detected', 'Drift détecté : 1=oui, 0=non')
DRIFT_FEATURES_COUNT = Gauge('fraud_drift_features_count', 'Nombre de features driftées')

app.mount("/metrics", make_asgi_app())

# ============================================================================
# État global
# ============================================================================
model = None
preprocessor = None
model_metadata = {}
decision_threshold = DEFAULT_THRESHOLD
recent_predictions = deque(maxlen=FRAUD_RATE_WINDOW)

# Flux temps réel (/stream) : en mémoire, propre à chaque pod. Avec plusieurs
# réplicas, chaque client ne verrait que les prédictions de son pod (il faudrait
# un bus partagé, Redis par exemple).
live_events = deque(maxlen=LIVE_REPLAY_SIZE)
live_subscribers: set = set()
live_event_ids = itertools.count(1)

# L'état de dérive vit en mémoire : Jenkins le pousse par HTTP après chaque
# exécution du pipeline ML. Un redémarrage du pod le remet à zéro (voir README).
drift_state = {
    "drift_detected": False,
    "drift_score": 0.0,
    "drifted_features_count": 0,
    "last_check": None,
    "report_html": None,
    "status": "no_data",
}


def resolve_threshold(metadata: Optional[dict]) -> float:
    """Seuil de décision : FRAUD_THRESHOLD > metadata.json['threshold'] > 0.5.

    Utilisé par l'API et par test/test_fraud_scenario.py, pour que le test
    valide exactement la règle de décision appliquée en production.
    """
    forced = os.getenv("FRAUD_THRESHOLD")
    if forced:
        return float(forced)
    if metadata and metadata.get("threshold") is not None:
        return float(metadata["threshold"])
    return DEFAULT_THRESHOLD


def require_admin_token(x_api_token: Optional[str] = Header(default=None)):
    """Protège les endpoints d'écriture quand API_ADMIN_TOKEN est défini."""
    expected = os.getenv("API_ADMIN_TOKEN")
    if expected and not secrets.compare_digest(x_api_token or "", expected):
        raise HTTPException(status_code=401, detail="Jeton X-API-Token absent ou invalide")


class InferencePreprocessor(PreprocessingFraud):
    """Rejoue à l'inférence les transformations apprises à l'entraînement.

    Attention : le feature engineering ci-dessous duplique celui de
    PreprocessingFraud et du notebook 02. Toute nouvelle feature doit être
    ajoutée aux deux endroits (le notebook 02, section 11, vérifie l'égalité).
    """

    def __init__(self):
        super().__init__()
        self.load_processors()
        self._check_processors()

    def _check_processors(self):
        missing = []
        if not self.feature_names.get('all_features'):
            missing.append('feature_names.pkl')
        if not self.label_encoders:
            missing.append('label_encoders.pkl')
        try:
            check_is_fitted(self.scaler)
        except NotFittedError:
            missing.append('scaler.pkl')
        if missing:
            raise RuntimeError(
                f"Processeurs absents ou invalides dans {self.processor_dir} : {', '.join(missing)}. "
                "Lancez `dvc pull artifacts/preprocessing/`."
            )

    def preprocess_inference(self, df_input: pd.DataFrame) -> pd.DataFrame:
        df = df_input.copy()

        # 1. Types
        if 'trans_date_trans_time' in df.columns:
            df['trans_date_trans_time'] = pd.to_datetime(df['trans_date_trans_time'])
        if 'dob' in df.columns:
            df['dob'] = pd.to_datetime(df['dob'])

        # 2. Feature engineering
        if 'trans_date_trans_time' in df.columns:
            ts = df['trans_date_trans_time']
            df['trans_hour'] = ts.dt.hour
            df['trans_day'] = ts.dt.day
            df['trans_month'] = ts.dt.month
            df['trans_year'] = ts.dt.year
            df['trans_dayofweek'] = ts.dt.dayofweek
            df['is_weekend'] = (df['trans_dayofweek'] >= 5).astype(int)
            df['day_period'] = df['trans_hour'].apply(self._get_period)
            if 'dob' in df.columns:
                df['age'] = (ts - df['dob']).dt.days / 365.25

        if all(col in df.columns for col in ['lat', 'long', 'merch_lat', 'merch_long']):
            df['distance_km'] = self._haversine_distance(df['lat'], df['long'], df['merch_lat'], df['merch_long'])

        if 'amt' in df.columns:
            df['amt_category'] = pd.cut(df['amt'], bins=[0, 50, 100, 200, float('inf')],
                                        labels=['faible', 'moyen', 'élevé', 'très_élevé'])

        # 3. Encodage : une catégorie inconnue est remplacée par la première classe connue
        for col in self.categorical_features:
            if col in df.columns and col in self.label_encoders:
                le = self.label_encoders[col]
                known = set(le.classes_)
                values = df[col].astype(str)
                df[col] = le.transform(values.where(values.isin(known), le.classes_[0]))

        # 4. Normalisation des colonnes numériques vues à l'entraînement
        numeric_cols = self.feature_names.get('numerical_features', [])
        for col in numeric_cols:
            if col not in df.columns:
                df[col] = 0
        if numeric_cols:
            df[numeric_cols] = self.scaler.transform(df[numeric_cols])

        # 5. Colonnes et ordre attendus par le modèle
        all_features = self.feature_names['all_features']
        for col in all_features:
            if col not in df.columns:
                df[col] = 0
        return df[all_features]


@app.on_event("startup")
async def startup_event():
    global model, preprocessor, model_metadata, decision_threshold

    try:
        preprocessor = InferencePreprocessor()
        print("✅ Processeurs chargés.")
    except Exception as e:
        preprocessor = None
        print(f"❌ Processeurs non chargés : {e}")

    model_dir = Path(os.getenv('MODEL_REGISTRY_DIR', str(DEFAULT_MODEL_DIR)))
    print(f"📁 Dossier du modèle : {model_dir}")
    try:
        with open(model_dir / "model.pkl", 'rb') as f:
            model = pickle.load(f)

        metadata_path = model_dir / "metadata.json"
        metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
        metadata.setdefault("model_name", "Best_Fraud_LightGBM")
        metadata.setdefault("version", "1.0.0")

        decision_threshold = resolve_threshold(metadata)
        model_metadata = {
            "name": metadata["model_name"],
            "uri": str(model_dir / "model.pkl"),
            "loaded_at": datetime.now().isoformat(),
            "source": "local_registry",
            "threshold": decision_threshold,
            "metadata": metadata,
        }
        MODEL_LOADED_STATUS.set(1)
        DECISION_THRESHOLD.set(decision_threshold)
        MODEL_VERSION.labels(version=str(metadata["version"]), name=metadata["model_name"],
                             source="local_registry").set(1)
        print(f"✅ Modèle chargé : {metadata['model_name']} v{metadata['version']} "
              f"(seuil de décision {decision_threshold:.3f})")
    except Exception as e:
        model = None
        MODEL_LOADED_STATUS.set(0)
        print(f"❌ Modèle non chargé : {e} — /health renverra 503.")

    # Restauration optionnelle de la dernière dérive connue (si le dossier existe)
    state_dir = Path(os.getenv("DRIFT_STATE_DIR", str(DEFAULT_DRIFT_STATE_DIR)))
    result_path = state_dir / "drift_result.txt"
    summary_path = state_dir / "drift_summary.json"
    if result_path.exists() and summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text())
            _apply_drift(drift_detected=result_path.read_text().strip() == "true",
                         drift_score=summary.get("drift_score", 0.0),
                         drifted_features_count=summary.get("drifted_features", 0),
                         last_check=datetime.fromtimestamp(result_path.stat().st_mtime).isoformat())
            print("✅ État de dérive restauré depuis", state_dir)
        except Exception as e:
            print(f"⚠️ État de dérive non restauré : {e}")


# ============================================================================
# Utilitaires de prédiction et de métriques
# ============================================================================

def _predict(df_input: pd.DataFrame):
    """Retourne (prédictions 0/1, probabilités de fraude ou None)."""
    X = preprocessor.preprocess_inference(df_input)
    if hasattr(model, "predict_proba"):
        proba = np.asarray(model.predict_proba(X))[:, 1]
        return (proba >= decision_threshold).astype(int), proba
    return np.asarray(model.predict(X)).astype(int), None


def _record_predictions(predictions: np.ndarray):
    fraud = int(predictions.sum())
    PREDICTIONS_TOTAL.labels(result='fraud').inc(fraud)
    PREDICTIONS_TOTAL.labels(result='legitimate').inc(len(predictions) - fraud)
    recent_predictions.extend(int(p) for p in predictions)
    if recent_predictions:
        FRAUD_RATE.set(sum(recent_predictions) / len(recent_predictions))


def _publish_live(items: list, predictions: np.ndarray, proba) -> None:
    """Diffuse chaque prédiction aux clients ouverts sur /stream.

    Appelée depuis une route async, donc dans la boucle d'événements : put_nowait
    est sûr. Un client trop lent (file pleine) perd des événements au lieu de
    ralentir /predict.
    """
    now = datetime.now().strftime("%H:%M:%S")
    for i, item in enumerate(items):
        event = {
            "id": str(next(live_event_ids)),
            "name": item.name,
            "merchant": item.merchant,
            "category": item.category,
            "amt": round(float(item.amt), 2),
            "is_fraud": bool(predictions[i]),
            "prediction": int(predictions[i]),
            "probability": None if proba is None else round(float(proba[i]), 4),
            "timestamp": now,
        }
        live_events.append(event)
        for queue in list(live_subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass


def _sse(event: dict) -> str:
    return f"id: {event['id']}\ndata: {json.dumps(event)}\n\n"


def _sample_value(metric, suffix="", **labels) -> float:
    """Lit une valeur via l'API publique collect() (sans attribut privé _value)."""
    for family in metric.collect():
        for sample in family.samples:
            if sample.name.endswith(suffix) and all(sample.labels.get(k) == v for k, v in labels.items()):
                return float(sample.value)
    return 0.0


def _counter_sum(counter) -> float:
    return sum(s.value for family in counter.collect() for s in family.samples if s.name.endswith("_total"))


def histogram_quantile(q: float, histogram) -> float:
    """Estime un quantile depuis les buckets cumulés, comme histogram_quantile() en PromQL.

    Interpolation linéaire dans le bucket qui contient le rang q * total ; si le
    rang tombe dans le bucket +Inf, on renvoie la plus grande borne finie.
    """
    buckets = sorted(
        (float(s.labels["le"]), s.value)
        for family in histogram.collect() for s in family.samples if s.name.endswith("_bucket")
    )
    if not buckets or buckets[-1][1] == 0:
        return 0.0
    rank = q * buckets[-1][1]
    lower_bound, lower_count = 0.0, 0.0
    for bound, count in buckets:
        if count >= rank:
            if bound == float("inf"):
                return lower_bound
            if count == lower_count:
                return bound
            return lower_bound + (bound - lower_bound) * (rank - lower_count) / (count - lower_count)
        lower_bound, lower_count = bound, count
    return lower_bound


def _apply_drift(drift_detected: bool, drift_score: float, drifted_features_count: int, last_check: str):
    drift_state.update(drift_detected=drift_detected, drift_score=drift_score,
                       drifted_features_count=drifted_features_count, last_check=last_check,
                       status="drift" if drift_detected else "stable")
    DRIFT_SCORE.set(drift_score)
    DRIFT_DETECTED_METRIC.set(1 if drift_detected else 0)
    DRIFT_FEATURES_COUNT.set(drifted_features_count)


# ============================================================================
# Endpoints
# ============================================================================

@app.get("/")
def read_root():
    return {"message": "Welcome to the Fraud Detection API. Use /docs for API documentation."}


@app.get("/live")
def liveness():
    """Sonde de vie : le processus répond, même si le modèle n'est pas chargé."""
    return {"status": "alive"}


@app.get("/health")
def health_check():
    """Sonde de disponibilité : 503 tant que le service ne peut pas prédire."""
    ready = model is not None and preprocessor is not None
    body = {"status": "ok" if ready else "degraded",
            "model_loaded": model is not None,
            "preprocessor_loaded": preprocessor is not None}
    return JSONResponse(status_code=200 if ready else 503, content=body)


@app.get("/features")
def get_features():
    if preprocessor is None:
        raise HTTPException(status_code=503, detail="Processeurs non chargés")
    return {
        "numerical": preprocessor.feature_names.get('numerical_features', []),
        "categorical": preprocessor.feature_names.get('categorical_features', []),
        "all_expected": preprocessor.feature_names.get('all_features', []),
    }


@app.get("/model-info")
def get_model_info():
    return model_metadata


class TransactionInput(BaseModel):
    trans_date_trans_time: str = "2025-01-01 12:00:00"
    amt: float = 100.0
    lat: float = 40.7128
    long: float = -74.0060
    merch_lat: float = 40.7200
    merch_long: float = -74.0100
    category: str = "grocery_pos"
    gender: str = "M"
    state: str = "NY"
    job: str = "Developer"
    dob: str = "1990-01-01"
    # Affichage seulement (flux /stream) : jamais transmis au modèle
    merchant: Optional[str] = None
    name: Optional[str] = None


DISPLAY_ONLY_FIELDS = {"merchant", "name"}


@app.post("/predict")
async def predict(request: Union[TransactionInput, List[TransactionInput]]):
    if model is None or preprocessor is None:
        raise HTTPException(status_code=503, detail="Model or preprocessor not available")

    start_time = time.time()
    try:
        items = request if isinstance(request, list) else [request]
        df_input = pd.DataFrame([item.model_dump(exclude=DISPLAY_ONLY_FIELDS) for item in items])
        predictions, proba = _predict(df_input)
    except Exception as e:
        PREDICTION_ERRORS.inc()
        HTTP_REQUESTS_TOTAL.labels(method='POST', endpoint='/predict', status='500').inc()
        raise HTTPException(status_code=500, detail=f"Prediction error: {e}")

    duration = time.time() - start_time
    _record_predictions(predictions)
    _publish_live(items, predictions, proba)
    PREDICTION_LATENCY.observe(duration)
    HTTP_REQUEST_LATENCY.labels(endpoint='/predict').observe(duration)
    HTTP_REQUESTS_TOTAL.labels(method='POST', endpoint='/predict', status='200').inc()

    return {
        "predictions": predictions.tolist(),
        "probabilities": None if proba is None else [round(float(p), 6) for p in proba],
        "threshold": decision_threshold,
        "count": len(predictions),
    }


@app.get("/stream")
async def live_stream(request: Request):
    """Flux Server-Sent Events des prédictions de /predict (page Live du frontend).

    À l'ouverture, renvoie les dernières prédictions, puis chaque nouvelle dès
    qu'elle est faite. Un commentaire « keep-alive » est envoyé toutes les
    LIVE_KEEPALIVE_S secondes pour que l'Ingress ne ferme pas la connexion.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=200)
    live_subscribers.add(queue)

    async def events():
        try:
            yield "retry: 3000\n\n"
            for event in list(live_events):
                yield _sse(event)
            while not await request.is_disconnected():
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=LIVE_KEEPALIVE_S)
                    yield _sse(event)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            live_subscribers.discard(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        # X-Accel-Buffering : l'Ingress nginx transmet chaque événement sans le mettre en tampon
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/predictCSV")
async def predict_csv(file: UploadFile = File(...)):
    if model is None or preprocessor is None:
        raise HTTPException(status_code=503, detail="Model or preprocessor not available")
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    start_time = time.time()
    try:
        df_input = pd.read_csv(io.BytesIO(await file.read()))
        predictions, proba = _predict(df_input)
    except Exception as e:
        PREDICTION_ERRORS.inc()
        HTTP_REQUESTS_TOTAL.labels(method='POST', endpoint='/predictCSV', status='500').inc()
        raise HTTPException(status_code=500, detail=f"Processing error: {e}")

    # La latence d'un batch n'alimente pas fraud_prediction_latency_seconds :
    # un gros CSV fausserait le p99 et déclencherait l'alerte HighLatency.
    duration = time.time() - start_time
    _record_predictions(predictions)
    HTTP_REQUEST_LATENCY.labels(endpoint='/predictCSV').observe(duration)
    HTTP_REQUESTS_TOTAL.labels(method='POST', endpoint='/predictCSV', status='200').inc()
    BATCH_TOTAL.inc()

    df_result = df_input.copy()
    df_result['predict'] = predictions
    if proba is not None:
        df_result['fraud_probability'] = np.round(proba, 6)
    output = io.StringIO()
    df_result.to_csv(output, index=False)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=prediction_{file.filename}"},
    )


@app.get("/model-metadata")
def get_model_metadata():
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    meta = model_metadata.get("metadata", {})
    return {
        "model_name": model_metadata.get("name", "Best_Fraud_LightGBM"),
        "version": str(meta.get('version', '1.0.0')),
        "source": model_metadata.get("source", "local_registry"),
        "loaded_at": model_metadata.get("loaded_at", ""),
        "mlflow_run_id": meta.get("run_id", "N/A"),
        "stage": "production",
        "algorithm": meta.get("algorithm", "LightGBM"),
        "threshold": decision_threshold,
        "features_count": len(preprocessor.feature_names.get('all_features', [])) if preprocessor else 0,
    }


@app.get("/drift-status")
def get_drift_status():
    return {
        "drift_detected": drift_state["drift_detected"],
        "status": drift_state["status"],
        "last_check": drift_state["last_check"],
        "report_available": drift_state["report_html"] is not None,
        "drift_score": drift_state["drift_score"],
        "drifted_features_count": drift_state["drifted_features_count"],
        "message": ("Aucune analyse disponible — lancez le pipeline Jenkins"
                    if drift_state["status"] == "no_data" else None),
    }


@app.get("/drift-report", response_class=HTMLResponse)
def get_drift_report():
    if drift_state["report_html"] is None:
        return HTMLResponse(content="""
            <div style="font-family:sans-serif;padding:40px;text-align:center;color:#666;">
                <h2>Aucun rapport disponible</h2>
                <p>Lancez le pipeline Jenkins pour générer un rapport de drift Evidently.</p>
            </div>
        """)
    return HTMLResponse(content=drift_state["report_html"])


class DriftMetricsUpdate(BaseModel):
    drift_detected: bool
    drift_score: float
    drifted_features_count: int


@app.post("/update-drift-metrics", dependencies=[Depends(require_admin_token)])
def update_drift_metrics(payload: DriftMetricsUpdate):
    """Reçoit le résultat de jenkins/drift_detection.py (via jenkins/publish_drift.py)."""
    _apply_drift(payload.drift_detected, payload.drift_score, payload.drifted_features_count,
                 datetime.now().isoformat())
    return {"status": "ok", **payload.model_dump()}


@app.post("/upload-drift-report", dependencies=[Depends(require_admin_token)])
async def upload_drift_report(file: UploadFile = File(...)):
    """Reçoit le rapport HTML Evidently et le garde en mémoire."""
    if not file.filename.endswith('.html'):
        raise HTTPException(status_code=400, detail="File must be an HTML file")
    contents = await file.read()
    drift_state["report_html"] = contents.decode("utf-8")
    print(f"✅ Rapport de dérive reçu : {len(contents)} octets")
    return {"status": "ok", "message": "Rapport Evidently reçu et stocké"}


@app.get("/metrics-summary")
def get_metrics_summary():
    prom_url = os.getenv("PROMETHEUS_URL", DEFAULT_PROMETHEUS_URL)

    def prom_query(query, all_results=False):
        if not prom_url:
            return [] if all_results else 0
        try:
            r = requests.get(f"{prom_url}/api/v1/query", params={"query": query}, timeout=3)
            results = r.json().get("data", {}).get("result", [])
        except Exception:
            return [] if all_results else 0
        if all_results:
            return results
        return float(results[0]["value"][1]) if results else 0

    ns = 'namespace="fraud-detection"'
    lat_count = _sample_value(PREDICTION_LATENCY, "_count")
    lat_avg = _sample_value(PREDICTION_LATENCY, "_sum") / lat_count if lat_count else 0.0
    cpu = prom_query(f'sum(rate(container_cpu_usage_seconds_total{{{ns}}}[5m])) by (pod)', all_results=True)
    mem = prom_query(f'sum(container_memory_working_set_bytes{{{ns}}}) by (pod)', all_results=True)

    return {
        "fraud_rate": _sample_value(FRAUD_RATE),
        "predictions_fraud": _sample_value(PREDICTIONS_TOTAL, "_total", result="fraud"),
        "predictions_legit": _sample_value(PREDICTIONS_TOTAL, "_total", result="legitimate"),
        "prediction_latency_avg": lat_avg,
        "prediction_latency_p50": histogram_quantile(0.50, PREDICTION_LATENCY),
        "prediction_latency_p95": histogram_quantile(0.95, PREDICTION_LATENCY),
        "prediction_latency_p99": histogram_quantile(0.99, PREDICTION_LATENCY),
        "prediction_errors": _counter_sum(PREDICTION_ERRORS),
        "decision_threshold": decision_threshold,
        "model_loaded": _sample_value(MODEL_LOADED_STATUS),
        "drift_score": _sample_value(DRIFT_SCORE),
        "drift_detected": _sample_value(DRIFT_DETECTED_METRIC),
        "drift_features_count": _sample_value(DRIFT_FEATURES_COUNT),
        "http_requests_total": _counter_sum(HTTP_REQUESTS_TOTAL),
        "k8s_running_pods": int(prom_query(f'sum(kube_pod_status_phase{{{ns}, phase="Running"}} == 1) or vector(0)')),
        "k8s_pending_pods": int(prom_query(f'sum(kube_pod_status_phase{{{ns}, phase="Pending"}} == 1) or vector(0)')),
        "k8s_failed_pods": int(prom_query(f'sum(kube_pod_status_phase{{{ns}, phase="Failed"}} == 1) or vector(0)')),
        "k8s_restart_pods": int(prom_query(f'sum(kube_pod_container_status_restarts_total{{{ns}}})')),
        "k8s_cpu_by_pod": {r["metric"].get("pod", "?"): float(r["value"][1]) for r in cpu},
        "k8s_mem_by_pod": {r["metric"].get("pod", "?"): float(r["value"][1]) for r in mem},
    }
