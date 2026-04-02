import pytest
from src.calibration import (
    brier_score, brier_score_totals, log_loss,
    calibration_buckets, generate_report,
)


def _make_predictions():
    """Predicciones de ejemplo para tests."""
    return [
        {"prob_home": 0.60, "prob_draw": 0.25, "prob_away": 0.15,
         "prob_over25": 0.55, "actual_result": "H", "home_goals": 2, "away_goals": 1},
        {"prob_home": 0.40, "prob_draw": 0.30, "prob_away": 0.30,
         "prob_over25": 0.50, "actual_result": "D", "home_goals": 1, "away_goals": 1},
        {"prob_home": 0.20, "prob_draw": 0.25, "prob_away": 0.55,
         "prob_over25": 0.65, "actual_result": "A", "home_goals": 0, "away_goals": 2},
        {"prob_home": 0.70, "prob_draw": 0.18, "prob_away": 0.12,
         "prob_over25": 0.60, "actual_result": "H", "home_goals": 3, "away_goals": 0},
        {"prob_home": 0.35, "prob_draw": 0.30, "prob_away": 0.35,
         "prob_over25": 0.45, "actual_result": "D", "home_goals": 0, "away_goals": 0},
    ]


# ── Brier Score ───────────────────────────────────────────

def test_brier_score_perfect():
    """Predicciones perfectas → Brier = 0."""
    predictions = [
        {"prob_home": 1.0, "prob_draw": 0.0, "prob_away": 0.0, "actual_result": "H"},
        {"prob_home": 0.0, "prob_draw": 1.0, "prob_away": 0.0, "actual_result": "D"},
        {"prob_home": 0.0, "prob_draw": 0.0, "prob_away": 1.0, "actual_result": "A"},
    ]
    assert brier_score(predictions) == 0.0


def test_brier_score_worst():
    """Predicciones inversas → Brier alto."""
    predictions = [
        {"prob_home": 0.0, "prob_draw": 0.0, "prob_away": 1.0, "actual_result": "H"},
    ]
    assert brier_score(predictions) == 2.0  # (0-1)² + (0-0)² + (1-0)² = 2


def test_brier_score_random():
    """Predicciones uniformes (1/3) → Brier ≈ 0.667 (3 outcomes sumados)."""
    predictions = [
        {"prob_home": 1/3, "prob_draw": 1/3, "prob_away": 1/3, "actual_result": r}
        for r in ["H", "D", "A"] * 10
    ]
    bs = brier_score(predictions)
    # 3-outcome Brier: cada outcome contribuye (1/3 - actual)²
    # Para el correcto: (1/3 - 1)² = 4/9; para los otros 2: (1/3 - 0)² × 2 = 2/9
    # Total = 4/9 + 2/9 = 6/9 = 0.667
    assert 0.60 < bs < 0.70


def test_brier_score_realistic():
    """Predicciones realistas → Brier < azar (0.667)."""
    predictions = _make_predictions()
    bs = brier_score(predictions)
    assert 0 < bs < 0.667  # Mejor que azar


def test_brier_score_empty():
    assert brier_score([]) == 0.0


# ── Brier Score Totals ────────────────────────────────────

def test_brier_totals():
    predictions = _make_predictions()
    bs = brier_score_totals(predictions)
    assert 0 < bs < 0.5


def test_brier_totals_perfect():
    predictions = [
        {"prob_over25": 1.0, "home_goals": 2, "away_goals": 1},
        {"prob_over25": 0.0, "home_goals": 1, "away_goals": 0},
    ]
    assert brier_score_totals(predictions) == 0.0


# ── Log-Loss ──────────────────────────────────────────────

def test_log_loss_good_predictions():
    """Predicciones buenas → log-loss bajo."""
    predictions = _make_predictions()
    ll = log_loss(predictions)
    assert 0 < ll < 5.0


def test_log_loss_empty():
    assert log_loss([]) == 0.0


def test_log_loss_worse_than_good():
    """Predicciones malas tienen mayor log-loss que buenas."""
    good = [{"prob_home": 0.80, "prob_draw": 0.10, "prob_away": 0.10, "actual_result": "H"}]
    bad = [{"prob_home": 0.10, "prob_draw": 0.10, "prob_away": 0.80, "actual_result": "H"}]
    assert log_loss(bad) > log_loss(good)


# ── Calibration Buckets ───────────────────────────────────

def test_calibration_buckets_exist():
    predictions = _make_predictions()
    buckets = calibration_buckets(predictions)
    assert len(buckets) > 0


def test_calibration_buckets_have_counts():
    predictions = _make_predictions()
    buckets = calibration_buckets(predictions)
    total_count = sum(b.count for b in buckets)
    # 5 predicciones × 3 outcomes = 15 pares
    assert total_count == 15


def test_calibration_bucket_ranges():
    predictions = _make_predictions()
    buckets = calibration_buckets(predictions, bucket_size=0.20)
    for b in buckets:
        assert b.range_low < b.range_high
        assert 0 <= b.predicted_avg <= 1
        assert 0 <= b.actual_rate <= 1


# ── Full Report ───────────────────────────────────────────

def test_generate_report():
    predictions = _make_predictions()
    report = generate_report(predictions)

    assert report.total_predictions == 5
    assert report.brier_score > 0
    assert report.log_loss > 0
    assert len(report.buckets_1x2) > 0
