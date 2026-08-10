from __future__ import annotations

import sys
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


# ============================================================
# 1. 경로 설정
# ============================================================

AI_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = AI_ROOT.parent

# backend 모듈 import를 위해 repo root 추가
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.adversarial_transform import (
    insert_spaces,
    insert_special_characters,
    mix_english,
    obfuscate_url,
    split_hangul_like,
)

from src.text_features import preprocess_for_model


HARD_PATH = (
    AI_ROOT
    / "data"
    / "raw"
    / "korean_phishing_hard_test_1000.csv"
)

MODEL_DIR = (
    AI_ROOT
    / "models"
    / "text_clf"
)

RESULT_DIR = (
    AI_ROOT
    / "results"
    / "adversarial_robustness"
)

RESULT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. 기본 설정
# ============================================================

THRESHOLD = 0.5
MAX_LENGTH = 256
BATCH_SIZE = 32


# ============================================================
# 3. 공격 유형
# ============================================================

ATTACKS = {
    "spacing": {
        "label": "공백 삽입",
        "function": insert_spaces,
    },

    "special_character": {
        "label": "특수문자 삽입",
        "function": insert_special_characters,
    },

    "english_mix": {
        "label": "한글·영문 혼용",
        "function": mix_english,
    },

    "url_obfuscation": {
        "label": "URL 형태 변형",
        "function": obfuscate_url,
    },

    "hangul_split": {
        "label": "자모 유사 변형",
        "function": split_hangul_like,
    },
}


# ============================================================
# 4. HARD 데이터 읽기
# ============================================================

def load_hard_dataset() -> pd.DataFrame:

    if not HARD_PATH.exists():
        raise FileNotFoundError(
            f"HARD 데이터가 없습니다:\n{HARD_PATH}"
        )

    df = pd.read_csv(
        HARD_PATH,
        encoding="utf-8-sig",
    )

    required_columns = {
        "content",
        "label",
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
        subset=["content", "label"]
    ).copy()

    df["content"] = (
        df["content"]
        .astype(str)
    )

    df["label"] = (
        df["label"]
        .astype(int)
    )

    print("=" * 80)
    print("HARD 데이터 로딩")
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
# 5. 모델 로드
# ============================================================

def load_model():

    if not MODEL_DIR.exists():
        raise FileNotFoundError(
            f"모델 폴더가 없습니다:\n{MODEL_DIR}"
        )

    device = torch.device(
        "cuda"
        if torch.cuda.is_available()
        else "cpu"
    )

    print("\n" + "=" * 80)
    print("모델 로딩")
    print("=" * 80)

    print("모델:", MODEL_DIR)
    print("장치:", device)

    tokenizer = (
        AutoTokenizer
        .from_pretrained(
            MODEL_DIR,
            local_files_only=True,
        )
    )

    model = (
        AutoModelForSequenceClassification
        .from_pretrained(
            MODEL_DIR,
            local_files_only=True,
        )
    )

    model.to(device)
    model.eval()

    return (
        tokenizer,
        model,
        device,
    )


# ============================================================
# 6. 배치 예측
# ============================================================

def predict_probabilities(
    texts: list[str],
    tokenizer,
    model,
    device,
) -> np.ndarray:

    probabilities = []

    for start in range(
        0,
        len(texts),
        BATCH_SIZE,
    ):

        batch = texts[
            start:
            start + BATCH_SIZE
        ]

        encoded = tokenizer(
            batch,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=MAX_LENGTH,
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

            probs = (
                torch.softmax(
                    logits,
                    dim=1,
                )[:, 1]
                .cpu()
                .numpy()
            )

        probabilities.extend(
            probs.tolist()
        )

        processed = min(
            start + BATCH_SIZE,
            len(texts),
        )

        if (
            processed % 320 == 0
            or processed == len(texts)
        ):
            print(
                f"예측 진행: "
                f"{processed}/{len(texts)}"
            )

    return np.array(
        probabilities,
        dtype=float,
    )


# ============================================================
# 7. 지표 계산
# ============================================================

def calculate_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
) -> dict:

    predictions = (
        probabilities
        >= THRESHOLD
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

        "roc_auc": roc_auc_score(
            labels,
            probabilities,
        ),

        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }

    return metrics


# ============================================================
# 8. 한 조건 평가
# ============================================================

def evaluate_condition(
    df: pd.DataFrame,
    condition_name: str,
    attack_label: str,
    raw_texts: list[str],
    tokenizer,
    model,
    device,
    original_predictions: np.ndarray | None = None,
) -> tuple[dict, pd.DataFrame]:

    print(
        "\n"
        + "=" * 80
    )

    print(
        f"평가: {attack_label}"
    )

    print(
        "=" * 80
    )

    # 모델 학습/평가 때와 동일한 전처리
    processed_texts = [
        preprocess_for_model(text)
        for text in raw_texts
    ]

    probabilities = (
        predict_probabilities(
            texts=processed_texts,
            tokenizer=tokenizer,
            model=model,
            device=device,
        )
    )

    labels = (
        df["label"]
        .to_numpy()
    )

    predictions = (
        probabilities
        >= THRESHOLD
    ).astype(int)

    metrics = (
        calculate_metrics(
            labels=labels,
            probabilities=probabilities,
        )
    )

    # 실제로 텍스트가 변경된 개수
    original_contents = (
        df["content"]
        .astype(str)
        .tolist()
    )

    changed_mask = np.array(
        [
            transformed != original
            for original, transformed
            in zip(
                original_contents,
                raw_texts,
            )
        ],
        dtype=bool,
    )

    metrics[
        "condition"
    ] = condition_name

    metrics[
        "attack_label"
    ] = attack_label

    metrics[
        "rows"
    ] = len(df)

    metrics[
        "changed_rows"
    ] = int(
        changed_mask.sum()
    )

    metrics[
        "changed_rate"
    ] = float(
        changed_mask.mean()
    )

    # --------------------------------------------------------
    # 탐지 유지율
    #
    # 원본에서 피싱을 정상적으로 잡았던 샘플 중
    # 공격 후에도 피싱으로 유지된 비율
    # --------------------------------------------------------

    if original_predictions is None:

        metrics[
            "detection_retention"
        ] = 1.0

        metrics[
            "newly_evaded_phishing"
        ] = 0

    else:

        originally_detected_phishing = (
            (labels == 1)
            & (original_predictions == 1)
        )

        denominator = int(
            originally_detected_phishing.sum()
        )

        if denominator > 0:

            retained = int(
                (
                    originally_detected_phishing
                    & (predictions == 1)
                ).sum()
            )

            metrics[
                "detection_retention"
            ] = (
                retained
                / denominator
            )

            metrics[
                "newly_evaded_phishing"
            ] = int(
                denominator
                - retained
            )

        else:

            metrics[
                "detection_retention"
            ] = None

            metrics[
                "newly_evaded_phishing"
            ] = None

    # --------------------------------------------------------
    # 예측 결과 저장용 DataFrame
    # --------------------------------------------------------

    result_df = df.copy()

    result_df[
        "attack_type"
    ] = condition_name

    result_df[
        "attack_label"
    ] = attack_label

    result_df[
        "original_content"
    ] = df[
        "content"
    ].astype(str)

    result_df[
        "transformed_content"
    ] = raw_texts

    result_df[
        "was_changed"
    ] = changed_mask

    result_df[
        "model_text"
    ] = processed_texts

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

    # --------------------------------------------------------
    # 출력
    # --------------------------------------------------------

    print(
        f"변형된 문자: "
        f"{metrics['changed_rows']}"
        f"/{metrics['rows']}"
    )

    print(
        f"Accuracy: "
        f"{metrics['accuracy']:.4f}"
    )

    print(
        f"Precision: "
        f"{metrics['precision']:.4f}"
    )

    print(
        f"Recall: "
        f"{metrics['recall']:.4f}"
    )

    print(
        f"F1: "
        f"{metrics['f1']:.4f}"
    )

    print(
        f"ROC-AUC: "
        f"{metrics['roc_auc']:.4f}"
    )

    print(
        f"FN: "
        f"{metrics['fn']}"
    )

    if (
        metrics[
            "detection_retention"
        ]
        is not None
    ):
        print(
            "탐지 유지율: "
            f"{metrics['detection_retention']:.4f}"
        )

        print(
            "새롭게 우회된 피싱: "
            f"{metrics['newly_evaded_phishing']}"
        )

    return (
        metrics,
        result_df,
    )


# ============================================================
# 9. 전체 실행
# ============================================================

def main() -> None:

    df = load_hard_dataset()

    (
        tokenizer,
        model,
        device,
    ) = load_model()

    all_metrics = []
    all_predictions = []

    # ========================================================
    # 원본 HARD 평가
    # ========================================================

    original_texts = (
        df["content"]
        .astype(str)
        .tolist()
    )

    (
        original_metrics,
        original_result,
    ) = evaluate_condition(
        df=df,
        condition_name="original",
        attack_label="원본",
        raw_texts=original_texts,
        tokenizer=tokenizer,
        model=model,
        device=device,
        original_predictions=None,
    )

    all_metrics.append(
        original_metrics
    )

    all_predictions.append(
        original_result
    )

    original_predictions = (
        original_result[
            "prediction"
        ]
        .to_numpy()
    )

    # ========================================================
    # 5개 공격 유형 평가
    # ========================================================

    for (
        attack_name,
        attack_info,
    ) in ATTACKS.items():

        transform_function = (
            attack_info[
                "function"
            ]
        )

        transformed_texts = [
            transform_function(text)
            for text in original_texts
        ]

        (
            metrics,
            result_df,
        ) = evaluate_condition(
            df=df,
            condition_name=attack_name,
            attack_label=attack_info[
                "label"
            ],
            raw_texts=transformed_texts,
            tokenizer=tokenizer,
            model=model,
            device=device,
            original_predictions=(
                original_predictions
            ),
        )

        all_metrics.append(
            metrics
        )

        all_predictions.append(
            result_df
        )

    # ========================================================
    # 10. 결과 저장
    # ========================================================

    metrics_df = pd.DataFrame(
        all_metrics
    )

    # 원본 대비 변화량
    original_f1 = float(
        original_metrics["f1"]
    )

    original_recall = float(
        original_metrics["recall"]
    )

    original_accuracy = float(
        original_metrics["accuracy"]
    )

    metrics_df[
        "f1_drop_vs_original"
    ] = (
        original_f1
        - metrics_df["f1"]
    )

    metrics_df[
        "recall_drop_vs_original"
    ] = (
        original_recall
        - metrics_df["recall"]
    )

    metrics_df[
        "accuracy_drop_vs_original"
    ] = (
        original_accuracy
        - metrics_df["accuracy"]
    )

    metrics_columns = [
        "condition",
        "attack_label",
        "rows",
        "changed_rows",
        "changed_rate",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "tn",
        "fp",
        "fn",
        "tp",
        "detection_retention",
        "newly_evaded_phishing",
        "accuracy_drop_vs_original",
        "recall_drop_vs_original",
        "f1_drop_vs_original",
    ]

    metrics_df = metrics_df[
        metrics_columns
    ]

    metrics_path = (
        RESULT_DIR
        / "adversarial_robustness_metrics.csv"
    )

    metrics_df.to_csv(
        metrics_path,
        index=False,
        encoding="utf-8-sig",
    )

    predictions_df = pd.concat(
        all_predictions,
        ignore_index=True,
    )

    predictions_path = (
        RESULT_DIR
        / "adversarial_robustness_predictions.csv"
    )

    predictions_df.to_csv(
        predictions_path,
        index=False,
        encoding="utf-8-sig",
    )

    # ========================================================
    # 11. 최종 비교표 출력
    # ========================================================

    print(
        "\n"
        + "=" * 100
    )

    print(
        "적대적 강건성 최종 비교"
    )

    print(
        "=" * 100
    )

    display_columns = [
        "attack_label",
        "changed_rows",
        "accuracy",
        "recall",
        "f1",
        "fn",
        "detection_retention",
        "newly_evaded_phishing",
        "recall_drop_vs_original",
        "f1_drop_vs_original",
    ]

    print(
        metrics_df[
            display_columns
        ].to_string(
            index=False
        )
    )

    print(
        "\n지표 저장:"
    )

    print(
        metrics_path
    )

    print(
        "\n전체 예측 저장:"
    )

    print(
        predictions_path
    )

    print(
        "\n완료."
    )


if __name__ == "__main__":
    main()