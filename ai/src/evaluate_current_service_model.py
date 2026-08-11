from pathlib import Path
import json

import numpy as np
import pandas as pd
import torch

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
)

from transformers import (
    AutoTokenizer,
    AutoModelForSequenceClassification,
)


# ============================================================
# 경로 설정
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

MODEL_PATH = PROJECT_ROOT / "models" / "text_clf"

VALIDATION_PATH = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "validation_real.csv"
)

RESULT_DIR = (
    PROJECT_ROOT
    / "results"
    / "current_service_model"
)

RESULT_PATH = RESULT_DIR / "validation_metrics.json"

MAX_LENGTH = 256
BATCH_SIZE = 16


# ============================================================
# 평가 함수
# ============================================================

def evaluate_current_service_model():
    print("=" * 70)
    print("현재 서비스 모델(V3) Validation 평가")
    print("=" * 70)

    print("Model:", MODEL_PATH)
    print("Validation:", VALIDATION_PATH)

    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            f"서비스 모델 폴더를 찾을 수 없습니다: {MODEL_PATH}"
        )

    if not VALIDATION_PATH.exists():
        raise FileNotFoundError(
            f"Validation 파일을 찾을 수 없습니다: {VALIDATION_PATH}"
        )

    # --------------------------------------------------------
    # Validation 데이터 로드
    # --------------------------------------------------------

    df = pd.read_csv(VALIDATION_PATH)

    required_columns = {"text", "label"}

    if not required_columns.issubset(df.columns):
        raise ValueError(
            "validation_real.csv에 text, label 컬럼이 필요합니다."
        )

    df = df.dropna(subset=["text", "label"]).copy()

    df["text"] = df["text"].astype(str)
    df["label"] = df["label"].astype(int)

    print()
    print("Validation shape:", df.shape)
    print()
    print("Validation label 분포")
    print(df["label"].value_counts().sort_index())

    # --------------------------------------------------------
    # Device
    # --------------------------------------------------------

    device = torch.device(
        "cuda" if torch.cuda.is_available() else "cpu"
    )

    print()
    print("Device:", device)

    # --------------------------------------------------------
    # 모델 로드
    # --------------------------------------------------------

    print()
    print("현재 서비스 모델 로딩 중...")

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL_PATH
    )

    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_PATH
    )

    model.to(device)
    model.eval()

    print("모델 로딩 완료")

    # --------------------------------------------------------
    # 추론
    # --------------------------------------------------------

    texts = df["text"].tolist()
    labels = df["label"].to_numpy()

    all_predictions = []
    all_probabilities = []

    print()
    print("Validation 추론 시작...")

    with torch.no_grad():

        for start in range(0, len(texts), BATCH_SIZE):

            batch_texts = texts[
                start:start + BATCH_SIZE
            ]

            encoded = tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=MAX_LENGTH,
                return_tensors="pt",
            )

            encoded = {
                key: value.to(device)
                for key, value in encoded.items()
            }

            outputs = model(**encoded)

            probabilities = torch.softmax(
                outputs.logits,
                dim=-1,
            )

            phishing_probabilities = (
                probabilities[:, 1]
                .detach()
                .cpu()
                .numpy()
            )

            predictions = (
                probabilities.argmax(dim=-1)
                .detach()
                .cpu()
                .numpy()
            )

            all_predictions.extend(
                predictions.tolist()
            )

            all_probabilities.extend(
                phishing_probabilities.tolist()
            )

            current = min(
                start + BATCH_SIZE,
                len(texts),
            )

            if (
                current % 200 == 0
                or current == len(texts)
            ):
                print(
                    f"{current}/{len(texts)} 완료"
                )

    predictions = np.array(all_predictions)
    probabilities = np.array(all_probabilities)

    # --------------------------------------------------------
    # Metrics
    # --------------------------------------------------------

    accuracy = accuracy_score(
        labels,
        predictions,
    )

    precision = precision_score(
        labels,
        predictions,
        zero_division=0,
    )

    recall = recall_score(
        labels,
        predictions,
        zero_division=0,
    )

    f1 = f1_score(
        labels,
        predictions,
        zero_division=0,
    )

    roc_auc = roc_auc_score(
        labels,
        probabilities,
    )

    tn, fp, fn, tp = confusion_matrix(
        labels,
        predictions,
        labels=[0, 1],
    ).ravel()

    metrics = {
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "roc_auc": float(roc_auc),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
        "validation_count": int(len(df)),
        "model_path": str(MODEL_PATH),
        "validation_path": str(
            VALIDATION_PATH
        ),
    }

    # --------------------------------------------------------
    # 출력
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("현재 서비스 모델 Validation 성능")
    print("=" * 70)

    for key, value in metrics.items():

        if key in {
            "model_path",
            "validation_path",
        }:
            continue

        print(f"{key}: {value}")

    # --------------------------------------------------------
    # 결과 저장
    # --------------------------------------------------------

    RESULT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        RESULT_PATH,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            metrics,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print("평가 결과 저장:")
    print(RESULT_PATH)

    return metrics


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    evaluate_current_service_model()