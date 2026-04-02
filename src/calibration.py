"""
WinStake.ia — Métricas de Calibración del Modelo
Evalúa si las probabilidades predichas se corresponden con la realidad.

Métricas:
- Brier Score: Error cuadrático medio de las probabilidades (0 = perfecto, 0.25 = azar)
- Log-Loss: Penaliza fuertemente predicciones confiantes que fallan
- Calibración por buckets: ¿Cuando dices 60%, gana realmente el 60%?
"""

import math
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class CalibrationBucket:
    """Un bucket de calibración (ej: predicciones entre 50-60%)."""
    range_low: float
    range_high: float
    predicted_avg: float = 0.0
    actual_rate: float = 0.0
    count: int = 0
    label: str = ""


@dataclass
class CalibrationReport:
    """Reporte completo de calibración del modelo."""
    brier_score: float = 0.0
    brier_score_1x2: float = 0.0
    brier_score_totals: float = 0.0
    log_loss: float = 0.0
    total_predictions: int = 0
    buckets_1x2: list = field(default_factory=list)
    buckets_totals: list = field(default_factory=list)


def brier_score(predictions: list[dict]) -> float:
    """
    Calcula el Brier Score para predicciones 1X2.

    Brier Score = (1/N) * Σ (predicted_prob - actual_outcome)²

    Donde actual_outcome = 1 si el evento ocurrió, 0 si no.
    Rango: 0 (perfecto) a 1 (peor posible). Azar en 3 outcomes = 0.222
    """
    if not predictions:
        return 0.0

    total_error = 0.0
    n = 0

    for p in predictions:
        result = p.get("actual_result", "")
        if not result:
            continue

        actual_home = 1.0 if result == "H" else 0.0
        actual_draw = 1.0 if result == "D" else 0.0
        actual_away = 1.0 if result == "A" else 0.0

        total_error += (p["prob_home"] - actual_home) ** 2
        total_error += (p["prob_draw"] - actual_draw) ** 2
        total_error += (p["prob_away"] - actual_away) ** 2
        n += 1

    return round(total_error / n, 4) if n > 0 else 0.0


def brier_score_totals(predictions: list[dict]) -> float:
    """Brier Score para Over/Under 2.5."""
    if not predictions:
        return 0.0

    total_error = 0.0
    n = 0

    for p in predictions:
        hg = p.get("home_goals")
        ag = p.get("away_goals")
        prob_over = p.get("prob_over25", 0)
        if hg is None or ag is None or prob_over == 0:
            continue

        actual_over = 1.0 if (hg + ag) > 2 else 0.0
        total_error += (prob_over - actual_over) ** 2
        total_error += ((1 - prob_over) - (1 - actual_over)) ** 2
        n += 1

    return round(total_error / n, 4) if n > 0 else 0.0


def log_loss(predictions: list[dict]) -> float:
    """
    Calcula Log-Loss para predicciones 1X2.

    Log-Loss = -(1/N) * Σ [y * log(p) + (1-y) * log(1-p)]
    Penaliza predicciones confiantes que fallan.
    """
    if not predictions:
        return 0.0

    eps = 1e-15  # Para evitar log(0)
    total = 0.0
    n = 0

    for p in predictions:
        result = p.get("actual_result", "")
        if not result:
            continue

        probs = [
            max(eps, min(1 - eps, p["prob_home"])),
            max(eps, min(1 - eps, p["prob_draw"])),
            max(eps, min(1 - eps, p["prob_away"])),
        ]
        actuals = [
            1.0 if result == "H" else 0.0,
            1.0 if result == "D" else 0.0,
            1.0 if result == "A" else 0.0,
        ]

        for actual, prob in zip(actuals, probs):
            total -= actual * math.log(prob) + (1 - actual) * math.log(1 - prob)
        n += 1

    return round(total / n, 4) if n > 0 else 0.0


def calibration_buckets(
    predictions: list[dict], bucket_size: float = 0.10
) -> list[CalibrationBucket]:
    """
    Agrupa predicciones en buckets y compara probabilidad predicha vs real.

    Ej: De todas las veces que dijimos 60-70% para Local,
    ¿ganó realmente el local ~65% de las veces?
    """
    # Recopilar todos los (prob, actual_outcome) pares
    pairs = []
    for p in predictions:
        result = p.get("actual_result", "")
        if not result:
            continue
        pairs.append((p["prob_home"], 1.0 if result == "H" else 0.0))
        pairs.append((p["prob_draw"], 1.0 if result == "D" else 0.0))
        pairs.append((p["prob_away"], 1.0 if result == "A" else 0.0))

    if not pairs:
        return []

    # Crear buckets
    buckets = []
    low = 0.0
    while low < 1.0:
        high = min(low + bucket_size, 1.0)
        bucket_pairs = [(prob, actual) for prob, actual in pairs if low <= prob < high]

        if bucket_pairs:
            pred_avg = sum(prob for prob, _ in bucket_pairs) / len(bucket_pairs)
            actual_rate = sum(actual for _, actual in bucket_pairs) / len(bucket_pairs)
            buckets.append(CalibrationBucket(
                range_low=low,
                range_high=high,
                predicted_avg=round(pred_avg, 3),
                actual_rate=round(actual_rate, 3),
                count=len(bucket_pairs),
                label=f"{int(low*100)}-{int(high*100)}%",
            ))

        low = high

    return buckets


def calibration_buckets_totals(
    predictions: list[dict], bucket_size: float = 0.10
) -> list[CalibrationBucket]:
    """Calibración por buckets para Over/Under 2.5."""
    pairs = []
    for p in predictions:
        hg = p.get("home_goals")
        ag = p.get("away_goals")
        prob_over = p.get("prob_over25", 0)
        if hg is None or ag is None or prob_over == 0:
            continue
        actual_over = 1.0 if (hg + ag) > 2 else 0.0
        pairs.append((prob_over, actual_over))

    if not pairs:
        return []

    buckets = []
    low = 0.0
    while low < 1.0:
        high = min(low + bucket_size, 1.0)
        bucket_pairs = [(prob, actual) for prob, actual in pairs if low <= prob < high]

        if bucket_pairs:
            pred_avg = sum(prob for prob, _ in bucket_pairs) / len(bucket_pairs)
            actual_rate = sum(actual for _, actual in bucket_pairs) / len(bucket_pairs)
            buckets.append(CalibrationBucket(
                range_low=low,
                range_high=high,
                predicted_avg=round(pred_avg, 3),
                actual_rate=round(actual_rate, 3),
                count=len(bucket_pairs),
                label=f"{int(low*100)}-{int(high*100)}%",
            ))

        low = high

    return buckets


def generate_report(predictions: list[dict]) -> CalibrationReport:
    """Genera reporte completo de calibración."""
    return CalibrationReport(
        brier_score=brier_score(predictions),
        brier_score_1x2=brier_score(predictions),
        brier_score_totals=brier_score_totals(predictions),
        log_loss=log_loss(predictions),
        total_predictions=len([p for p in predictions if p.get("actual_result")]),
        buckets_1x2=calibration_buckets(predictions),
        buckets_totals=calibration_buckets_totals(predictions),
    )


def print_calibration_report(predictions: list[dict]):
    """Imprime reporte de calibración al logger."""
    report = generate_report(predictions)

    logger.info("CALIBRACIÓN DEL MODELO")
    logger.info(f"  Predicciones evaluadas: {report.total_predictions}")
    logger.info(f"  Brier Score (1X2): {report.brier_score_1x2:.4f}  (azar=0.667, perfecto=0)")
    logger.info(f"  Brier Score (O/U): {report.brier_score_totals:.4f}  (azar=0.250, perfecto=0)")
    logger.info(f"  Log-Loss: {report.log_loss:.4f}")

    if report.buckets_1x2:
        logger.info(f"\n  Calibración 1X2 (predicho vs real):")
        logger.info(f"  {'Rango':<12} {'Predicho':>10} {'Real':>10} {'N':>6} {'Error':>8}")
        for b in report.buckets_1x2:
            error = abs(b.predicted_avg - b.actual_rate)
            bar = "+" if b.actual_rate > b.predicted_avg else "-"
            logger.info(
                f"  {b.label:<12} {b.predicted_avg*100:>9.1f}% {b.actual_rate*100:>9.1f}% "
                f"{b.count:>5}  {bar}{error*100:.1f}%"
            )

    if report.buckets_totals:
        logger.info(f"\n  Calibración Over 2.5 (predicho vs real):")
        for b in report.buckets_totals:
            error = abs(b.predicted_avg - b.actual_rate)
            logger.info(
                f"  {b.label:<12} {b.predicted_avg*100:>9.1f}% {b.actual_rate*100:>9.1f}% "
                f"{b.count:>5}"
            )

    return report
