from __future__ import annotations

from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

# ============================================================
# 1. 기본 설정
# ============================================================

SEED = 42

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DIR = PROJECT_ROOT / "data" / "raw"
RESULT_DIR = PROJECT_ROOT / "results" / "tfidf_baseline"

TRAIN_PATH = PROCESSED_DIR / "train_real.csv"
VALIDATION_PATH = PROCESSED_DIR / "validation_real.csv"
HARD_PATH = RAW_DIR / "korean_phishing_hard_test_1000.csv"

RESULT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

# ============================================================
# 2. 데이터 읽기
# ============================================================

def read_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"파일을 찾을 수 없습니다: {path}"
        )

    df = pd.read_csv(
        path,
        encoding="utf-8-sig",
    )

    # label 확인
    if "label" not in df.columns:
        raise ValueError(
            f"label 컬럼이 없습니다.\n"
            f"파일: {path}\n"
            f"현재 컬럼: {df.columns.tolist()}"
        )

    # text가 없고 content가 있으면 content 사용
    if "text" not in df.columns:
        if "content" in df.columns:
            df["text"] = df["content"].astype(str)
        else:
            raise ValueError(
                f"text와 content 컬럼이 모두 없습니다.\n"
                f"파일: {path}\n"
                f"현재 컬럼: {df.columns.tolist()}"
            )

    df = df.dropna(
        subset=["text", "label"]
    ).copy()

    df["text"] = (
        df["text"]
        .astype(str)
    )

    df["label"] = (
        df["label"]
        .astype(int)
    )

    return df.reset_index(drop=True)


# ============================================================
# 3. 평가 지표 계산
# ============================================================

def calculate_metrics(
    labels,
    predictions,
    probabilities,
) -> dict:
    tn, fp, fn, tp = confusion_matrix(
        labels,
        predictions,
        labels=[0, 1],
    ).ravel()

    metrics = {
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

    # 양성/음성 둘 다 있을 때만 ROC-AUC 계산
    if len(set(labels)) >= 2:
        metrics["roc_auc"] = roc_auc_score(
            labels,
            probabilities,
        )
    else:
        metrics["roc_auc"] = None

    return metrics


# ============================================================
# 4. 데이터셋 하나 평가
# ============================================================

def evaluate_dataset(
    dataset_name: str,
    df: pd.DataFrame,
    vectorizer: TfidfVectorizer,
    model: LogisticRegression,
) -> dict:

    print("\n" + "=" * 80)
    print(f"{dataset_name.upper()} 평가")
    print("=" * 80)

    X = vectorizer.transform(
        df["text"]
    )

    probabilities = (
        model.predict_proba(
            X
        )[:, 1]
    )

    predictions = (
        probabilities >= 0.5
    ).astype(int)

    metrics = calculate_metrics(
        df["label"].to_numpy(),
        predictions,
        probabilities,
    )

    for key, value in metrics.items():
        if isinstance(value, float):
            print(
                f"{key:>10}: {value:.4f}"
            )
        else:
            print(
                f"{key:>10}: {value}"
            )

    # 예측 결과 저장
    result_df = df.copy()

    result_df[
        "phishing_probability"
    ] = probabilities

    result_df[
        "prediction"
    ] = predictions

    result_df[
        "is_correct"
    ] = (
        result_df["label"]
        == result_df["prediction"]
    )

    prediction_path = (
        RESULT_DIR
        / f"{dataset_name}_predictions.csv"
    )

    result_df.to_csv(
        prediction_path,
        index=False,
        encoding="utf-8-sig",
    )

    print(
        "\n예측 결과 저장:",
        prediction_path,
    )

    return {
        "model": "TF-IDF + Logistic Regression",
        "dataset": dataset_name,
        "rows": len(df),
        **metrics,
    }


# ============================================================
# 5. 메인 실행
# ============================================================

def main() -> None:

    print("=" * 80)
    print("TF-IDF + Logistic Regression Baseline")
    print("=" * 80)

    # --------------------------------------------------------
    # 데이터 불러오기
    # --------------------------------------------------------

    print("\n[1] 데이터 불러오기")

    train_df = read_dataset(
        TRAIN_PATH
    )

    validation_df = read_dataset(
        VALIDATION_PATH
    )

    hard_df = read_dataset(
        HARD_PATH
    )

    print(
        f"Train: {len(train_df):,}건"
    )

    print(
        f"Validation: {len(validation_df):,}건"
    )

    print(
        f"HARD: {len(hard_df):,}건"
    )

    print("\nTrain label 분포")
    print(
        train_df["label"]
        .value_counts()
        .sort_index()
    )

    print("\nValidation label 분포")
    print(
        validation_df["label"]
        .value_counts()
        .sort_index()
    )

    print("\nHARD label 분포")
    print(
        hard_df["label"]
        .value_counts()
        .sort_index()
    )

    # --------------------------------------------------------
    # TF-IDF
    # --------------------------------------------------------

    print("\n[2] TF-IDF 학습")

    vectorizer = TfidfVectorizer(
        analyzer="char",
        ngram_range=(2, 4),
        min_df=2,
        max_features=100000,
        sublinear_tf=True,
    )

    X_train = vectorizer.fit_transform(
        train_df["text"]
    )

    print(
        "TF-IDF feature 수:",
        X_train.shape[1],
    )

    # --------------------------------------------------------
    # Logistic Regression
    # --------------------------------------------------------

    print(
        "\n[3] Logistic Regression 학습"
    )

    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        random_state=SEED,
    )

    model.fit(
        X_train,
        train_df["label"],
    )

    # --------------------------------------------------------
    # Validation / HARD 평가
    # --------------------------------------------------------

    print(
        "\n[4] Validation / HARD 평가"
    )

    all_metrics = []

    validation_metrics = evaluate_dataset(
        dataset_name="validation",
        df=validation_df,
        vectorizer=vectorizer,
        model=model,
    )

    all_metrics.append(
        validation_metrics
    )

    hard_metrics = evaluate_dataset(
        dataset_name="hard",
        df=hard_df,
        vectorizer=vectorizer,
        model=model,
    )

    all_metrics.append(
        hard_metrics
    )

    # --------------------------------------------------------
    # 지표 저장
    # --------------------------------------------------------

    metrics_df = pd.DataFrame(
        all_metrics
    )

    metrics_path = (
        RESULT_DIR
        / "tfidf_baseline_comparison.csv"
    )

    metrics_df.to_csv(
        metrics_path,
        index=False,
        encoding="utf-8-sig",
    )

    print("\n" + "=" * 80)
    print("최종 비교표")
    print("=" * 80)

    print(
        metrics_df.to_string(
            index=False
        )
    )

    print(
        "\n평가 지표 저장:",
        metrics_path,
    )

    print("\n완료.")


if __name__ == "__main__":
    main()