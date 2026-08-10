from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
)

from src.text_features import preprocess_for_model


# ============================================================
# 1. 기본 경로
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RAW_DIR = PROJECT_ROOT / "data" / "raw"

RESULT_DIR = (
    PROJECT_ROOT
    / "results"
    / "model_comparison"
)

RESULT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. 비교할 KcELECTRA 모델
# ============================================================

MODEL_PATHS = {
    # 기존 초기 KcELECTRA baseline
    "kcelectra_baseline": (
        PROJECT_ROOT
        / "models"
        / "kcelectra_baseline"
        / "checkpoint-779"
    ),

    # 현재 실제 서비스에서 사용하는 최종 문자 분류 모델
    "final_text_clf": (
        PROJECT_ROOT
        / "models"
        / "text_clf"
    ),
}


# ============================================================
# 3. 평가 데이터
# ============================================================

VALIDATION_PATH = (
    PROCESSED_DIR
    / "validation_real.csv"
)

HARD_PATH = (
    RAW_DIR
    / "korean_phishing_hard_test_1000.csv"
)


# ============================================================
# 4. 데이터 읽기
# ============================================================

def read_dataset(
    path: Path,
) -> pd.DataFrame:

    if not path.exists():
        raise FileNotFoundError(
            f"파일을 찾지 못했습니다: {path}"
        )

    df = pd.read_csv(
        path,
        encoding="utf-8-sig",
    )

    print("\n데이터 읽기:")
    print(path)

    print(
        "shape:",
        df.shape,
    )

    print(
        "columns:",
        df.columns.tolist(),
    )

    # --------------------------------------------------------
    # label 확인
    # --------------------------------------------------------

    if "label" not in df.columns:
        raise ValueError(
            f"label 컬럼이 없습니다: {path}"
        )

    df = df.dropna(
        subset=["label"]
    ).copy()

    df["label"] = (
        df["label"]
        .astype(int)
    )

    # --------------------------------------------------------
    # text 확인
    # --------------------------------------------------------

    if "text" not in df.columns:

        if "content" in df.columns:

            print(
                "text 컬럼이 없어 "
                "content에서 전처리합니다."
            )

            df["text"] = (
                df["content"]
                .map(
                    preprocess_for_model
                )
            )

        else:
            raise ValueError(
                "text와 content 컬럼이 "
                "모두 없습니다."
            )

    df = df.dropna(
        subset=["text"]
    ).copy()

    df["text"] = (
        df["text"]
        .astype(str)
    )

    return df.reset_index(
        drop=True
    )


# ============================================================
# 5. 모델 예측
# ============================================================

def predict_probabilities(
    model_path: Path,
    df: pd.DataFrame,
    batch_size: int = 16,
) -> np.ndarray:

    if not model_path.exists():
        raise FileNotFoundError(
            f"모델 폴더를 찾지 못했습니다: "
            f"{model_path}"
        )

    print("\n모델 불러오기:")
    print(model_path)

    tokenizer = (
        AutoTokenizer
        .from_pretrained(
            model_path,
            local_files_only=True,
        )
    )

    model = (
        AutoModelForSequenceClassification
        .from_pretrained(
            model_path,
            local_files_only=True,
        )
    )

    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    print(
        "사용 장치:",
        device,
    )

    model.to(
        device
    )

    model.eval()

    probabilities = []

    # --------------------------------------------------------
    # batch 단위 예측
    # --------------------------------------------------------

    for start in range(
        0,
        len(df),
        batch_size,
    ):

        batch_texts = (
            df["text"]
            .iloc[
                start:
                start + batch_size
            ]
            .tolist()
        )

        encoded = tokenizer(
            batch_texts,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=256,
        )

        encoded = {
            key: value.to(device)
            for key, value
            in encoded.items()
        }

        with torch.no_grad():

            logits = model(
                **encoded
            ).logits

            batch_probabilities = (
                torch.softmax(
                    logits,
                    dim=1,
                )[:, 1]
                .cpu()
                .numpy()
            )

        probabilities.extend(
            batch_probabilities.tolist()
        )

        processed = min(
            start + batch_size,
            len(df),
        )

        if (
            start == 0
            or processed % 320 == 0
            or processed == len(df)
        ):
            print(
                f"예측 진행: "
                f"{processed}/{len(df)}"
            )

    return np.array(
        probabilities,
        dtype=float,
    )


# ============================================================
# 6. 지표 계산
# ============================================================

def calculate_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    threshold: float = 0.5,
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

    metrics = {
        "threshold": threshold,

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

    # 두 클래스가 모두 있을 때만 계산
    if len(
        np.unique(labels)
    ) >= 2:

        metrics["roc_auc"] = (
            roc_auc_score(
                labels,
                probabilities,
            )
        )

    else:
        metrics["roc_auc"] = None

    return metrics


# ============================================================
# 7. Pair Accuracy
# ============================================================

def calculate_pair_accuracy(
    result_df: pd.DataFrame,
) -> float | None:

    if (
        "pair_id"
        not in result_df.columns
    ):
        return None

    pair_results = []

    for _, group in (
        result_df.groupby(
            "pair_id"
        )
    ):

        pair_results.append(
            bool(
                group[
                    "is_correct"
                ].all()
            )
        )

    if not pair_results:
        return None

    return float(
        np.mean(
            pair_results
        )
    )


# ============================================================
# 8. 모델 하나 + 데이터셋 하나 평가
# ============================================================

def evaluate_one(
    model_name: str,
    model_path: Path,
    dataset_name: str,
    dataset_path: Path,
) -> dict:

    print(
        "\n"
        + "=" * 80
    )

    print(
        f"{model_name} "
        f"- {dataset_name} 평가"
    )

    print(
        "=" * 80
    )

    df = read_dataset(
        dataset_path
    )

    probabilities = (
        predict_probabilities(
            model_path=model_path,
            df=df,
        )
    )

    labels = (
        df["label"]
        .to_numpy()
    )

    metrics = calculate_metrics(
        labels=labels,
        probabilities=probabilities,
        threshold=0.5,
    )

    # --------------------------------------------------------
    # 예측 결과
    # --------------------------------------------------------

    result_df = df.copy()

    result_df[
        "phishing_probability"
    ] = probabilities

    result_df[
        "predicted_label"
    ] = (
        probabilities >= 0.5
    ).astype(int)

    result_df[
        "is_correct"
    ] = (
        result_df["label"]
        == result_df[
            "predicted_label"
        ]
    )

    pair_accuracy = (
        calculate_pair_accuracy(
            result_df
        )
    )

    # --------------------------------------------------------
    # 최종 metrics
    # --------------------------------------------------------

    metrics[
        "model"
    ] = model_name

    metrics[
        "dataset"
    ] = dataset_name

    metrics[
        "rows"
    ] = len(
        result_df
    )

    metrics[
        "pair_accuracy"
    ] = pair_accuracy

    # --------------------------------------------------------
    # 예측 CSV 저장
    # --------------------------------------------------------

    output_path = (
        RESULT_DIR
        / (
            f"{model_name}_"
            f"{dataset_name}_"
            f"predictions.csv"
        )
    )

    result_df.to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # 출력
    # --------------------------------------------------------

    print("\n평가 결과")

    for key in [
        "accuracy",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "tn",
        "fp",
        "fn",
        "tp",
        "pair_accuracy",
    ]:

        value = metrics[
            key
        ]

        if isinstance(
            value,
            float,
        ):
            print(
                f"{key}: "
                f"{value:.4f}"
            )

        else:
            print(
                f"{key}: "
                f"{value}"
            )

    print(
        "\n예측 저장:"
    )

    print(
        output_path
    )

    return metrics


# ============================================================
# 9. 전체 실행
# ============================================================

def main() -> None:

    print(
        "=" * 80
    )

    print(
        "KcELECTRA 모델 동일 조건 비교"
    )

    print(
        "=" * 80
    )

    print(
        "장치:",
        (
            "cuda"
            if torch.cuda.is_available()
            else "cpu"
        ),
    )

    # --------------------------------------------------------
    # 평가 데이터
    # --------------------------------------------------------

    datasets = {
        "validation": (
            VALIDATION_PATH
        ),

        "hard": (
            HARD_PATH
        ),
    }

    all_metrics = []

    # --------------------------------------------------------
    # 모든 모델 × 모든 평가셋
    # --------------------------------------------------------

    for (
        model_name,
        model_path,
    ) in MODEL_PATHS.items():

        if not model_path.exists():

            print(
                "\n경고: "
                "모델이 없어 "
                "건너뜁니다."
            )

            print(
                model_name,
                model_path,
            )

            continue

        for (
            dataset_name,
            dataset_path,
        ) in datasets.items():

            metrics = (
                evaluate_one(
                    model_name=model_name,
                    model_path=model_path,
                    dataset_name=dataset_name,
                    dataset_path=dataset_path,
                )
            )

            all_metrics.append(
                metrics
            )

    # --------------------------------------------------------
    # 평가 여부 확인
    # --------------------------------------------------------

    if not all_metrics:

        raise RuntimeError(
            "평가된 모델이 없습니다. "
            "모델 경로를 확인하세요."
        )

    # --------------------------------------------------------
    # 비교표
    # --------------------------------------------------------

    comparison_df = (
        pd.DataFrame(
            all_metrics
        )
    )

    comparison_df = (
        comparison_df[
            [
                "model",
                "dataset",
                "rows",
                "threshold",
                "accuracy",
                "precision",
                "recall",
                "f1",
                "roc_auc",
                "tn",
                "fp",
                "fn",
                "tp",
                "pair_accuracy",
            ]
        ]
    )

    comparison_path = (
        RESULT_DIR
        / "kcelectra_model_comparison.csv"
    )

    comparison_df.to_csv(
        comparison_path,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # 최종 출력
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 80
    )

    print(
        "최종 비교표"
    )

    print(
        "=" * 80
    )

    print(
        comparison_df.to_string(
            index=False
        )
    )

    print(
        "\n비교표 저장:"
    )

    print(
        comparison_path
    )

    print(
        "\n완료."
    )


if __name__ == "__main__":
    main()