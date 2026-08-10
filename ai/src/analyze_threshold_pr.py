from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    average_precision_score,
)


# ============================================================
# 1. 경로 설정
# ============================================================

AI_ROOT = Path(__file__).resolve().parent.parent

PREDICTION_PATH = (
    AI_ROOT
    / "results"
    / "model_comparison"
    / "final_text_clf_hard_predictions.csv"
)

RESULT_DIR = (
    AI_ROOT
    / "results"
    / "threshold_analysis"
)

RESULT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. 데이터 로딩
# ============================================================

def load_predictions() -> pd.DataFrame:

    if not PREDICTION_PATH.exists():
        raise FileNotFoundError(
            f"예측 파일이 없습니다:\n{PREDICTION_PATH}"
        )

    df = pd.read_csv(
        PREDICTION_PATH,
        encoding="utf-8-sig",
    )

    required_columns = {
        "label",
        "phishing_probability",
    }

    missing = (
        required_columns
        - set(df.columns)
    )

    if missing:
        raise ValueError(
            f"필수 컬럼이 없습니다: {sorted(missing)}"
        )

    df = df.dropna(
        subset=[
            "label",
            "phishing_probability",
        ]
    ).copy()

    df["label"] = (
        df["label"]
        .astype(int)
    )

    df["phishing_probability"] = (
        df["phishing_probability"]
        .astype(float)
    )

    print("=" * 80)
    print("HARD 예측 결과 로딩")
    print("=" * 80)

    print("전체:", len(df))

    print("\nLabel 분포")
    print(
        df["label"]
        .value_counts()
        .sort_index()
    )

    return df.reset_index(
        drop=True
    )


# ============================================================
# 3. 특정 threshold 평가
# ============================================================

def evaluate_threshold(
    labels: np.ndarray,
    probabilities: np.ndarray,
    threshold: float,
) -> dict:

    predictions = (
        probabilities
        >= threshold
    ).astype(int)

    tn, fp, fn, tp = (
        confusion_matrix(
            labels,
            predictions,
            labels=[0, 1],
        )
        .ravel()
    )

    return {
        "threshold": float(threshold),

        "accuracy": accuracy_score(
            labels,
            predictions,
        ),

        "precision": precision_score(
            labels,
            predictions,
            zero_division=0,
        ),

        "recall": recall_score(
            labels,
            predictions,
            zero_division=0,
        ),

        "f1": f1_score(
            labels,
            predictions,
            zero_division=0,
        ),

        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }


# ============================================================
# 4. 전체 threshold sweep
# ============================================================

def build_threshold_table(
    labels: np.ndarray,
    probabilities: np.ndarray,
) -> pd.DataFrame:

    thresholds = np.round(
        np.arange(
            0.05,
            0.951,
            0.01,
        ),
        2,
    )

    rows = []

    for threshold in thresholds:

        rows.append(
            evaluate_threshold(
                labels=labels,
                probabilities=probabilities,
                threshold=float(threshold),
            )
        )

    return pd.DataFrame(
        rows
    )


# ============================================================
# 5. 추천 threshold 선택
# ============================================================

def select_recommended_thresholds(
    threshold_df: pd.DataFrame,
) -> pd.DataFrame:

    recommendations = []

    # --------------------------------------------------------
    # A. F1 최대
    # --------------------------------------------------------

    best_f1_row = (
        threshold_df
        .sort_values(
            by=[
                "f1",
                "recall",
                "precision",
            ],
            ascending=False,
        )
        .iloc[0]
    )

    recommendations.append(
        {
            "strategy": "best_f1",
            "description": "F1 최대 threshold",
            **best_f1_row.to_dict(),
        }
    )

    # --------------------------------------------------------
    # B. Recall 95% 이상 중 Precision 최대
    # --------------------------------------------------------

    recall_95 = threshold_df[
        threshold_df["recall"]
        >= 0.95
    ].copy()

    if not recall_95.empty:

        row = (
            recall_95
            .sort_values(
                by=[
                    "precision",
                    "f1",
                    "threshold",
                ],
                ascending=False,
            )
            .iloc[0]
        )

        recommendations.append(
            {
                "strategy": "recall_at_least_0.95",
                "description": "Recall 95% 이상 중 Precision 최대",
                **row.to_dict(),
            }
        )

    # --------------------------------------------------------
    # C. Recall 98% 이상 중 Precision 최대
    # --------------------------------------------------------

    recall_98 = threshold_df[
        threshold_df["recall"]
        >= 0.98
    ].copy()

    if not recall_98.empty:

        row = (
            recall_98
            .sort_values(
                by=[
                    "precision",
                    "f1",
                    "threshold",
                ],
                ascending=False,
            )
            .iloc[0]
        )

        recommendations.append(
            {
                "strategy": "recall_at_least_0.98",
                "description": "Recall 98% 이상 중 Precision 최대",
                **row.to_dict(),
            }
        )

    # --------------------------------------------------------
    # D. 현재 threshold 0.5
    # --------------------------------------------------------

    current_row = (
        threshold_df[
            np.isclose(
                threshold_df[
                    "threshold"
                ],
                0.5,
            )
        ]
    )

    if not current_row.empty:

        row = current_row.iloc[0]

        recommendations.append(
            {
                "strategy": "current_0.5",
                "description": "현재 기준 threshold 0.5",
                **row.to_dict(),
            }
        )

    return pd.DataFrame(
        recommendations
    )


# ============================================================
# 6. PR Curve 데이터
# ============================================================

def build_pr_curve(
    labels: np.ndarray,
    probabilities: np.ndarray,
) -> pd.DataFrame:

    precision, recall, thresholds = (
        precision_recall_curve(
            labels,
            probabilities,
        )
    )

    # 마지막 precision/recall 값에는 threshold가 없음
    pr_df = pd.DataFrame(
        {
            "threshold": thresholds,
            "precision": precision[:-1],
            "recall": recall[:-1],
        }
    )

    pr_df["f1"] = (
        2
        * pr_df["precision"]
        * pr_df["recall"]
        / (
            pr_df["precision"]
            + pr_df["recall"]
            + 1e-12
        )
    )

    return pr_df


# ============================================================
# 7. 전체 실행
# ============================================================

def main() -> None:

    df = load_predictions()

    labels = (
        df["label"]
        .to_numpy()
    )

    probabilities = (
        df["phishing_probability"]
        .to_numpy()
    )

    # --------------------------------------------------------
    # PR-AUC
    # --------------------------------------------------------

    pr_auc = (
        average_precision_score(
            labels,
            probabilities,
        )
    )

    print(
        "\nPR-AUC:",
        round(
            float(pr_auc),
            6,
        ),
    )

    # --------------------------------------------------------
    # Threshold 전체 비교
    # --------------------------------------------------------

    threshold_df = (
        build_threshold_table(
            labels=labels,
            probabilities=probabilities,
        )
    )

    threshold_path = (
        RESULT_DIR
        / "threshold_sweep.csv"
    )

    threshold_df.to_csv(
        threshold_path,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # 추천 threshold
    # --------------------------------------------------------

    recommendation_df = (
        select_recommended_thresholds(
            threshold_df
        )
    )

    recommendation_df[
        "pr_auc"
    ] = float(
        pr_auc
    )

    recommendation_path = (
        RESULT_DIR
        / "recommended_thresholds.csv"
    )

    recommendation_df.to_csv(
        recommendation_path,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # PR Curve 데이터 저장
    # --------------------------------------------------------

    pr_df = (
        build_pr_curve(
            labels=labels,
            probabilities=probabilities,
        )
    )

    pr_path = (
        RESULT_DIR
        / "pr_curve.csv"
    )

    pr_df.to_csv(
        pr_path,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # 출력
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 100
    )

    print(
        "추천 Threshold 비교"
    )

    print(
        "=" * 100
    )

    display_columns = [
        "strategy",
        "description",
        "threshold",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "fp",
        "fn",
        "tp",
        "tn",
    ]

    print(
        recommendation_df[
            display_columns
        ].to_string(
            index=False
        )
    )

    print(
        "\nThreshold 전체 결과 저장:"
    )

    print(
        threshold_path
    )

    print(
        "\n추천 Threshold 저장:"
    )

    print(
        recommendation_path
    )

    print(
        "\nPR Curve 저장:"
    )

    print(
        pr_path
    )

    print(
        "\n완료."
    )


if __name__ == "__main__":
    main()