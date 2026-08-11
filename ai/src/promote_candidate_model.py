from pathlib import Path
import json
import shutil
from datetime import datetime


# ============================================================
# 경로 설정
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CURRENT_MODEL_DIR = (
    PROJECT_ROOT
    / "models"
    / "text_clf"
)

CANDIDATE_MODEL_DIR = (
    PROJECT_ROOT
    / "models"
    / "retraining_candidate"
    / "best_model"
)

COMPARE_RESULT_PATH = (
    PROJECT_ROOT
    / "results"
    / "model_comparison"
    / "comparison_result.json"
)

BACKUP_ROOT = (
    PROJECT_ROOT
    / "models"
    / "backups"
)


# ============================================================
# 비교 결과 로드
# ============================================================

def load_comparison_result() -> dict:

    if not COMPARE_RESULT_PATH.exists():
        raise FileNotFoundError(
            f"비교 결과 파일을 찾을 수 없습니다: "
            f"{COMPARE_RESULT_PATH}"
        )

    with open(
        COMPARE_RESULT_PATH,
        "r",
        encoding="utf-8-sig",
    ) as f:
        return json.load(f)


# ============================================================
# 필수 모델 파일 검사
# ============================================================

def validate_model_directory(
    model_dir: Path,
) -> None:

    if not model_dir.exists():
        raise FileNotFoundError(
            f"모델 폴더를 찾을 수 없습니다: "
            f"{model_dir}"
        )

    required_files = [
        "config.json",
        "tokenizer_config.json",
    ]

    for filename in required_files:

        path = model_dir / filename

        if not path.exists():
            raise FileNotFoundError(
                f"필수 모델 파일 누락: {path}"
            )

    model_weight_exists = (
        (model_dir / "model.safetensors").exists()
        or
        (model_dir / "pytorch_model.bin").exists()
    )

    if not model_weight_exists:
        raise FileNotFoundError(
            "모델 weight 파일이 없습니다. "
            "model.safetensors 또는 "
            "pytorch_model.bin이 필요합니다."
        )


# ============================================================
# Candidate 승격
# ============================================================

def promote_candidate_model() -> dict:

    print("=" * 70)
    print("Retraining Candidate 모델 승격")
    print("=" * 70)

    comparison = load_comparison_result()

    decision = comparison.get(
        "decision"
    )

    promotion = bool(
        comparison.get(
            "promotion",
            False,
        )
    )

    print()
    print("비교 결과:", decision)

    # --------------------------------------------------------
    # REJECT이면 절대 서비스 모델 수정하지 않음
    # --------------------------------------------------------

    if (
        decision != "PROMOTE"
        or not promotion
    ):

        print()
        print(
            "Candidate가 승격 기준을 "
            "통과하지 못했습니다."
        )

        print(
            "현재 서비스 모델은 "
            "그대로 유지합니다."
        )

        result = {
            "promoted": False,
            "decision": decision,
            "service_model_changed": False,
            "reason": (
                "Candidate가 승격 기준을 "
                "통과하지 못함"
            ),
        }

        return result

    # --------------------------------------------------------
    # PROMOTE인 경우에만 아래 로직 실행
    # --------------------------------------------------------

    print()
    print(
        "Candidate가 승격 기준을 통과했습니다."
    )

    # 현재 모델과 Candidate 검사
    validate_model_directory(
        CURRENT_MODEL_DIR
    )

    validate_model_directory(
        CANDIDATE_MODEL_DIR
    )

    # --------------------------------------------------------
    # 백업 경로 생성
    # --------------------------------------------------------

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_dir = (
        BACKUP_ROOT
        / f"text_clf_{timestamp}"
    )

    BACKUP_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    print()
    print("현재 서비스 모델 백업:")
    print(backup_dir)

    # --------------------------------------------------------
    # 현재 서비스 모델 백업
    # --------------------------------------------------------

    shutil.copytree(
        CURRENT_MODEL_DIR,
        backup_dir,
    )

    print("백업 완료")

    # --------------------------------------------------------
    # Candidate → 서비스 모델 교체
    #
    # 실패하면 기존 백업을 복구
    # --------------------------------------------------------

    try:

        print()
        print(
            "Candidate를 서비스 모델로 "
            "승격 중..."
        )

        # 기존 서비스 모델 제거
        shutil.rmtree(
            CURRENT_MODEL_DIR
        )

        # Candidate 복사
        shutil.copytree(
            CANDIDATE_MODEL_DIR,
            CURRENT_MODEL_DIR,
        )

        # 복사 후 필수 파일 다시 확인
        validate_model_directory(
            CURRENT_MODEL_DIR
        )

    except Exception as exc:

        print()
        print(
            "승격 중 오류 발생."
        )

        print(
            "기존 서비스 모델을 복구합니다."
        )

        if CURRENT_MODEL_DIR.exists():

            shutil.rmtree(
                CURRENT_MODEL_DIR
            )

        shutil.copytree(
            backup_dir,
            CURRENT_MODEL_DIR,
        )

        print(
            "기존 서비스 모델 복구 완료"
        )

        raise RuntimeError(
            "Candidate 승격 실패. "
            "기존 모델로 복구했습니다."
        ) from exc

    # --------------------------------------------------------
    # 성공
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("Candidate 승격 완료")
    print("=" * 70)

    print()
    print("새 서비스 모델:")
    print(CURRENT_MODEL_DIR)

    print()
    print("기존 모델 백업:")
    print(backup_dir)

    result = {
        "promoted": True,
        "decision": decision,
        "service_model_changed": True,
        "service_model_path": str(
            CURRENT_MODEL_DIR
        ),
        "backup_path": str(
            backup_dir
        ),
    }

    return result


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    result = promote_candidate_model()

    print()
    print("결과:")
    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )