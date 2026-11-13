"""
Tests unitaires de l'API : modèle et préprocesseur sont remplacés par des mocks,
aucun artefact DVC n'est nécessaire.

    pytest test/test_api_mock.py
"""
import asyncio
import os
import pickle
import sys
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from prometheus_client import Histogram
from sklearn.preprocessing import LabelEncoder, RobustScaler

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'backend', 'src'))

import api  # noqa: E402
from api import InferencePreprocessor, app, histogram_quantile, resolve_threshold  # noqa: E402

client = TestClient(app)   # sans « with » : l'événement startup ne tourne pas, rien n'est chargé

sample_data = {
    "trans_date_trans_time": "2025-01-01 12:00:00",
    "amt": 100.0,
    "lat": 40.0,
    "long": -74.0,
    "merch_lat": 40.1,
    "merch_long": -74.1,
    "category": "grocery_pos",
    "gender": "M",
    "state": "NY",
    "job": "Developer",
    "dob": "1990-01-01",
}


def fake_model(fraud_probability):
    model = MagicMock()
    model.predict_proba.return_value = np.array([[1 - fraud_probability, fraud_probability]])
    return model


# ---------------------------------------------------------------- endpoints

def test_read_root():
    response = client.get("/")
    assert response.status_code == 200
    assert "Welcome" in response.json()["message"]


def test_live_always_ok():
    assert client.get("/live").status_code == 200


def test_health_is_503_without_model():
    # La readinessProbe Kubernetes ne doit pas envoyer de trafic à un pod sans modèle
    response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "degraded"


@patch('api.preprocessor')
@patch('api.model')
def test_health_is_200_when_ready(mock_mod, mock_prep):
    assert client.get("/health").status_code == 200


@patch('api.decision_threshold', 0.5)
@patch('api.preprocessor')
@patch('api.model', new_callable=lambda: fake_model(0.1))
def test_predict_endpoint(mock_mod, mock_prep):
    mock_prep.preprocess_inference.return_value = pd.DataFrame([1])

    response = client.post("/predict", json=sample_data)
    assert response.status_code == 200
    body = response.json()
    assert body["predictions"] == [0]
    assert body["probabilities"] == [pytest.approx(0.1)]
    assert body["threshold"] == 0.5


@patch('api.preprocessor')
@patch('api.model', new_callable=lambda: fake_model(0.7))
def test_predict_applies_decision_threshold(mock_mod, mock_prep):
    mock_prep.preprocess_inference.return_value = pd.DataFrame([1])
    with patch('api.decision_threshold', 0.8):
        assert client.post("/predict", json=sample_data).json()["predictions"] == [0]
    with patch('api.decision_threshold', 0.6):
        assert client.post("/predict", json=sample_data).json()["predictions"] == [1]


@patch('api.decision_threshold', 0.5)
@patch('api.preprocessor')
@patch('api.model', new_callable=lambda: fake_model(0.7))
def test_predict_publishes_to_live_stream(mock_mod, mock_prep):
    # Chaque prédiction de /predict part vers les clients de /stream (page Live)
    mock_prep.preprocess_inference.return_value = pd.DataFrame([1])
    queue = asyncio.Queue()
    api.live_subscribers.add(queue)
    try:
        payload = {**sample_data, "merchant": "Kirlin and Sons", "name": "Jane Doe"}
        assert client.post("/predict", json=payload).status_code == 200
    finally:
        api.live_subscribers.discard(queue)

    event = queue.get_nowait()
    assert event["is_fraud"] is True
    assert event["probability"] == pytest.approx(0.7)
    assert (event["merchant"], event["name"], event["amt"]) == ("Kirlin and Sons", "Jane Doe", 100.0)
    # Les champs d'affichage ne doivent jamais atteindre le modèle
    sent = mock_prep.preprocess_inference.call_args[0][0]
    assert not {"merchant", "name"} & set(sent.columns)


@patch('api.preprocessor')
@patch('api.model', new_callable=lambda: fake_model(0.1))
def test_predict_csv_endpoint(mock_mod, mock_prep):
    mock_prep.preprocess_inference.return_value = pd.DataFrame([1])

    files = {'file': ('test.csv', "amt,lat,long\n100,40,-74", 'text/csv')}
    response = client.post("/predictCSV", files=files)
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "attachment" in response.headers["content-disposition"]
    header = response.content.decode('utf-8').splitlines()[0]
    assert header.endswith("predict,fraud_probability")


def test_predict_returns_503_without_model():
    assert client.post("/predict", json=sample_data).status_code == 503


def test_drift_endpoints_require_token_when_configured(monkeypatch):
    payload = {"drift_detected": True, "drift_score": 0.5, "drifted_features_count": 3}
    monkeypatch.setenv("API_ADMIN_TOKEN", "secret-de-test")
    assert client.post("/update-drift-metrics", json=payload).status_code == 401
    ok = client.post("/update-drift-metrics", json=payload, headers={"X-API-Token": "secret-de-test"})
    assert ok.status_code == 200
    assert client.get("/drift-status").json()["drift_detected"] is True


def test_update_test_metrics_endpoint_removed():
    # Les résultats de CI passent par le Pushgateway, plus par l'API
    assert client.post("/update-test-metrics", json={}).status_code == 404


# ---------------------------------------------------------------- fonctions

def test_resolve_threshold_priority(monkeypatch):
    monkeypatch.delenv("FRAUD_THRESHOLD", raising=False)
    assert resolve_threshold({}) == 0.5
    assert resolve_threshold({"threshold": 0.73}) == 0.73
    monkeypatch.setenv("FRAUD_THRESHOLD", "0.3")
    assert resolve_threshold({"threshold": 0.73}) == 0.3


def test_histogram_quantile_matches_promql_interpolation():
    h = Histogram('test_latency_seconds', 'test', buckets=[0.1, 0.5, 1.0], registry=None)
    for value in [0.05] * 50 + [0.3] * 40 + [0.8] * 10:
        h.observe(value)
    assert histogram_quantile(0.50, h) == pytest.approx(0.1)    # 50 obs <= 0.1
    assert histogram_quantile(0.90, h) == pytest.approx(0.5)    # 90 obs <= 0.5
    assert histogram_quantile(0.95, h) == pytest.approx(0.75)   # milieu du bucket ]0.5, 1.0]


# ---------------------------------------------------------------- préprocesseur

def test_inference_preprocessor_refuses_missing_artifacts(tmp_path, monkeypatch):
    monkeypatch.setenv("PROCESSORS_DIR", str(tmp_path))   # dossier vide
    with pytest.raises(RuntimeError, match="Processeurs absents"):
        InferencePreprocessor()


def test_inference_preprocessor_with_synthetic_artifacts(tmp_path, monkeypatch):
    """Rejoue preprocess_inference avec de vrais processeurs (créés pour le test)."""
    numerical = ['amt', 'lat', 'long', 'merch_lat', 'merch_long', 'trans_hour',
                 'trans_dayofweek', 'is_weekend', 'age', 'distance_km']
    categories = {
        'category': ['grocery_pos', 'shopping_net'], 'gender': ['F', 'M'], 'state': ['CA', 'NY'],
        'job': ['Developer', 'Teacher'], 'amt_category': ['faible', 'moyen', 'élevé', 'très_élevé'],
        'day_period': ['matin', 'après-midi', 'soirée', 'nuit'],
    }
    encoders = {col: LabelEncoder().fit(values) for col, values in categories.items()}
    rng = np.random.default_rng(0)
    scaler = RobustScaler().fit(pd.DataFrame(rng.normal(size=(50, len(numerical))), columns=numerical))
    feature_names = {'numerical_features': numerical, 'categorical_features': list(categories),
                     'all_features': numerical + list(categories)}
    for name, obj in [('scaler', scaler), ('label_encoders', encoders), ('feature_names', feature_names)]:
        with open(tmp_path / f"{name}.pkl", "wb") as f:
            pickle.dump(obj, f)
    monkeypatch.setenv("PROCESSORS_DIR", str(tmp_path))

    prep = InferencePreprocessor()
    unknown_category = {**sample_data, "category": "categorie_jamais_vue"}
    X = prep.preprocess_inference(pd.DataFrame([sample_data, unknown_category]))

    assert list(X.columns) == feature_names['all_features']    # ordre attendu par le modèle
    assert not X.isna().any().any()
    assert X.loc[1, 'category'] == 0                            # inconnue -> première classe connue
