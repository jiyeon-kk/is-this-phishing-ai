from __future__ import annotations

from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score


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
    / "hard_error_analysis"
)

RESULT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. 데이터 로딩
# ============================================================

def load_data() -> pd.DataFrame:

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
        "predicted_label",
        "phishing_probability",
        "scenario",
        "subtype",
        "content",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"필수 컬럼이 없습니다: {sorted(missing)}"
        )

    df["label"] = df["label"].astype(int)
    df["predicted_label"] = df["predicted_label"].astype(int)

    df["is_correct"] = (
        df["label"]
        == df["predicted_label"]
    )

    df["error_type"] = "CORRECT"

    df.loc[
        (df["label"] == 0)
        & (df["predicted_label"] == 1),
        "error_type",
    ] = "FP"

    df.loc[
        (df["label"] == 1)
        & (df["predicted_label"] == 0),
        "error_type",
    ] = "FN"

    return df


# ============================================================
# 3. 그룹별 성능 계산 함수
# ============================================================

def summarize_group(
    df: pd.DataFrame,
    group_col: str,
) -> pd.DataFrame:

    rows = []

    for group_value, group_df in df.groupby(group_col):

        total = len(group_df)

        correct = int(
            group_df["is_correct"].sum()
        )

        fp = int(
            (
                (group_df["label"] == 0)
                & (group_df["predicted_label"] == 1)
            ).sum()
        )

        fn = int(
            (
                (group_df["label"] == 1)
                & (group_df["predicted_label"] == 0)
            ).sum()
        )

        normal_count = int(
            (group_df["label"] == 0).sum()
        )

        phishing_count = int(
            (group_df["label"] == 1).sum()
        )

        rows.append(
            {
                group_col: group_value,
                "total": total,
                "correct": correct,
                "accuracy": (
                    correct / total
                    if total > 0
                    else 0.0
                ),
                "normal_count": normal_count,
                "phishing_count": phishing_count,
                "fp": fp,
                "fn": fn,
                "total_errors": fp + fn,
                "fp_rate_within_normal": (
                    fp / normal_count
                    if normal_count > 0
                    else 0.0
                ),
                "fn_rate_within_phishing": (
                    fn / phishing_count
                    if phishing_count > 0
                    else 0.0
                ),
            }
        )

    result = pd.DataFrame(rows)

    return result.sort_values(
        by=[
            "total_errors",
            "accuracy",
        ],
        ascending=[
            False,
            True,
        ],
    ).reset_index(drop=True)


# ============================================================
# 4. 전체 오분류 요약
# ============================================================

def build_overall_summary(
    df: pd.DataFrame,
) -> pd.DataFrame:

    total = len(df)

    correct = int(
        df["is_correct"].sum()
    )

    fp = int(
        (
            (df["label"] == 0)
            & (df["predicted_label"] == 1)
        ).sum()
    )

    fn = int(
        (
            (df["label"] == 1)
            & (df["predicted_label"] == 0)
        ).sum()
    )

    return pd.DataFrame(
        [
            {
                "total": total,
                "correct": correct,
                "accuracy": accuracy_score(
                    df["label"],
                    df["predicted_label"],
                ),
                "fp": fp,
                "fn": fn,
                "total_errors": fp + fn,
            }
        ]
    )


# ============================================================
# 5. FP / FN 상세 사례 추출
# ============================================================

def extract_error_examples(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:

    fp_df = df[
        df["error_type"] == "FP"
    ].copy()

    fn_df = df[
        df["error_type"] == "FN"
    ].copy()

    # FP:
    # 정상인데 피싱 확률이 높은 순
    fp_df = fp_df.sort_values(
        by="phishing_probability",
        ascending=False,
    )

    # FN:
    # 실제 피싱인데 피싱 확률이 낮은 순
    fn_df = fn_df.sort_values(
        by="phishing_probability",
        ascending=True,
    )

    preferred_columns = [
        "id",
        "pair_id",
        "scenario",
        "subtype",
        "content",
        "text",
        "label",
        "predicted_label",
        "phishing_probability",
        "hard_reason",
        "error_type",
    ]

    existing_columns = [
        col
        for col in preferred_columns
        if col in df.columns
    ]

    return (
        fp_df[existing_columns],
        fn_df[existing_columns],
    )


# ============================================================
# 6. 취약 유형 TOP 생성
# ============================================================

def build_top_weaknesses(
    scenario_df: pd.DataFrame,
    subtype_df: pd.DataFrame,
) -> pd.DataFrame:

    records = []

    for _, row in scenario_df.iterrows():
        records.append(
            {
                "level": "scenario",
                "category": row["scenario"],
                "total": row["total"],
                "accuracy": row["accuracy"],
                "fp": row["fp"],
                "fn": row["fn"],
                "total_errors": row["total_errors"],
                "fp_rate_within_normal": row[
                    "fp_rate_within_normal"
                ],
                "fn_rate_within_phishing": row[
                    "fn_rate_within_phishing"
                ],
            }
        )

    for _, row in subtype_df.iterrows():
        records.append(
            {
                "level": "subtype",
                "category": row["subtype"],
                "total": row["total"],
                "accuracy": row["accuracy"],
                "fp": row["fp"],
                "fn": row["fn"],
                "total_errors": row["total_errors"],
                "fp_rate_within_normal": row[
                    "fp_rate_within_normal"
                ],
                "fn_rate_within_phishing": row[
                    "fn_rate_within_phishing"
                ],
            }
        )

    result = pd.DataFrame(records)

    return result.sort_values(
        by=[
            "total_errors",
            "accuracy",
        ],
        ascending=[
            False,
            True,
        ],
    ).reset_index(drop=True)


# ============================================================
# 7. 실행
# ============================================================

def main() -> None:

    df = load_data()

    overall_df = build_overall_summary(
        df
    )

    scenario_df = summarize_group(
        df,
        "scenario",
    )

    subtype_df = summarize_group(
        df,
        "subtype",
    )

    fp_df, fn_df = extract_error_examples(
        df
    )

    weakness_df = build_top_weaknesses(
        scenario_df,
        subtype_df,
    )

    # --------------------------------------------------------
    # 저장
    # --------------------------------------------------------

    overall_path = (
        RESULT_DIR
        / "overall_error_summary.csv"
    )

    scenario_path = (
        RESULT_DIR
        / "scenario_error_analysis.csv"
    )

    subtype_path = (
        RESULT_DIR
        / "subtype_error_analysis.csv"
    )

    fp_path = (
        RESULT_DIR
        / "false_positive_examples.csv"
    )

    fn_path = (
        RESULT_DIR
        / "false_negative_examples.csv"
    )

    weakness_path = (
        RESULT_DIR
        / "top_weaknesses.csv"
    )

    overall_df.to_csv(
        overall_path,
        index=False,
        encoding="utf-8-sig",
    )

    scenario_df.to_csv(
        scenario_path,
        index=False,
        encoding="utf-8-sig",
    )

    subtype_df.to_csv(
        subtype_path,
        index=False,
        encoding="utf-8-sig",
    )

    fp_df.to_csv(
        fp_path,
        index=False,
        encoding="utf-8-sig",
    )

    fn_df.to_csv(
        fn_path,
        index=False,
        encoding="utf-8-sig",
    )

    weakness_df.to_csv(
        weakness_path,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # 화면 출력
    # --------------------------------------------------------

    print("=" * 100)
    print("HARD 오분류 전체 요약")
    print("=" * 100)

    print(
        overall_df.to_string(
            index=False
        )
    )

    print(
        "\n"
        + "=" * 100
    )
    print(
        "시나리오별 성능"
    )
    print(
        "=" * 100
    )

    print(
        scenario_df.to_string(
            index=False
        )
    )

    print(
        "\n"
        + "=" * 100
    )
    print(
        "오분류 많은 subtype TOP 15"
    )
    print(
        "=" * 100
    )

    print(
        subtype_df.head(15).to_string(
            index=False
        )
    )

    print(
        "\n"
        + "=" * 100
    )
    print(
        "전체 취약 유형 TOP 20"
    )
    print(
        "=" * 100
    )

    print(
        weakness_df.head(20).to_string(
            index=False
        )
    )

    print(
        "\n"
        + "=" * 100
    )
    print(
        "False Positive 상위 10개"
    )
    print(
        "=" * 100
    )

    fp_display_cols = [
        col
        for col in [
            "scenario",
            "subtype",
            "phishing_probability",
            "content",
        ]
        if col in fp_df.columns
    ]

    print(
        fp_df[
            fp_display_cols
        ]
        .head(10)
        .to_string(
            index=False
        )
    )

    print(
        "\n"
        + "=" * 100
    )
    print(
        "False Negative 상위 10개"
    )
    print(
        "=" * 100
    )

    fn_display_cols = [
        col
        for col in [
            "scenario",
            "subtype",
            "phishing_probability",
            "content",
        ]
        if col in fn_df.columns
    ]

    print(
        fn_df[
            fn_display_cols
        ]
        .head(10)
        .to_string(
            index=False
        )
    )

    print(
        "\n저장 완료:"
    )

    print(
        f"- {overall_path}"
    )
    print(
        f"- {scenario_path}"
    )
    print(
        f"- {subtype_path}"
    )
    print(
        f"- {fp_path}"
    )
    print(
        f"- {fn_path}"
    )
    print(
        f"- {weakness_path}"
    )


if __name__ == "__main__":
    main()