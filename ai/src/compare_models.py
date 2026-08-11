from pathlib import Path
import json


# ============================================================
# 경로 설정
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent

CURRENT_RESULT_PATH = (
    PROJECT_ROOT
    / "results"
    / "current_service_model"
    / "validation_metrics.json"
)

CANDIDATE_RESULT_PATH = (
    PROJECT_ROOT
    / "results"
    / "retraining_candidate"
    / "validation_metrics.json"
)

COMPARE_RESULT_DIR = (
    PROJECT_ROOT
    / "results"
    / "model_comparison"
)

COMPARE_RESULT_PATH = (
    COMPARE_RESULT_DIR
    / "comparison_result.json"
)


# ============================================================
# 승격 기준
# ============================================================

# Candidate F1이 현재 모델보다 낮으면 승격 금지
MIN_F1_DELTA = 0.0

# Candidate Precision이 현재 모델보다 낮으면 승격 금지
MIN_PRECISION_DELTA = 0.0

# False Positive는 증가시키지 않음
MAX_FP_INCREASE = 0


# ============================================================
# JSON 로드
# ============================================================

def load_metrics(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"평가 결과 파일을 찾을 수 없습니다: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


# ============================================================
# Candidate 승격 판단
# ============================================================

def compare_models() -> dict:

    print("=" * 70)
    print("Current V3 vs Retraining Candidate 자동 비교")
    print("=" * 70)

    # --------------------------------------------------------
    # 결과 불러오기
    # --------------------------------------------------------

    current = load_metrics(
        CURRENT_RESULT_PATH
    )

    candidate = load_metrics(
        CANDIDATE_RESULT_PATH
    )

    # --------------------------------------------------------
    # Current 서비스 모델 metrics
    # --------------------------------------------------------

    current_f1 = float(
        current["f1"]
    )

    current_precision = float(
        current["precision"]
    )

    current_recall = float(
        current["recall"]
    )

    current_fp = int(
        current["fp"]
    )

    current_fn = int(
        current["fn"]
    )

    # --------------------------------------------------------
    # Candidate metrics
    #
    # Candidate JSON은 HuggingFace Trainer.evaluate()
    # 결과이므로 eval_ 접두사가 붙어 있음
    # --------------------------------------------------------

    candidate_f1 = float(
        candidate["eval_f1"]
    )

    candidate_precision = float(
        candidate["eval_precision"]
    )

    candidate_recall = float(
        candidate["eval_recall"]
    )

    candidate_fp = int(
        candidate["eval_fp"]
    )

    candidate_fn = int(
        candidate["eval_fn"]
    )

    # --------------------------------------------------------
    # 변화량
    # --------------------------------------------------------

    f1_delta = (
        candidate_f1
        - current_f1
    )

    precision_delta = (
        candidate_precision
        - current_precision
    )

    fp_increase = (
        candidate_fp
        - current_fp
    )

    # --------------------------------------------------------
    # 개별 통과 조건
    # --------------------------------------------------------

    f1_pass = (
        f1_delta
        >= MIN_F1_DELTA
    )

    precision_pass = (
        precision_delta
        >= MIN_PRECISION_DELTA
    )

    fp_pass = (
        fp_increase
        <= MAX_FP_INCREASE
    )

    # --------------------------------------------------------
    # 최종 승격 여부
    # --------------------------------------------------------

    promotion_pass = (
        f1_pass
        and precision_pass
        and fp_pass
    )

    # --------------------------------------------------------
    # 판단 사유
    # --------------------------------------------------------

    reasons = []

    if not f1_pass:
        reasons.append(
            "Candidate F1이 현재 모델보다 낮음"
        )

    if not precision_pass:
        reasons.append(
            "Candidate Precision이 현재 모델보다 낮음"
        )

    if not fp_pass:
        reasons.append(
            "Candidate False Positive가 증가함"
        )

    if promotion_pass:
        decision = "PROMOTE"

        reasons.append(
            "모든 승격 기준을 통과함"
        )

    else:
        decision = "REJECT"

    # --------------------------------------------------------
    # 결과 객체
    # --------------------------------------------------------

    result = {
        "decision": decision,
        "promotion": promotion_pass,

        "current": {
            "f1": current_f1,
            "precision": current_precision,
            "recall": current_recall,
            "fp": current_fp,
            "fn": current_fn,
        },

        "candidate": {
            "f1": candidate_f1,
            "precision": candidate_precision,
            "recall": candidate_recall,
            "fp": candidate_fp,
            "fn": candidate_fn,
        },

        "delta": {
            "f1": f1_delta,
            "precision": precision_delta,
            "fp_increase": fp_increase,
        },

        "checks": {
            "f1_pass": f1_pass,
            "precision_pass": precision_pass,
            "fp_pass": fp_pass,
        },

        "reasons": reasons,
    }

    # --------------------------------------------------------
    # 콘솔 출력
    # --------------------------------------------------------

    print()
    print("[Current]")

    print(
        f"F1        : {current_f1:.6f}"
    )

    print(
        f"Precision : {current_precision:.6f}"
    )

    print(
        f"Recall    : {current_recall:.6f}"
    )

    print(
        f"FP        : {current_fp}"
    )

    print(
        f"FN        : {current_fn}"
    )

    print()
    print("[Candidate]")

    print(
        f"F1        : {candidate_f1:.6f}"
    )

    print(
        f"Precision : {candidate_precision:.6f}"
    )

    print(
        f"Recall    : {candidate_recall:.6f}"
    )

    print(
        f"FP        : {candidate_fp}"
    )

    print(
        f"FN        : {candidate_fn}"
    )

    print()
    print("[Delta]")

    print(
        f"F1        : {f1_delta:+.6f}"
    )

    print(
        f"Precision : {precision_delta:+.6f}"
    )

    print(
        f"FP 증가   : {fp_increase:+d}"
    )

    print()
    print("[Checks]")

    print(
        f"F1 기준 통과        : {f1_pass}"
    )

    print(
        f"Precision 기준 통과 : {precision_pass}"
    )

    print(
        f"FP 기준 통과        : {fp_pass}"
    )

    print()
    print("=" * 70)

    print(
        "최종 판단:",
        decision,
    )

    for reason in reasons:
        print(
            "-",
            reason,
        )

    # --------------------------------------------------------
    # 결과 JSON 저장
    # --------------------------------------------------------

    COMPARE_RESULT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        COMPARE_RESULT_PATH,
        "w",
        encoding="utf-8",
    ) as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print()
    print(
        "비교 결과 저장:"
    )

    print(
        COMPARE_RESULT_PATH
    )

    return result


# ============================================================
# 실행
# ============================================================

if __name__ == "__main__":
    compare_models()