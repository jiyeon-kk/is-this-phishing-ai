"""신고 기반 AI Batch 재학습 관리.

전체 흐름:

승인된 신규 신고 사례 누적
↓
RETRAIN_MIN_SAMPLES 이상인지 확인
↓
기존 학습 데이터 + 신규 승인 사례 병합
↓
GPU 사용 가능 여부 확인
↓
Candidate 모델 학습
↓
현재 서비스 모델 Validation 평가
↓
Candidate Validation 평가
↓
Current vs Candidate 자동 비교
↓
PROMOTE / REJECT
↓
PROMOTE일 때만 서비스 모델 교체
↓
재학습에 사용한 case_key 사용 완료 처리

중요:
- confirmed만으로는 학습하지 않는다.
- training_approved 된 사례만 사용한다.
- 학습 실패 시 used_for_training 처리하지 않는다.
- Candidate가 REJECT되더라도 정상적으로 학습·평가까지 완료됐다면
  해당 사례는 이번 재학습 cycle에서 이미 사용된 것이므로
  used_for_training=1로 처리한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend import reputation


# ============================================================
# 설정
# ============================================================

RETRAIN_MIN_SAMPLES = 20

PROJECT_ROOT = (
    Path(__file__).resolve().parent.parent
)

PIPELINE_RESULT_DIR = (
    PROJECT_ROOT
    / "ai"
    / "results"
    / "retraining_pipeline"
)


# ============================================================
# 시간
# ============================================================

def _now() -> str:
    """현재 UTC 시각을 ISO 문자열로 반환한다."""

    return datetime.now(
        timezone.utc
    ).isoformat()


def _make_model_version() -> str:
    """이번 재학습 cycle의 고유 버전을 생성한다."""

    timestamp = datetime.now(
        timezone.utc
    ).strftime(
        "%Y%m%d_%H%M%S"
    )

    return f"candidate_{timestamp}"


# ============================================================
# 재학습 상태
# ============================================================

def get_retraining_status() -> dict:
    """현재 신규 승인 샘플 누적 상태를 반환한다."""

    samples = (
        reputation
        .get_approved_training_samples()
    )

    sample_count = len(
        samples
    )

    ready = (
        sample_count
        >= RETRAIN_MIN_SAMPLES
    )

    return {
        "ready": ready,
        "new_sample_count": sample_count,
        "required_sample_count": (
            RETRAIN_MIN_SAMPLES
        ),
        "remaining_sample_count": max(
            RETRAIN_MIN_SAMPLES
            - sample_count,
            0,
        ),
    }


# ============================================================
# GPU 확인
# ============================================================

def _get_device_status() -> dict:
    """Candidate 학습 가능 GPU 환경인지 확인한다."""

    import torch

    cuda_available = bool(
        torch.cuda.is_available()
    )

    if cuda_available:

        device_name = (
            torch.cuda.get_device_name(0)
        )

    else:

        device_name = "CPU"

    return {
        "cuda_available": cuda_available,
        "device": device_name,
    }


# ============================================================
# 결과 저장
# ============================================================

def _save_pipeline_result(
    result: dict,
    model_version: str,
) -> Path:
    """재학습 cycle 결과를 JSON으로 저장한다."""

    PIPELINE_RESULT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        PIPELINE_RESULT_DIR
        / f"{model_version}.json"
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )

    return path


# ============================================================
# 전체 재학습 Pipeline
# ============================================================

def run_retraining_pipeline() -> dict:
    """신고 기반 Batch 재학습 전체 흐름을 실행한다.

    실제 동작:

    1. 신규 승인 샘플 수 확인
    2. 기준 미달이면 종료
    3. GPU 확인
    4. 재학습 CSV 생성
    5. Candidate 모델 학습
    6. 현재 서비스 모델 Validation 평가
    7. Candidate vs Current 비교
    8. 통과 시에만 서비스 모델 승격
    9. 정상적으로 학습/평가가 끝난 사례를 사용 완료 처리

    모델 학습이나 평가 도중 오류가 발생하면
    case_key를 used_for_training 처리하지 않는다.
    """

    started_at = _now()

    model_version = (
        _make_model_version()
    )

    print("=" * 70)
    print("PhishGuard 신고 기반 Batch 재학습")
    print("=" * 70)

    print()
    print(
        "Model version:",
        model_version,
    )

    # --------------------------------------------------------
    # 1. Batch 조건 확인
    # --------------------------------------------------------

    status = (
        get_retraining_status()
    )

    print()
    print("[재학습 상태]")
    print(status)

    if not status["ready"]:

        print()
        print(
            "재학습 기준에 도달하지 않았습니다."
        )

        print(
            "Candidate 학습을 시작하지 않습니다."
        )

        return {
            "started": False,
            "completed": False,
            "ready": False,
            "model_version": model_version,
            "status": status,
            "reason": (
                "재학습에 필요한 신규 승인 "
                "샘플 수가 부족함"
            ),
        }

    # --------------------------------------------------------
    # 2. GPU 확인
    # --------------------------------------------------------

    device_status = (
        _get_device_status()
    )

    print()
    print("[학습 장치]")
    print(device_status)

    if not device_status[
        "cuda_available"
    ]:

        print()
        print(
            "CUDA GPU가 없어 실제 Candidate "
            "학습을 시작하지 않습니다."
        )

        return {
            "started": False,
            "completed": False,
            "ready": True,
            "model_version": model_version,
            "status": status,
            "device": device_status,
            "reason": (
                "GPU 학습 환경이 필요함"
            ),
        }

    # --------------------------------------------------------
    # 이후 heavy module은 실제 재학습 시에만 import
    # --------------------------------------------------------

    from ai.train_retraining_candidate import (
        build_retraining_dataset,
    )

    from ai.src.train_retraining_candidate_model import (
        run_candidate_training,
    )

    from ai.src.evaluate_current_service_model import (
        evaluate_current_service_model,
    )

    from ai.src.compare_models import (
        compare_models,
    )

    from ai.src.promote_candidate_model import (
        promote_candidate_model,
    )

    # --------------------------------------------------------
    # 3. 기존 데이터 + 신규 승인 데이터 병합
    # --------------------------------------------------------

    print()
    print("[1/5] 재학습 데이터 생성")

    dataset_result = (
        build_retraining_dataset()
    )

    if not dataset_result.get(
        "created",
        False,
    ):

        raise RuntimeError(
            "재학습 데이터 생성에 실패했습니다."
        )

    case_keys = list(
        dataset_result.get(
            "case_keys",
            [],
        )
    )

    if not case_keys:

        raise RuntimeError(
            "재학습에 사용할 case_key가 없습니다."
        )

    print(
        "재학습 고유 사례:",
        len(case_keys),
    )

    # --------------------------------------------------------
    # 4. Candidate 모델 학습
    # --------------------------------------------------------

    print()
    print("[2/5] Candidate 모델 학습")

    candidate_training_result = (
        run_candidate_training()
    )

    # --------------------------------------------------------
    # 5. Current 모델 평가
    # --------------------------------------------------------

    print()
    print("[3/5] 현재 서비스 모델 평가")

    current_metrics = (
        evaluate_current_service_model()
    )

    # Candidate validation 결과는
    # run_candidate_training() 내부에서 JSON으로 저장된다.

    # --------------------------------------------------------
    # 6. Current vs Candidate 비교
    # --------------------------------------------------------

    print()
    print("[4/5] Current vs Candidate 비교")

    comparison = (
        compare_models()
    )

    decision = comparison.get(
        "decision"
    )

    # --------------------------------------------------------
    # 7. PROMOTE일 때만 서비스 모델 교체
    # --------------------------------------------------------

    print()
    print("[5/5] 모델 승격 판단")

    promotion_result = (
        promote_candidate_model()
    )

    # --------------------------------------------------------
    # 8. 재학습 완료 사례 사용 처리
    #
    # REJECT여도 학습 + 평가까지 성공적으로 사용된 데이터이므로
    # 같은 데이터가 다음 batch에서 무한 반복되지 않게 처리한다.
    #
    # 단, 위 단계 중 오류가 발생하면 여기까지 오지 않으므로
    # used_for_training 처리가 되지 않는다.
    # --------------------------------------------------------

    used_result = (
        reputation
        .mark_training_samples_used(
            case_keys=case_keys,
            model_version=(
                f"{model_version}_{decision}"
            ),
        )
    )

    completed_at = _now()

    # --------------------------------------------------------
    # 최종 결과
    # --------------------------------------------------------

    result = {
        "started": True,
        "completed": True,
        "ready": True,

        "model_version": model_version,

        "started_at": started_at,
        "completed_at": completed_at,

        "device": device_status,

        "dataset": {
            "base_count": (
                dataset_result.get(
                    "base_count"
                )
            ),
            "new_count": (
                dataset_result.get(
                    "new_count"
                )
            ),
            "merged_count": (
                dataset_result.get(
                    "merged_count"
                )
            ),
            "case_keys": case_keys,
        },

        "current_metrics": (
            current_metrics
        ),

        "comparison": (
            comparison
        ),

        "decision": (
            decision
        ),

        "promotion": (
            promotion_result
        ),

        "training_samples_used": (
            used_result
        ),
    }

    result_path = (
        _save_pipeline_result(
            result=result,
            model_version=model_version,
        )
    )

    result[
        "result_path"
    ] = str(
        result_path
    )

    print()
    print("=" * 70)
    print("재학습 Pipeline 완료")
    print("=" * 70)

    print()
    print(
        "최종 판단:",
        decision,
    )

    print(
        "서비스 모델 변경:",
        promotion_result.get(
            "service_model_changed",
            False,
        ),
    )

    print(
        "사용 완료 처리:",
        used_result.get(
            "updated_count",
            0,
        ),
    )

    print()
    print(
        "Pipeline 결과:",
        result_path,
    )

    return result