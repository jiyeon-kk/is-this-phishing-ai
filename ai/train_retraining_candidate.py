from pathlib import Path

import pandas as pd

from backend.reputation import get_approved_training_samples


# ============================================================
# 경로 설정
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 기존 V3 학습 데이터
BASE_TRAIN_PATH = (
    PROJECT_ROOT
    / "ai"
    / "data"
    / "processed"
    / "train_augmented_v3.csv"
)

# 재학습용 병합 데이터 저장 위치
RETRAINING_DIR = (
    PROJECT_ROOT
    / "ai"
    / "data"
    / "retraining"
)

MERGED_TRAIN_PATH = (
    RETRAINING_DIR
    / "train_retraining_candidate.csv"
)


def build_retraining_dataset() -> dict:
    """기존 V3 학습 데이터와 신규 승인 신고 데이터를 병합한다."""

    if not BASE_TRAIN_PATH.exists():
        raise FileNotFoundError(
            f"기존 V3 학습 데이터를 찾을 수 없습니다: {BASE_TRAIN_PATH}"
        )

    # 1. 기존 V3 학습 데이터 불러오기
    base_df = pd.read_csv(BASE_TRAIN_PATH)

    # 2. 아직 학습에 사용되지 않은 승인 신고 데이터 가져오기
    approved_samples = get_approved_training_samples()

    if not approved_samples:
        return {
            "created": False,
            "reason": "신규 승인 학습 샘플이 없습니다.",
            "base_count": len(base_df),
            "new_count": 0,
            "merged_count": len(base_df),
            "output_path": None,
        }

    # 3. 신고 데이터를 DataFrame으로 변환
    report_df = pd.DataFrame(
        [
            {
                "text": sample["text"],
                "label": sample["label"],
            }
            for sample in approved_samples
        ]
    )

    # 4. 신규 신고 데이터 내부 중복 제거
    report_df = report_df.drop_duplicates(
        subset=["text", "label"]
    ).reset_index(drop=True)

    # 5. 기존 V3 학습 데이터에 이미 존재하는 신규 신고는 제외
    existing_pairs = set(
        zip(
            base_df["text"].astype(str),
            base_df["label"].astype(int),
        )
    )

    report_df = report_df[
        ~report_df.apply(
            lambda row: (
                str(row["text"]),
                int(row["label"]),
            ) in existing_pairs,
            axis=1,
        )
    ].reset_index(drop=True)

    # 6. 기존 V3 데이터는 그대로 유지하고
    # 신규 승인 데이터만 뒤에 추가
    merged_df = pd.concat(
        [
            base_df,
            report_df,
        ],
        ignore_index=True,
    )

    # 6. 저장 폴더 생성
    RETRAINING_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # 7. candidate 학습용 CSV 저장
    merged_df.to_csv(
        MERGED_TRAIN_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    return {
        "created": True,
        "base_count": len(base_df),
        "new_count": len(report_df),
        "merged_count": len(merged_df),
        "output_path": str(MERGED_TRAIN_PATH),
        "case_keys": [
            sample["case_key"]
            for sample in approved_samples
        ],
    }


if __name__ == "__main__":
    result = build_retraining_dataset()
    print(result)