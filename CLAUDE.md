# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repository is

Two things live here:

1. **A bank-card fraud detection MLOps platform** (the course's running example): FastAPI backend + Next.js frontend, DVC/DagsHub for data, MLflow on DagsHub for tracking, Jenkins for CI/CD/CT, Kubernetes (minikube) for serving, Prometheus/Alertmanager + Evidently for monitoring.
2. **A LaTeX Beamer course** (194 pages, 14 sections) that teaches MLOps using that platform as the running example. Only the compiled `slides/main.pdf` lives in this repo; the LaTeX sources are kept outside it (on the author's machine in `~/Desktop/slides/`). `books/` (commercial PDFs) and `*.mp4` videos are gitignored on purpose and must never be committed.

`README.md` § "Guide complet" is the end-to-end install/run guide (local, Kubernetes, Jenkins, drift demo, operations, troubleshooting). `README_GITHUB_DVC_MLFLOW.md` details GitHub/DagsHub DVC/MLflow setup and the notebooks. Keep both in sync when changing remotes, env vars, ports, image names, or Jenkins credentials.

Code comments, log messages, UI strings, and slides are in **French**. Keep new content in French to match.

## Commands

### Data and artifacts (DVC)
`data/` and `artifacts/` (~2.3 GB) are gitignored and versioned with DVC against the DagsHub remote. The repo starts with **no data, no model and no `.dvc` pointer files**: everything is produced from scratch. The Kaggle "Credit Card Transactions Fraud Detection" `fraudTrain.csv` is saved as `data/raws/fraud_1M.csv`, then notebooks 01 → 02 run, then `dvc add data artifacts` creates `data.dvc` / `artifacts.dvc` (commit, `dvc push`, `git push`), then notebooks 03 → 04 run, then `dvc add artifacts` again (README step 5, `README_GITHUB_DVC_MLFLOW.md` §8). Before that first push, `dvc pull` has nothing to fetch. Once pushed, nothing that loads the model works until you pull:
```bash
dvc pull artifacts/preprocessing/ artifacts/mlflow/Best_Fraud_LightGBM/   # what serving and the Docker build need
dvc pull data/raws/fraud_600k.csv data/raws/new_data.csv                  # what drift detection needs
```
Put credentials in `.dvc/config.local` with `dvc remote modify origin --local user|password …`, as the Jenkinsfiles do. Don't put them in `.dvc/config`. The committed `origin` URL is a placeholder (`<utilisateur-dagshub>/<depot-dagshub>`) to fill in with `dvc remote modify origin url …` (README guide, step 3.2).

### Secrets and MLflow configuration
Copy `.env.example` to `.env` (gitignored). MLflow reads `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME` and `MLFLOW_TRACKING_PASSWORD` from the environment, and the notebooks load `.env` through `notebooks/project_setup.py`. Don't hard-code DagsHub owners, URIs or tokens in notebooks. With `MLFLOW_TRACKING_URI` unset, tracking falls back to `sqlite:///<root>/mlflow.db` + `<root>/mlruns/` (view with `mlflow ui --backend-store-uri sqlite:///mlflow.db`). The Jenkinsfiles derive everything from `DAGSHUB_USER` / `DAGSHUB_REPO` at the top of their `environment` block (placeholders `<utilisateur-dagshub>` / `<depot-dagshub>`; Docker Hub account `<compte-dockerhub>` in `IMAGE_*` and the k8s Deployments).

The Alertmanager Slack webhook is never committed: `k8s/monitoring/alertmanager-config.template.yaml` holds `${SLACK_WEBHOOK_URL}` and is applied with `envsubst '${SLACK_WEBHOOK_URL}' < … | kubectl apply -f -` (keep the explicit variable list, or envsubst mangles the Go templates). The rendered `k8s/monitoring/alertmanager-secret.yaml` is gitignored. Never write a real webhook, token or password into a tracked file.

### Notebooks
```bash
pip install -r requirements.txt     # includes dvc, mlflow, ipykernel
jupyter lab notebooks/              # run 01 → 02 → 03 → 04 in order
```
- Every notebook does `from project_setup import ...`. That module finds the repo root (the first parent containing `.dvc/` or `.git`), so paths never depend on the working directory or machine.
- Options are read from `.env` or the environment: `QUICK_RUN=1` (fast demo: tunes LightGBM and XGBoost on a sample, skips ensembles), `RUN_TUNING`, `RUN_ENSEMBLES`, `N_ITER`, `TUNING_MAX_ROWS`, `USE_MLFLOW`, `REBUILD_SUBSET`.
- Notebooks are committed **without outputs** (the course recommends `nbstripout --install`; README step 9 adds `--drop-empty-cells --keep-id` and strips `metadata.language_info` so re-running a notebook produces no diff). They need `data/raws/fraud_1M.csv` (Kaggle download, first time) or `dvc pull` once a version has been pushed. Notebook 02 raises `FileNotFoundError` with both hints when neither `fraud_600k.csv` nor `fraud_1M.csv` is present.

### Backend (run from repo root)
```bash
pip install -r backend/requirements.txt          # serving deps (includes prometheus-client)
MODEL_REGISTRY_DIR=artifacts/mlflow/Best_Fraud_LightGBM/1.0.0 \
PYTHONPATH=backend/src uvicorn backend.src.api:app --reload --port 8000
```
- `api.py` does `from preprocessing import …`, so `backend/src` must be on `PYTHONPATH`.
- `MODEL_REGISTRY_DIR` defaults to `<root>/artifacts/mlflow/Best_Fraud_LightGBM/1.0.0`; `PROCESSORS_DIR` (read in `PreprocessingFraud.__init__`) defaults to `<root>/artifacts/preprocessing`.
- The app sets `root_path="/api"`. Swagger is at `http://localhost:8000/docs`.
- Root `requirements.txt` holds the broader dev/training deps (xgboost, catboost, mlflow, dvc, pytest, httpx). `backend/requirements.txt` must keep scikit-learn, lightgbm, xgboost and catboost at the **same versions** as the root file: any of the four CT candidates can become the served pickle. The backend installs **`xgboost-cpu`** (same version, same `import xgboost`, no CUDA/NCCL libraries) and deliberately has **no `mlflow`**: the API only loads the exported pickle, and the model pickles reference only xgboost/sklearn/numpy. This brought the image from 3.2 GB to 1.43 GB. Re-check `/health` and `test_fraud_scenario.py` against a freshly built image after any change there.

### Tests
```bash
pytest test/                                                  # unit tests, no DVC artifacts needed
pytest test/test_api_mock.py::test_predict_endpoint           # single test
python test/test_fraud_scenario.py                            # quality gate on the real model (exit 1 on failure)
```
- `test_api_mock.py` mocks the model and preprocessor with `unittest.mock.patch('api.model')` etc. `TestClient(app)` is created without `with`, so the startup event never runs and `/health` is 503 by default. `test_inference_preprocessor_with_synthetic_artifacts` builds real pickles in `tmp_path` and points `PROCESSORS_DIR` at them.
- `test_jenkins_scripts.py` covers `register_best_model.decide_promotion` (mlflow is stubbed in `sys.modules`) and `validate_data.validate`.
- `test_fraud_scenario.py` loads `artifacts/mlflow/Best_Fraud_LightGBM/production.pkl`, applies `api.resolve_threshold(metadata)` (same rule as the API) to 11 known frauds, writes `artifacts/jenkins/scenario_test.json`, and fails below `MIN_DETECTED` (default 9). Under pytest it skips when the model file is absent.
- `testing/deepchecks.ipynb` (with `testing/requirements-deepchecks.txt`) covers data and model validation.

### Frontend
```bash
cd frontend && npm install && npm run dev      # http://localhost:3000, expects API at NEXT_PUBLIC_API_URL (default http://localhost:8000)
npm run build                                  # also type-checks; output is `standalone` (used by the Dockerfile)
```

### Full stack
```bash
docker-compose up -d --build    # api :8000, frontend :3000; backend image build requires artifacts/ (notebooks or dvc pull)
```

### Kubernetes
Apply `k8s/namespace.yaml`, then `k8s/backend/*`, `k8s/frontend/*`, and `k8s/ingress.yaml`. The `k8s/monitoring/*` manifests assume kube-prometheus-stack installed as release `monitoring` in namespace `monitoring`; the Alertmanager config goes through `envsubst` (see Secrets above).

### Slides
The sources are not in this repo. In the source folder: `make` (latexmk -> `build/main.pdf`), `make qa` (lists Overfull `\vbox` slides). Copy the resulting PDF to `slides/main.pdf` here.

## Architecture: how the pieces connect

### Preprocessing is shared between training and inference
`backend/src/preprocessing.py::PreprocessingFraud` is the training pipeline: clean, engineer features (time parts, age, haversine `distance_km`, `amt_category`, `day_period`), split 80/20 stratified, `LabelEncoder` per categorical column, `RobustScaler` on numerics, then SMOTE on train only. It pickles `scaler.pkl`, `label_encoders.pkl`, `feature_names.pkl`, `smote_config.pkl`, and `preprocessed_data.pkl` into `artifacts/preprocessing/`.

`api.py::InferencePreprocessor` subclasses it and **re-implements the feature engineering** in `preprocess_inference()`, using the loaded pickles. Changing a feature means editing both places. At inference time:
- unknown categories map to `le.classes_[0]`;
- missing columns are filled with 0;
- the output column order comes from `feature_names['all_features']`.

`InferencePreprocessor.__init__` raises `RuntimeError` if `feature_names.pkl`, `label_encoders.pkl` or a fitted `scaler.pkl` is missing, so the API reports `preprocessor_loaded: false` instead of failing later at predict time.

The notebooks (`notebooks/01–04`) are where preprocessing and modeling are actually run. `python backend/src/preprocessing.py` now runs `PreprocessingFraud.run_preprocessing()`, which **overwrites `artifacts/preprocessing/`** with artifacts that differ from notebook 02's (see the scaler note below) — don't run it casually.

### The notebook pipeline produces the artifacts
- **02_preprocessing** writes the same pickle files the API loads. It splits train/validation/test (64/16/20, stratified, seed 42) *before* fitting `LabelEncoder`s and the `RobustScaler`. The scaler is fitted on exactly `feature_names['numerical_features']` (15 columns): the API scales that list, so the two must stay identical. (`PreprocessingFraud.scale_features` in the backend instead scales every column after encoding. Both stay self-consistent with the API, but they produce different artifacts.) SMOTE is applied to train only.
- `preprocessed_data.pkl` keys:
  - `X_train`/`y_train`: SMOTE-resampled train;
  - `X_val`/`y_val` and `X_test`/`y_test`: real class distribution;
  - `X_train_orig`/`y_train_orig`: train before SMOTE.

  `jenkins/train_model.py` reads `X_train`, `X_val` and `X_test`; for an old pickle without `X_val` it splits the test set 50/50 (stratified) into validation and test, and tags the run `validation_source=moitie_du_test`.
- Section 11 of notebook 02 imports `api.InferencePreprocessor` and asserts that it reproduces `X_test`. This is the training-serving skew guard; keep it passing when features change.
- **03_fraud_detection_modeling** logs one MLflow run per model in the experiment `fraud_detection`:
  - validation metrics are logged as `val_*`;
  - each run carries tags `git_commit`, `dvc_data_md5` and `dvc_artifacts_md5`;
  - hyperparameters are tuned with `PredefinedSplit` on the real validation set, never with CV on SMOTE data;
  - the model is selected by `val_pr_auc` with an F1-optimal threshold;
  - `test_*` metrics are added only to the selected run (tag `selected=true`).
- **04_mlflow_tracking** registers the best run as `Fraud_Detection_Production` with alias `champion` (falling back to stage `Production`). It then exports `model.pkl`, `metadata.json` and `production.pkl` to `artifacts/mlflow/Best_Fraud_LightGBM/`, in the same format as `register_best_model.py`. The API decides with `resolve_threshold()`: `FRAUD_THRESHOLD` env > `metadata.json["threshold"]` > 0.5.

### Model artifacts and champion/challenger
`jenkins/register_best_model.py` (ML pipeline) takes the best run of the **current CT batch** by `val_pr_auc` (batch id in `artifacts/jenkins/ct_batch.txt`, tag `ct_batch`, written by `train_model.py`), compares it with the registered model `Fraud_Detection_Production` at alias `champion` (fallback: stage `Production`), and registers + aliases it only if `challenger > champion + MIN_IMPROVEMENT`. It always exports the resulting champion (new or kept) and writes `artifacts/jenkins/promotion.json` + `promotion.txt` (`true`/`false`). Rule is the pure function `decide_promotion()`.

The export, from `mlflow.sklearn.load_model(runs:/<id>/model)`, writes:
- `artifacts/mlflow/Best_Fraud_LightGBM/production.pkl`, read by `test_fraud_scenario.py`;
- `artifacts/mlflow/Best_Fraud_LightGBM/1.0.0/model.pkl` plus `metadata.json` (`version` = registry version, `run_id`, `algorithm`, `threshold` = `val_best_threshold`, `val_*`/`test_*` metrics), which the backend Dockerfile copies to `/app/model_registry/`.

The directory names `Best_Fraud_LightGBM` and `1.0.0` are fixed paths, whatever the algorithm or version. The API loads a plain pickle and doesn't use the MLflow registry at runtime.

### ML pipeline (`jenkins/Jenkinsfile.ml.txt`)
The Jenkinsfiles are `.txt` and are referenced from Jenkins job configs. Stages:
1. Checkout (deletes stale `artifacts/jenkins/*.txt|json|html`), `dvc pull` of `fraud_600k.csv`, `new_data.csv` (tolerated if absent) and `artifacts/preprocessing/`.
2. `validate_data.py`: blocking schema/null/range/known-category checks on `new_data.csv` → `data_validation.json`, exit 1 on error.
3. `drift_detection.py`: Evidently `DataDriftPreset` on 6 columns (`amt, category, gender, city_pop, merch_lat, merch_long`). Writes `drift_result.txt`, `drift_summary.json` (always, even without new data) and `drift_report.html`. Drift = share of drifted columns > `DRIFT_THRESHOLD` (0.3), i.e. 2 or more.
4. If drift: `train_model.py` (RF, XGBoost, LightGBM, CatBoost; logs `val_*`, `val_best_threshold`, `test_*`, tags git/DVC/`ct_batch`) → `register_best_model.py` (champion/challenger) → `test/test_fraud_scenario.py` (blocking quality gate).
5. `publish_drift.py` POSTs the summary and HTML report to the API (with `X-API-Token` if `API_ADMIN_TOKEN` is set).
6. If drift **and** `promotion.txt == true`: trigger `fraud-deploy-pipeline`.
7. `post`: `push_metrics.py 1|0` pushes build status, scenario results and promotion flag to the Pushgateway.

`simulate_new_data.py` generates a drifted `new_data.csv` for demos. CT still retrains on the existing `preprocessed_data.pkl`, **not** on `new_data.csv` (known limitation, README).

### Deploy pipeline (`jenkins/Jenkinsfile.deploy.txt`)
1. `IMAGE_TAG = <BUILD_NUMBER>-<git short sha>`.
2. `dvc pull` of the artifacts, then `register_best_model.py --export-champion` replaces the model with the registry champion (keeps the DVC model if no champion exists).
3. Docker build and push of `<compte-dockerhub>/fraud-backend` and `…/fraud-frontend` with `:$IMAGE_TAG` and `:latest`, in parallel.
4. `kubectl set image …:$IMAGE_TAG` + `kubernetes.io/change-cause` annotation, then `kubectl rollout status --timeout=900s` (minikube may need minutes to pull the backend image); on failure, `kubectl rollout undo` and exit 1.

The `dvc pull` calls in this pipeline use `--force`: Jenkins reuses the workspace, and the previous build's `--export-champion` rewrote `metadata.json`, so a plain `dvc pull` refuses to overwrite it and every build after the first fails.

The frontend is built with `--build-arg NEXT_PUBLIC_API_URL=http://api.fraud.local`. `NEXT_PUBLIC_*` values are baked in at build time (docker-compose passes it as a build arg too); there is no frontend ConfigMap.

The Jenkins agent image is `jenkins/Dockerfile`. It provides Python 3.11 in `/opt/venv-fraud` (root `requirements.txt` + `evidently>=0.7,<0.8`), the docker CLI, and kubectl.

### Backend state and monitoring
- `/live` always returns 200 (livenessProbe); `/health` returns **503** until model and preprocessor are loaded (readinessProbe, Dockerfile HEALTHCHECK, compose `service_healthy`).
- **Drift state lives in memory** (`drift_state` dict in `api.py`). Jenkins pushes it over HTTP, and a pod restart wipes it. On startup the app tries to restore it from `DRIFT_STATE_DIR` (default `<root>/artifacts/jenkins`); nothing is mounted there in k8s.
- `/stream` is a Server-Sent Events feed for the frontend Live page. `/predict` (not `/predictCSV`) calls `_publish_live()`, which pushes one event per transaction to every subscriber queue (`live_subscribers`) and keeps the last 20 in `live_events`, replayed to each new client. `TransactionInput.merchant` / `.name` are display-only and excluded from the model input (`DISPLAY_ONLY_FIELDS`). The response sets `X-Accel-Buffering: no` so the nginx Ingress doesn't buffer it, and a `: keep-alive` comment goes out every 15 s. Like the drift state, it's per pod and in memory. `scripts/simulate_live_traffic.py` replays real transactions against `/predict` for demos.
- `/update-drift-metrics` and `/upload-drift-report` depend on `require_admin_token`: enforced only when `API_ADMIN_TOKEN` is set (k8s: optional secret `fraud-api-secrets`). `/update-test-metrics` was removed; CI results go to the Pushgateway.
- Prometheus metrics (`fraud_*`) are exposed at `/metrics` via `make_asgi_app()` and scraped by `k8s/monitoring/servicemonitor-backend.yaml`. `fraud_rate_current` is the fraud share of the last 1000 predictions; `fraud_prediction_latency_seconds` only measures `/predict` (CSV batches go to `fraud_http_request_latency_seconds`). Alert rules are in `prometheusrule-fraud.yaml` (`HighFraudRate` uses a 10-minute ratio of the counter with a 20-prediction minimum).
- `/metrics-summary` reads metric values through `collect()` (no private `_value`), estimates p50/p95/p99 with `histogram_quantile()` (PromQL-style interpolation), and queries `PROMETHEUS_URL` (default: the in-cluster kube-prometheus service; empty disables it) for pod, CPU, and memory stats.

### Networking and hard-coded endpoints
- Ingress hosts: `fraud.local` routes to the frontend and `api.fraud.local` to the backend.
- The backend Service is a NodePort on **30080**. Jenkins reaches it at `API_URL=http://192.168.49.2:30080` and the Pushgateway at `PUSHGATEWAY_URL=http://192.168.49.2:30091`, both set in the `environment` block of `Jenkinsfile.ml.txt` (minikube IP). Update them when the cluster changes.
- The Jenkins container joins the `minikube` Docker network with a **fixed IP `192.168.49.100`**. Without it, Jenkins can start first after a reboot and take `192.168.49.2`, and `minikube start` then fails with `Address already in use`.
- CORS allow-list in `api.py`: `CORS_ORIGINS` env, default `localhost:3000`, `127.0.0.1:3000`, `fraud.local`.
- `frontend/src/services/api.ts` covers predict (reads `probabilities`), CSV batch, and health. `app/monitoring/page.tsx` fetches the drift, metadata, health, and metrics-summary endpoints directly, and embeds `/drift-report` in an iframe.

## Slides conventions (source folder, outside this repo)

- `main.tex` holds the preamble and the `\input`s for `sections/NN_*.tex`.
- The custom theme is `style/beamerthememlops.sty`:
  - boxes: `keybox`, `warnbox`, `okbox`, `projbox` ("Dans notre projet"), each taking `[title={…}]`;
  - macros: `\hl{}`, `\nv{}`, `\code{}`, `\rubrique{}`, `\ok`, `\nok`, `\warn`;
  - TikZ styles: `box`, `boxn`, `boxa`, `boxg`, `boxb`, `grp`, `fl`, `fla`, `lbl`;
  - a `P{width}` column type;
  - `listings` styles for Python, YAML, Groovy, Dockerfile, and shell.
- Section files use UTF-8 accents directly, **except inside `lstlisting` blocks**: non-ASCII characters there (accents, « ») break pdflatex. Frames are mostly `\footnotesize` two-column layouts.
- It compiles with plain `pdflatex`, without `-shell-escape`.
- Run `make qa` after editing to catch vertical overflow.
- Project figures quoted in the slides (dataset sizes, ROC-AUC 0.9992, drift threshold, and so on) are listed in the slides' `README.md`. Keep the slides consistent with that table and with the code.
