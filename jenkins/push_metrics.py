"""
Pousse les métriques du pipeline ML Jenkins vers le Prometheus Pushgateway.

    python3 jenkins/push_metrics.py 1   # build réussi
    python3 jenkins/push_metrics.py 0   # build échoué

Métriques (job="jenkins_ml_pipeline") :
  fraud_jenkins_build_status        1 = succès, 0 = échec (alerte MLPipelineFailed)
  fraud_ci_scenario_detected        fraudes détectées par le test de scénario
  fraud_ci_scenario_total           fraudes testées
  fraud_ci_scenario_detection_rate  détectées / testées
  fraud_ci_model_promoted           1 si un nouveau champion a été promu

Les résultats du test de scénario vont au Pushgateway et non à l'API : ce sont
des mesures de CI, elles ne doivent pas se mélanger aux métriques du trafic réel.
"""
import json
import os
import sys
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent.parent
JENKINS_DIR = BASE_DIR / "artifacts" / "jenkins"
PUSHGATEWAY_URL = os.getenv("PUSHGATEWAY_URL", "http://192.168.49.2:30091")


def gauge(name, help_text, value):
    return f"# HELP {name} {help_text}\n# TYPE {name} gauge\n{name} {value}\n"


def build_payload(build_status):
    body = gauge("fraud_jenkins_build_status", "Statut du dernier build du pipeline ML", build_status)

    scenario = JENKINS_DIR / "scenario_test.json"
    if scenario.exists():
        s = json.loads(scenario.read_text())
        body += gauge("fraud_ci_scenario_detected", "Fraudes détectées par le test de scénario", s["detected"])
        body += gauge("fraud_ci_scenario_total", "Fraudes testées par le test de scénario", s["total"])
        body += gauge("fraud_ci_scenario_detection_rate", "Taux de détection du test de scénario",
                      s["detection_rate"])

    promotion = JENKINS_DIR / "promotion.json"
    if promotion.exists():
        promoted = json.loads(promotion.read_text()).get("promoted", False)
        body += gauge("fraud_ci_model_promoted", "Nouveau champion promu au dernier build", int(promoted))
    return body


def push(build_status: int):
    try:
        resp = requests.post(f"{PUSHGATEWAY_URL}/metrics/job/jenkins_ml_pipeline",
                             data=build_payload(build_status), timeout=5)
        print(f"✅ Métriques poussées vers {PUSHGATEWAY_URL} -> {resp.status_code}")
    except Exception as e:
        # Non bloquant : l'absence de Pushgateway ne doit pas faire échouer le build
        print(f"⚠️ Push vers le Pushgateway impossible : {e}")


if __name__ == '__main__':
    push(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
