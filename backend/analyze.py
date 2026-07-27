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
        → fusion.level
        → 화면 표시용 위험도 보정
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

# 클러스터에 걸릴 때 위험도 가산량.
# 조직 위험도에 비례해 내부 판정 점수에 소폭 반영한다.
_CLUSTER_BONUS = 0.10


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


def _to_display_score(
    internal_score: float,
    rule_s: float,
    rep_s: float,
    cluster: dict | None,
) -> float:
    """내부 판정 점수를 사용자 화면용 위험도로 보수적으로 변환한다.

    내부 판정 점수와 level은 변경하지 않는다.

    보조 위험 신호가 없는 모델 단독 판단:
        화면 표시 최대 95%

    규칙·평판·클러스터 중 1개가 함께 확인됨:
        화면 표시 최대 98%

    규칙·평판·클러스터 중 2개 이상이 함께 확인됨:
        화면 표시 최대 99%

    따라서 모델이 과도하게 높은 확률을 출력하더라도
    사용자 화면에 100% 확정처럼 표시되는 것을 방지한다.
    """

    corroborating_count = sum(
        [
            rule_s > 0,
            rep_s > 0,
            cluster is not None,
        ]
    )

    if corroborating_count == 0:
        cap = 0.95
    elif corroborating_count == 1:
        cap = 0.98
    else:
        cap = 0.99

    return round(min(internal_score, cap), 4)


def analyze(text: str, sender: str | None = None) -> dict:
    """문자 -> AnalyzeResponse 형태 dict (계약 ①)."""

    pre = preprocess(text, sender)

    # 1. 문자 분류 모델
    model_p = predict_proba(pre["masked"])

    # 2. 기존 문자 키워드·블록리스트 규칙
    text_rule_s, text_rule_ev = rules.analyze(pre)

    # 3. 신규 URL 구조 규칙
    url_rule_s, url_rule_ev = analyze_url_rules(pre)

    # 기존 규칙과 URL 규칙의 중복 과대합산을 막기 위해
    # 두 점수 중 더 큰 값을 대표 규칙 점수로 사용한다.
    rule_s = max(text_rule_s, url_rule_s)

    # 기존 규칙과 URL 규칙 evidence를 통합하고 중복 제거한다.
    rule_ev = _dedupe_evidence(text_rule_ev + url_rule_ev)

    # 4. 평판·그래프 신호
    rep_s, rep_ev = reputation.lookup(pre)
    cluster = graph.match_cluster(pre)

    # 5. 최신 fusion
    # model_p를 기본 위험도로 유지하면서
    # rule_s와 rep_s가 위험도를 올리기만 한다.
    internal_score = fusion.fuse(model_p, rule_s, rep_s)

    # 조직 클러스터에 걸리면 내부 판정 위험도를 소폭 가산한다.
    if cluster:
        internal_score = round(
            min(
                1.0,
                internal_score + _CLUSTER_BONUS * cluster["risk"],
            ),
            4,
        )

    # 판정 등급은 성능 보존을 위해 내부 점수를 기준으로 계산한다.
    level = fusion.level(internal_score)

    # 사용자 화면에는 100%가 쉽게 노출되지 않도록
    # 보조 신호 수를 고려한 표시용 위험도를 사용한다.
    display_score = _to_display_score(
        internal_score=internal_score,
        rule_s=rule_s,
        rep_s=rep_s,
        cluster=cluster,
    )

    # rules + URL rules + reputation evidence 통합
    evidence = _dedupe_evidence(rule_ev + rep_ev)

    # signals 순서 고정: model → rule → reputation (계약 ①)
    signals = {
        "model": model_p,
        "rule": rule_s,
        "reputation": rep_s,
    }

    # 사용자에게 보여줄 설명도 표시용 위험도를 기준으로 생성한다.
    reasons = explain(
        evidence,
        level,
        display_score,
        cluster,
    )

    return {
        # 프론트에서 기존처럼 risk_score × 100으로 표시하면 된다.
        "risk_score": display_score,
        "level": level,
        "reasons": reasons,
        "evidence": evidence,
        "signals": signals,
        "cluster": cluster,
        "urls": pre["urls"],
    }


def record_report(text: str, sender: str | None = None) -> int:
    """신고 저장 + 그래프 갱신.

    갱신 후 cluster_count 반환 (/api/report 용).
    """

    reputation.add_report(text, sender)

    # 데이터가 변경되었으므로 다음 접근 때 그래프 재계산
    graph.invalidate()

    return graph.to_json()["cluster_count"]