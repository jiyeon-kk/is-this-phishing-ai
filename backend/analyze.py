"""분석 오케스트레이터 (계약 ①⑤ 관통).

문자 한 건을 받아 신호들을 모아 최종 응답(dict)을 조립한다:

    preprocess
        → classifier(model)
        → backend.rules(text rule)
        → ai.url_rule_engine(URL structure rule)
        → reputation(rep)
        → graph(cluster)
        → fusion.fuse
        → (cluster면 소폭 가산)
        → 정상 정보성 문자 오탐 완화
        → fusion.level
        → 화면 표시용 위험도 보정
        → 불확실성·재검토 판단
        → explain
        → AnalyzeResponse 형태 dict

엔진(classifier·rules·url_rule_engine·reputation·graph)은 각 모듈 임포트 시
초기화되어 프로세스 내에서 재사용된다.

신고(/api/report)로 데이터가 바뀌면 graph.invalidate()로 그래프만 갱신한다
(record_report 참고).
"""

from ai import fusion
from ai.classifier import predict_proba
from ai.preprocess import preprocess
from ai.url_rule_engine import analyze as analyze_url_rules
from backend import graph, reputation, rules
from backend.explain import explain


# ============================================================
# 기본 설정
# ============================================================

# 클러스터에 걸릴 때 위험도 가산량.
# 조직 위험도에 비례해 내부 판정 점수에 소폭 반영한다.
_CLUSTER_BONUS = 0.10


def _is_strong_cluster(cluster: dict | None) -> bool:
    """최종 판단/신뢰도에 반영해도 되는 강한 클러스터인지 확인."""
    if not cluster:
        return False

    match_type = cluster.get("match_type")

    if match_type in {"domain", "sender"}:
        return True

    if match_type == "strong_phrase":
        return (
            int(cluster.get("shared_phrase_count", 0)) >= 2
            and int(cluster.get("similar_phrase_count", 0)) >= 2
        )

    return False


# ============================================================
# 불확실성 판단 기준
# ============================================================

_REVIEW_SCORE_LOW = 0.35
_REVIEW_SCORE_HIGH = 0.75

# 모델·규칙·평판 신호의 최대 차이가 이 값 이상이면
# 신호 불일치가 큰 것으로 판단한다.
_HIGH_DISAGREEMENT_THRESHOLD = 0.45

# 신호 일치도 등급 기준
_HIGH_AGREEMENT_THRESHOLD = 0.75
_MEDIUM_AGREEMENT_THRESHOLD = 0.55


# ============================================================
# 정상 정보성 문자 오탐 완화용 패턴
# ============================================================

# 실제 카드 승인·입출금·결제 안내에서 자주 나타나는 표현.
#
# 주의:
# 이 표현 하나만 있다고 안전 처리하지 않는다.
# 아래 _apply_benign_adjustment()에서
#
#   정상 정보 패턴 존재
#   + URL 없음
#   + 행동 요구 없음
#   + 규칙 위험 신호 없음
#   + 평판 위험 신호 없음
#   + 위험 클러스터 없음
#
# 을 모두 만족할 때만 모델 단독 오탐을 완화한다.
_BENIGN_TRANSACTION_PATTERNS = (
    "정상 승인",
    "승인되었습니다",
    "승인 되었습니다",
    "결제가 완료되었습니다",
    "결제 완료",
    "이용금액",
    "결제금액",
    "승인금액",
    "입금되었습니다",
    "입금 되었습니다",
    "출금되었습니다",
    "출금 되었습니다",
    "자동이체",
    "이용내역",
)


# 피싱 문자에서 자주 등장하는 행동 유도 표현.
#
# 정상 거래 표현이 있더라도 아래 표현이 존재하면
# benign adjustment를 적용하지 않는다.
_ACTION_REQUEST_PATTERNS = (
    "확인해주세요",
    "확인해 주세요",
    "확인 바랍니다",
    "확인바랍니다",
    "즉시 확인",
    "지금 확인",
    "아래 링크",
    "아래 주소",
    "링크를",
    "링크에서",
    "접속해주세요",
    "접속해 주세요",
    "접속 바랍니다",
    "클릭해주세요",
    "클릭해 주세요",
    "인증해주세요",
    "인증해 주세요",
    "본인인증",
    "본인 인증",
    "취소해주세요",
    "취소해 주세요",
    "입력해주세요",
    "입력해 주세요",
    "설치해주세요",
    "설치해 주세요",
    "앱 설치",
    "어플 설치",
    "송금해주세요",
    "송금해 주세요",
    "이체해주세요",
    "이체해 주세요",
    "연락해주세요",
    "연락해 주세요",
    "본인이 아닐 경우",
    "본인이 아니시면",
    "본인 거래가 아닐 경우",
    "계좌가 정지",
    "계좌 정지",
    "카드가 정지",
    "카드 정지",
)


# ============================================================
# Evidence 중복 제거
# ============================================================

def _dedupe_evidence(items: list[dict]) -> list[dict]:
    """중복되거나 의미가 겹치는 evidence를 제거한다."""

    seen = set()
    result = []

    # 기존 backend.rules와 신규 URL 규칙엔진 양쪽에서
    # 같은 의미로 생성될 가능성이 큰 URL 구조 근거들.
    dedupe_by_type = {
        "의심 TLD",
        "단축 URL",
        "IP 주소",
        "IP 주소 직접 사용",
        "Punycode",
    }

    for item in items:
        evidence_type = item.get("type")
        detail = item.get("detail")

        # URL 구조 근거는 같은 type이면 하나만 유지한다.
        if evidence_type in dedupe_by_type:
            key = (evidence_type,)
        else:
            # 일반 근거는 type과 detail이 모두 같은 경우만 제거한다.
            key = (evidence_type, detail)

        if key in seen:
            continue

        seen.add(key)
        result.append(item)

    return result


# ============================================================
# 정상 정보성 문자 오탐 완화
# ============================================================

def _apply_benign_adjustment(
    text: str,
    internal_score: float,
    rule_s: float,
    rep_s: float,
    urls: list,
    cluster: dict | None,
) -> float:
    """정상 거래 알림에 대한 모델 단독 오탐을 완화한다.

    단순 화이트리스트 방식이 아니다.

    정상 거래·승인 안내 패턴이 존재하면서 동시에

        - URL이 없고
        - 사용자의 즉각적인 행동을 요구하지 않고
        - 문자/URL 규칙 위험도가 낮고
        - 신고·평판 위험도가 낮고
        - 반복 신고 기반 위험 클러스터가 없을 때

    에만 모델의 과도한 위험 점수를 제한한다.

    따라서 피싱 공격자가 단순히 '정상 승인' 같은 단어를
    추가하는 것만으로는 안전 판정을 받을 수 없다.
    """

    normalized_text = text.lower().strip()

    # --------------------------------------------------------
    # 1. 정상적인 거래·승인 안내 표현 존재 여부
    # --------------------------------------------------------
    has_benign_pattern = any(
        pattern.lower() in normalized_text
        for pattern in _BENIGN_TRANSACTION_PATTERNS
    )

    # --------------------------------------------------------
    # 2. 사용자의 행동을 요구하는 표현 존재 여부
    # --------------------------------------------------------
    has_action_request = any(
        pattern.lower() in normalized_text
        for pattern in _ACTION_REQUEST_PATTERNS
    )

    # --------------------------------------------------------
    # 3. URL 포함 여부
    # --------------------------------------------------------
    has_url = bool(urls)

    # --------------------------------------------------------
    # 4. 클러스터 위험도
    # --------------------------------------------------------
    cluster_risk = (
        float(cluster.get("risk", 0.0))
        if cluster
        else 0.0
    )

    cluster_report_count = (
        int(cluster.get("report_count", 0))
        if cluster
        else 0
    )

    strong_cluster_risk = (
        _is_strong_cluster(cluster)
        and cluster_risk >= 0.50
        and cluster_report_count >= 2
    )

    # --------------------------------------------------------
    # 5. 모델 외부의 위험 근거가 있는지 확인
    # --------------------------------------------------------
    has_external_risk = (
        rule_s >= 0.10
        or rep_s >= 0.10
        or strong_cluster_risk
    )

    # --------------------------------------------------------
    # 6. 정상 정보성 문자로 판단 가능한 경우만 완화
    # --------------------------------------------------------
    if (
        has_benign_pattern
        and not has_action_request
        and not has_url
        and not has_external_risk
    ):
        # 모델이 0.99 같은 높은 값을 내더라도
        # 다른 위험 근거가 전혀 없는 정상 거래 알림이라면
        # 내부 위험도를 최대 0.25로 제한한다.
        return round(min(internal_score, 0.25), 4)

    return round(internal_score, 4)


# ============================================================
# 사용자 화면용 위험도 변환
# ============================================================

def _to_display_score(
    internal_score: float,
    model_p: float,
    rule_s: float,
    rep_s: float,
    cluster: dict | None,
) -> float:
    """내부 판정 점수를 사용자 화면용 위험도로 보수적으로 변환한다.

    model_p는 아직 보정되지 않은 분류모델 확률이므로,
    화면에서 확정 확률처럼 그대로 해석하지 않는다.

    강한 보조 근거 수에 따라 표시 가능한 상한을 조정한다.
    """

    cluster_risk = (
        float(cluster.get("risk", 0.0))
        if cluster
        else 0.0
    )

    strong_rule = rule_s >= 0.30
    strong_reputation = rep_s >= 0.30

    strong_cluster = (
        _is_strong_cluster(cluster)
        and cluster_risk >= 0.50
        and int(cluster.get("report_count", 0)) >= 2
    )

    corroborating_count = sum(
        [
            strong_rule,
            strong_reputation,
            strong_cluster,
        ]
    )

    if corroborating_count == 0:
        cap = 0.70
    elif corroborating_count == 1:
        cap = 0.93
    elif corroborating_count == 2:
        cap = 0.96
    else:
        cap = 0.98

    return round(min(internal_score, cap), 4)


# ============================================================
# 불확실성 / 재검토 판단
# ============================================================

def _calculate_uncertainty(
    model_p: float,
    rule_s: float,
    rep_s: float,
    internal_score: float,
    cluster: dict | None,
) -> dict:
    """신호의 판단 방향과 근거 강도를 기준으로 재검토 여부를 계산한다."""

    cluster_risk = (
        float(cluster.get("risk", 0.0))
        if cluster
        else 0.0
    )

    cluster_report_count = (
        int(cluster.get("report_count", 0))
        if cluster
        else 0
    )

    # --------------------------------------------------------
    # 위험을 지지하는 기준
    # --------------------------------------------------------
    model_risk = model_p >= 0.70
    rule_risk = rule_s >= 0.30
    reputation_risk = rep_s >= 0.30

    # 클러스터는 단순 매칭만으로 강한 근거로 보지 않는다.
    # 위험도와 반복 신고가 함께 확인되어야 위험 신호로 인정한다.
    cluster_risk_support = (
        _is_strong_cluster(cluster)
        and cluster_risk >= 0.50
        and cluster_report_count >= 2
    )

    # --------------------------------------------------------
    # 안전을 지지하는 기준
    # --------------------------------------------------------
    model_safe = model_p <= 0.30
    rule_safe = rule_s < 0.10
    reputation_safe = rep_s < 0.10

    # 클러스터가 없거나 신고 1건 수준의 약한 연결은
    # 위험을 뒷받침하지 못한 상태로 본다.
    cluster_safe = not cluster_risk_support

    risk_support_count = sum(
        [
            model_risk,
            rule_risk,
            reputation_risk,
            cluster_risk_support,
        ]
    )

    safe_support_count = sum(
        [
            model_safe,
            rule_safe,
            reputation_safe,
            cluster_safe,
        ]
    )

    review_reasons = []

    # --------------------------------------------------------
    # 최종 점수가 안전/위험 경계 구간인 경우
    # --------------------------------------------------------
    if 0.40 <= internal_score < 0.70:
        review_reasons.append(
            "최종 위험도가 안전과 위험의 경계 구간에 있습니다."
        )

    # --------------------------------------------------------
    # 모델만 위험을 지지하고
    # 규칙·평판·반복 신고 근거가 없는 경우
    # --------------------------------------------------------
    if model_risk and risk_support_count == 1:
        review_reasons.append(
            "문자 모델은 높은 위험을 예측했지만 이를 뒷받침하는 "
            "규칙·평판·반복 신고 근거가 부족합니다."
        )

    # --------------------------------------------------------
    # 모델은 안전인데 보조 신호 여러 개가 위험한 경우
    # --------------------------------------------------------
    if model_safe and risk_support_count >= 2:
        review_reasons.append(
            "문자 모델과 규칙·평판·클러스터 판단이 서로 충돌합니다."
        )

    review_required = bool(review_reasons)

    # --------------------------------------------------------
    # 신뢰도 결정
    # --------------------------------------------------------
    if review_required:
        confidence = "low"
    elif risk_support_count >= 3:
        confidence = "high"
    elif safe_support_count >= 3:
        confidence = "high"
    elif risk_support_count >= 2 or safe_support_count >= 2:
        confidence = "medium"
    else:
        confidence = "low"

    dominant_count = max(
        risk_support_count,
        safe_support_count,
    )

    signal_agreement = round(dominant_count / 4, 4)
    signal_disagreement = round(1.0 - signal_agreement, 4)

    return {
        "confidence": confidence,
        "review_required": review_required,
        "review_reason": (
            " ".join(review_reasons)
            if review_reasons
            else None
        ),
        "signal_agreement": signal_agreement,
        "signal_disagreement": signal_disagreement,
    }


# ============================================================
# 문자 분석
# ============================================================

def analyze(text: str, sender: str | None = None) -> dict:
    """문자 -> AnalyzeResponse 형태 dict (계약 ①)."""

    # --------------------------------------------------------
    # 0. 전처리
    # --------------------------------------------------------
    pre = preprocess(text, sender)

    # --------------------------------------------------------
    # 1. 문자 분류 모델
    # --------------------------------------------------------
    model_p = predict_proba(pre["masked"])

    # numpy float 등이 반환되어도 JSON 직렬화 가능하도록
    # Python float로 변환한다.
    model_p = float(model_p)

    # --------------------------------------------------------
    # 2. 기존 문자 키워드·블록리스트 규칙
    # --------------------------------------------------------
    text_rule_s, text_rule_ev = rules.analyze(pre)
    text_rule_s = float(text_rule_s)

    # --------------------------------------------------------
    # 3. 신규 URL 구조 규칙
    # --------------------------------------------------------
    url_rule_s, url_rule_ev = analyze_url_rules(pre)
    url_rule_s = float(url_rule_s)

    # 기존 규칙과 URL 규칙의 중복 과대합산을 막기 위해
    # 두 점수 중 더 큰 값을 대표 규칙 점수로 사용한다.
    rule_s = max(
        text_rule_s,
        url_rule_s,
    )

    # 기존 규칙과 URL 규칙 evidence 통합 + 중복 제거
    rule_ev = _dedupe_evidence(
        text_rule_ev + url_rule_ev
    )

    # --------------------------------------------------------
    # 4. 평판 신호
    # --------------------------------------------------------
    rep_s, rep_ev = reputation.lookup(pre)
    rep_s = float(rep_s)

    # --------------------------------------------------------
    # 5. 그래프 / 캠페인 신호
    # --------------------------------------------------------
    cluster = graph.match_cluster(pre)
    campaign = graph.match_campaign(pre)

    # --------------------------------------------------------
    # 6. 기본 Fusion
    # --------------------------------------------------------
    #
    # model_p를 기본 위험도로 사용하고
    # rule_s / rep_s가 위험도를 보조한다.
    internal_score = fusion.fuse(
        model_p,
        rule_s,
        rep_s,
    )

    internal_score = float(internal_score)

    # --------------------------------------------------------
    # 7. 조직 클러스터 위험도 반영
    # --------------------------------------------------------
    if _is_strong_cluster(cluster):
        cluster_risk = float(
            cluster.get("risk", 0.0)
        )

        internal_score = round(
            internal_score
            + (1.0 - internal_score)
            * _CLUSTER_BONUS
            * cluster_risk,
            4,
        )

    # --------------------------------------------------------
    # 8. 정상 정보성 문자에 대한 모델 단독 오탐 완화
    # --------------------------------------------------------
    #
    # 예:
    #
    # [KB국민은행]
    # 체크카드 이용금액 23,500원이 정상 승인되었습니다.
    #
    # 모델만 높은 확률을 내지만
    # URL / 행동 유도 / 규칙 / 평판 / 반복신고 근거가
    # 전혀 없다면 위험도를 낮춘다.
    #
    # 반대로 아래처럼 행동 유도나 URL이 있다면
    # 완화를 적용하지 않는다.
    #
    # "980,000원이 승인되었습니다.
    #  본인이 아닐 경우 아래 링크에서 취소해주세요."
    #
    internal_score = _apply_benign_adjustment(
        text=text,
        internal_score=internal_score,
        rule_s=rule_s,
        rep_s=rep_s,
        urls=pre["urls"],
        cluster=cluster,
    )

    # --------------------------------------------------------
    # 9. 최종 판정 등급
    # --------------------------------------------------------
    #
    # 중요:
    # benign adjustment 이후 점수를 사용해야
    # 정상 금융 문자의 level도 함께 내려간다.
    level = fusion.level(internal_score)

    # --------------------------------------------------------
    # 10. 화면 표시용 위험도
    # --------------------------------------------------------
    display_score = _to_display_score(
        internal_score=internal_score,
        model_p=model_p,
        rule_s=rule_s,
        rep_s=rep_s,
        cluster=cluster,
    )

    # --------------------------------------------------------
    # 11. 불확실성 및 재검토 필요 여부
    # --------------------------------------------------------
    uncertainty = _calculate_uncertainty(
        model_p=model_p,
        rule_s=rule_s,
        rep_s=rep_s,
        internal_score=internal_score,
        cluster=cluster,
    )

    # --------------------------------------------------------
    # 12. Evidence 통합
    # --------------------------------------------------------
    evidence = _dedupe_evidence(
        rule_ev + rep_ev
    )

    # --------------------------------------------------------
    # 13. 원본 신호 저장
    # --------------------------------------------------------
    #
    # 모델이 정상 금융 문자를 0.99로 잘못 판단했더라도
    # 여기에는 원래 모델 값이 그대로 남는다.
    #
    # 따라서 나중에
    # "모델 단독 판단 vs 다중 신호 최종 판단"
    # 분석에도 사용할 수 있다.
    signals = {
        "model": round(model_p, 4),
        "rule": round(rule_s, 4),
        "reputation": round(rep_s, 4),
    }

    # --------------------------------------------------------
    # 14. 사용자 설명 생성
    # --------------------------------------------------------
    reasons = explain(
        evidence,
        level,
        display_score,
        cluster,
    )

    # --------------------------------------------------------
    # 15. API 응답
    # --------------------------------------------------------
    return {
        # 프론트에서는 기존처럼
        # risk_score × 100으로 표시하면 된다.
        "risk_score": display_score,

        "level": level,
        "reasons": reasons,
        "evidence": evidence,
        "signals": signals,
        "cluster": cluster,
        "campaign": campaign,
        "urls": pre["urls"],

        # 불확실성 기반 재검토 정보
        "confidence": uncertainty["confidence"],
        "review_required": uncertainty["review_required"],
        "review_reason": uncertainty["review_reason"],
        "signal_agreement": uncertainty["signal_agreement"],
        "signal_disagreement": uncertainty["signal_disagreement"],
    }


# ============================================================
# 사용자 신고 저장
# ============================================================

def record_report(
    text: str,
    sender: str | None = None,
) -> dict:
    """신고 저장 + 그래프 갱신.

    저장된 신고의 상태와 누적 신고 수,
    갱신 후 클러스터 개수를 함께 반환한다.
    """

    saved_report = reputation.add_report(
        text,
        sender,
    )

    # 신고 데이터가 바뀌었으므로
    # 그래프 캐시 무효화
    graph.invalidate()

    cluster_count = graph.to_json()[
        "cluster_count"
    ]

    return {
        "cluster_count": cluster_count,
        "status": saved_report["status"],
        "report_count": saved_report["report_count"],
    }