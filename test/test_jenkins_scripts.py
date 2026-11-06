"""
Tests des règles de décision des scripts Jenkins (sans MLflow ni données réelles).

    pytest test/test_jenkins_scripts.py
"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "jenkins"))

# register_best_model importe mlflow au chargement : un mock suffit pour tester la règle
for module in ("mlflow", "mlflow.sklearn", "mlflow.tracking"):
    sys.modules.setdefault(module, MagicMock())

from register_best_model import decide_promotion  # noqa: E402
from validate_data import validate  # noqa: E402

KNOWN_CATEGORIES = ["grocery_pos", "shopping_net", "travel"]


def valid_frame(n=20):
    return pd.DataFrame({
        "trans_date_trans_time": ["2019-01-01 10:00:00"] * n,
        "category": ["grocery_pos"] * n,
        "amt": [42.0] * n,
        "gender": ["F", "M"] * (n // 2),
        "city_pop": [1500] * n,
        "lat": [40.0] * n, "long": [-74.0] * n,
        "merch_lat": [40.1] * n, "merch_long": [-74.1] * n,
        "dob": ["1990-05-01"] * n,
        "is_fraud": [0] * (n - 1) + [1],
    })


# ---------------------------------------------------------------- champion / challenger

def test_promotion_without_champion():
    promoted, _ = decide_promotion("run-b", 0.80, None, None)
    assert promoted


def test_promotion_when_challenger_is_better():
    promoted, _ = decide_promotion("run-b", 0.85, "run-a", 0.80)
    assert promoted


def test_no_promotion_when_challenger_is_worse_or_equal():
    assert not decide_promotion("run-b", 0.79, "run-a", 0.80)[0]
    assert not decide_promotion("run-b", 0.80, "run-a", 0.80)[0]


def test_margin_is_respected():
    assert not decide_promotion("run-b", 0.805, "run-a", 0.80, min_improvement=0.01)[0]
    assert decide_promotion("run-b", 0.82, "run-a", 0.80, min_improvement=0.01)[0]


def test_same_run_is_not_promoted_twice():
    assert not decide_promotion("run-a", 0.90, "run-a", 0.90)[0]


# ---------------------------------------------------------------- validation des données

def test_valid_data_passes():
    assert validate(valid_frame(), KNOWN_CATEGORIES, min_rows=10) == []


def test_missing_column_is_blocking():
    errors = validate(valid_frame().drop(columns=["amt"]), KNOWN_CATEGORIES, min_rows=10)
    assert errors and "colonnes manquantes" in errors[0]


def test_corrupted_values_are_reported():
    df = valid_frame()
    df.loc[0, "amt"] = -5
    df.loc[1, "merch_lat"] = 123.0
    df.loc[2, "category"] = "crypto"
    df.loc[3, "is_fraud"] = 2
    df.loc[4, "dob"] = "pas une date"
    errors = " | ".join(validate(df, KNOWN_CATEGORIES, min_rows=10))
    for expected in ["amt", "merch_lat", "crypto", "is_fraud", "dob"]:
        assert expected in errors


def test_too_few_rows_is_blocking():
    assert validate(valid_frame(4), KNOWN_CATEGORIES, min_rows=10)
