from __future__ import annotations

import json
import random
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from datasets import Dataset
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
    DataCollatorWithPadding,
    Trainer,
    TrainingArguments,
)


# ============================================================
# 1. 기본 설정
# ============================================================

SEED = 42
MODEL_NAME = "beomi/KcELECTRA-base-v2022"

MAX_LENGTH = 256
TRAIN_BATCH_SIZE = 4
EVAL_BATCH_SIZE = 8
GRADIENT_ACCUMULATION_STEPS = 4

LEARNING_RATE = 2e-5
WEIGHT_DECAY = 0.01
NUM_EPOCHS = 2

PROJECT_ROOT = Path(__file__).resolve().parent.parent

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
RETRAINING_DIR = PROJECT_ROOT / "data" / "retraining"

TRAIN_PATH = (
    RETRAINING_DIR
    / "train_retraining_candidate.csv"
)

VALIDATION_PATH = (
    PROCESSED_DIR
    / "validation_real.csv"
)

MODEL_DIR = (
    PROJECT_ROOT
    / "models"
    / "retraining_candidate"
)

RESULT_DIR = (
    PROJECT_ROOT
    / "results"
    / "retraining_candidate"
)

FINAL_MODEL_DIR = (
    MODEL_DIR
    / "best_model"
)

MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

RESULT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

FINAL_MODEL_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# 2. 재현성
# ============================================================

def set_seed(seed: int = SEED) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)

    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ============================================================
# 3. 데이터 읽기
# ============================================================

def read_train_dataset(
    path: Path,
) -> pd.DataFrame:
    """Candidate 학습 데이터를 읽는다."""

    if not path.exists():
        raise FileNotFoundError(
            f"Candidate 학습 데이터를 찾을 수 없습니다: {path}"
        )

    df = pd.read_csv(
        path,
        encoding="utf-8-sig",
    )

    required_columns = {
        "text",
        "label",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            f"필수 컬럼이 없습니다: {sorted(missing_columns)}"
        )

    df = df.dropna(
        subset=["text", "label"]
    ).copy()

    df["text"] = (
        df["text"]
        .astype(str)
        .str.strip()
    )

    df = df[
        df["text"].ne("")
    ].copy()

    df["label"] = (
        df["label"]
        .astype(int)
    )

    invalid_labels = (
        set(df["label"].unique())
        - {0, 1}
    )

    if invalid_labels:
        raise ValueError(
            f"잘못된 label: {sorted(invalid_labels)}"
        )

    return df.reset_index(drop=True)


def read_validation_dataset(
    path: Path,
) -> pd.DataFrame:
    """기존 V3와 동일한 validation 데이터를 읽는다."""

    if not path.exists():
        raise FileNotFoundError(
            f"Validation 데이터를 찾을 수 없습니다: {path}"
        )

    df = pd.read_csv(
        path,
        encoding="utf-8-sig",
    )

    required_columns = {
        "text",
        "label",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        raise ValueError(
            f"필수 컬럼이 없습니다: {sorted(missing_columns)}"
        )

    df = df.dropna(
        subset=["text", "label"]
    ).copy()

    df["text"] = (
        df["text"]
        .astype(str)
        .str.strip()
    )

    df = df[
        df["text"].ne("")
    ].copy()

    df["label"] = (
        df["label"]
        .astype(int)
    )

    return df.reset_index(drop=True)


# ============================================================
# 4. 평가 지표
# ============================================================

def compute_metrics(eval_pred) -> dict[str, float]:
    logits, labels = eval_pred

    probabilities = torch.softmax(
        torch.tensor(logits),
        dim=1,
    ).numpy()

    phishing_probabilities = (
        probabilities[:, 1]
    )

    predictions = np.argmax(
        logits,
        axis=1,
    )

    tn, fp, fn, tp = confusion_matrix(
        labels,
        predictions,
        labels=[0, 1],
    ).ravel()

    return {
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
            phishing_probabilities,
        ),
        "tn": int(tn),
        "fp": int(fp),
        "fn": int(fn),
        "tp": int(tp),
    }


# ============================================================
# 5. 최종 모델 저장
# ============================================================

def save_final_model(
    trainer: Trainer,
    tokenizer,
) -> None:
    trainer.model.save_pretrained(
        str(FINAL_MODEL_DIR),
        safe_serialization=True,
    )

    tokenizer.save_pretrained(
        str(FINAL_MODEL_DIR)
    )

    print("\nCandidate 모델 저장 완료:")
    print(FINAL_MODEL_DIR)


# ============================================================
# 6. 저장 모델 재로딩 검증
# ============================================================

def verify_saved_model() -> None:
    tokenizer = AutoTokenizer.from_pretrained(
        FINAL_MODEL_DIR
    )

    model = (
        AutoModelForSequenceClassification
        .from_pretrained(
            FINAL_MODEL_DIR
        )
    )

    model.eval()

    sample_text = (
        "[국외발신] 고객님의 계정이 정지되었습니다. "
        "[URL_SHORTENER] 에서 인증해주세요."
    )

    encoded = tokenizer(
        sample_text,
        return_tensors="pt",
        truncation=True,
        max_length=MAX_LENGTH,
    )

    with torch.no_grad():
        logits = model(
            **encoded
        ).logits

        probability = torch.softmax(
            logits,
            dim=1,
        )[0, 1].item()

    print("\nCandidate 재로딩 성공")
    print(
        "테스트 피싱 확률:",
        round(float(probability), 6),
    )


# ============================================================
# 7. Candidate 학습
# ============================================================

def run_candidate_training() -> None:
    set_seed()

    print("=" * 80)
    print("PhishGuard Retraining Candidate 학습")
    print("=" * 80)

    print("Train:", TRAIN_PATH)
    print("Validation:", VALIDATION_PATH)
    print("Candidate 저장:", FINAL_MODEL_DIR)

    print(
        "Device:",
        "cuda"
        if torch.cuda.is_available()
        else "cpu",
    )

    train_df = read_train_dataset(
        TRAIN_PATH
    )

    validation_df = (
        read_validation_dataset(
            VALIDATION_PATH
        )
    )

    print("\nTrain shape:", train_df.shape)
    print(
        "Validation shape:",
        validation_df.shape,
    )

    print("\nTrain label 분포")
    print(
        train_df["label"]
        .value_counts()
        .sort_index()
    )

    tokenizer = (
        AutoTokenizer.from_pretrained(
            MODEL_NAME
        )
    )

    model = (
        AutoModelForSequenceClassification
        .from_pretrained(
            MODEL_NAME,
            num_labels=2,
            id2label={
                0: "NORMAL",
                1: "PHISHING",
            },
            label2id={
                "NORMAL": 0,
                "PHISHING": 1,
            },
        )
    )

    train_dataset = Dataset.from_pandas(
        train_df[
            ["text", "label"]
        ],
        preserve_index=False,
    )

    validation_dataset = Dataset.from_pandas(
        validation_df[
            ["text", "label"]
        ],
        preserve_index=False,
    )

    def tokenize_batch(batch):
        return tokenizer(
            batch["text"],
            truncation=True,
            max_length=MAX_LENGTH,
        )

    train_dataset = train_dataset.map(
        tokenize_batch,
        batched=True,
        desc="Candidate train tokenization",
    )

    validation_dataset = (
        validation_dataset.map(
            tokenize_batch,
            batched=True,
            desc="Candidate validation tokenization",
        )
    )

    train_dataset = (
        train_dataset.remove_columns(
            ["text"]
        )
    )

    validation_dataset = (
        validation_dataset.remove_columns(
            ["text"]
        )
    )

    data_collator = (
        DataCollatorWithPadding(
            tokenizer=tokenizer
        )
    )

    training_args = TrainingArguments(
        output_dir=str(MODEL_DIR),

        learning_rate=LEARNING_RATE,
        weight_decay=WEIGHT_DECAY,
        num_train_epochs=NUM_EPOCHS,

        per_device_train_batch_size=(
            TRAIN_BATCH_SIZE
        ),

        per_device_eval_batch_size=(
            EVAL_BATCH_SIZE
        ),

        gradient_accumulation_steps=(
            GRADIENT_ACCUMULATION_STEPS
        ),

        eval_strategy="epoch",
        save_strategy="epoch",

        logging_strategy="steps",
        logging_steps=100,

        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,

        save_total_limit=1,

        seed=SEED,
        data_seed=SEED,

        fp16=torch.cuda.is_available(),

        dataloader_num_workers=0,

        report_to="none",
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=validation_dataset,
        processing_class=tokenizer,
        data_collator=data_collator,
        compute_metrics=compute_metrics,
    )

    train_result = trainer.train()

    print("\n학습 완료")
    print(train_result)

    save_final_model(
        trainer,
        tokenizer,
    )

    verify_saved_model()

    validation_metrics = (
        trainer.evaluate(
            validation_dataset
        )
    )

    print("\nCandidate Validation 성능")

    for key, value in (
        validation_metrics.items()
    ):
        print(f"{key}: {value}")

    metrics_path = (
        RESULT_DIR
        / "validation_metrics.json"
    )

    with open(
        metrics_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            validation_metrics,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print("\n평가 결과 저장:")
    print(metrics_path)

    print("\n중요:")
    print(
        "이 모델은 Candidate이며 "
        "현재 서비스 모델을 자동으로 덮어쓰지 않습니다."
    )


if __name__ == "__main__":
    run_candidate_training()