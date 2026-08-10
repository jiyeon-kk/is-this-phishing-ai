"""요청/응답 스키마 (계약 ①②③).

필드명·범위·null 규칙이 프론트(C)와의 계약. 여기 어긋나면 전체가 안 붙음.

- 필드명은 snake_case 고정 (risk_score O, riskScore X)
- 위험도(risk_score, weight, risk, signals 값)는 전부 0~1 실수
- level은 "safe" | "suspicious" | "danger" 셋 중 하나
- confidence는 "high" | "medium" | "low" 셋 중 하나
- cluster는 null 가능 (조직 매칭 안 되면 없음)
- review_reason은 재검토가 필요하지 않으면 null 가능
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field


# level 값 3종 고정 (계약 ①)
Level = Literal["safe", "suspicious", "danger"]

# 신뢰도 값 3종 고정
Confidence = Literal["high", "medium", "low"]


# --- ① /api/analyze ----------------------------------------------------
class AnalyzeRequest(BaseModel):
    text: str = Field(..., description="문자 본문")
    sender: Optional[str] = Field(
        None,
        description="발신번호 (선택, null 가능)",
    )


class Evidence(BaseModel):
    """탐지 근거 1건.

    rules/reputation이 내놓는 형식과 동일하며,
    이 형식이 그대로 /api/analyze의 evidence로 나가고
    explain 함수의 입력이 된다.
    """

    type: str = Field(
        ...,
        description="근거 종류 (예: '단축 URL')",
    )
    detail: str = Field(
        ...,
        description="구체 값 (예: 'bit.ly')",
    )
    weight: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="기여 가중치 0~1",
    )


class Signals(BaseModel):
    """신호별 원점수.

    프론트에서 문자모델·규칙·평판 3개 막대로 표시한다.
    """

    model: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="문자모델 점수 0~1",
    )
    rule: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="규칙 점수 0~1",
    )
    reputation: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="평판 점수 0~1",
    )


class Cluster(BaseModel):
    """매칭된 조직 클러스터 요약.

    조직 또는 캠페인과 매칭되지 않은 경우 cluster 전체가 null이다.
    """

    id: str = Field(
        ...,
        description="클러스터 id (예: '조직-0')",
    )
    size: int = Field(
        ...,
        ge=0,
        description="클러스터 노드 수",
    )
    report_count: int = Field(
        ...,
        ge=0,
        description="누적 신고 수",
    )
    risk: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="클러스터 위험도 0~1",
    )

class Campaign(BaseModel):
    """입력 문자와 연결된 유사 피싱 캠페인 요약."""

    matched: bool = Field(
        ...,
        description="유사 캠페인 매칭 여부",
    )

    campaign_id: str = Field(
        ...,
        description="캠페인 또는 클러스터 ID",
    )

    match_type: Literal["domain", "sender", "phrase"] = Field(
        ...,
        description="캠페인 연결 근거",
    )

    similar_case_count: int = Field(
        ...,
        ge=0,
        description="연결된 클러스터 전체 신고 수",
    )

    shared_domain_count: int = Field(
        ...,
        ge=0,
        description="동일 등록도메인을 공유한 신고 수",
    )

    shared_sender_count: int = Field(
        ...,
        ge=0,
        description="동일 발신번호를 공유한 신고 수",
    )

    similar_phrase_count: int = Field(
        ...,
        ge=0,
        description="유사 문구를 공유한 신고 수",
    )

    first_seen: Optional[str] = Field(
        None,
        description="캠페인 최초 신고 시각",
    )

    last_seen: Optional[str] = Field(
        None,
        description="캠페인 최근 신고 시각",
    )

    reports_last_24h: int = Field(
        ...,
        ge=0,
        description="최근 24시간 신고 수",
    )

    status: Literal[
        "rapidly_spreading",
        "active",
        "historical",
    ] = Field(
        ...,
        description="캠페인 활동 상태",
    )


class AnalyzeResponse(BaseModel):
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="사용자 화면에 표시하는 최종 위험도 0~1",
    )

    level: Level = Field(
        ...,
        description="safe | suspicious | danger",
    )

    reasons: list[str] = Field(
        default_factory=list,
        description="사람이 읽는 근거 문장 배열",
    )

    evidence: list[Evidence] = Field(
        default_factory=list,
        description="구조화된 탐지 근거 목록",
    )

    signals: Signals = Field(
        ...,
        description="문자모델·규칙·평판 신호별 원점수",
    )

    cluster: Optional[Cluster] = Field(
        None,
        description="조직 클러스터 요약 (매칭 없으면 null)",
    )

    campaign: Optional[Campaign] = Field(
    None,
    description="유사 피싱 캠페인 정보 (매칭 없으면 null)",
   )

    urls: list[str] = Field(
        default_factory=list,
        description="문자에서 추출된 URL 목록",
    )

    # --- 불확실성 기반 재검토 필드 -------------------------------
    confidence: Confidence = Field(
        ...,
        description=(
            "다중 신호 일치도를 바탕으로 계산한 시스템 판단 신뢰도: "
            "high | medium | low"
        ),
    )

    review_required: bool = Field(
        ...,
        description="사용자 또는 관리자의 추가 확인이 필요한지 여부",
    )

    review_reason: Optional[str] = Field(
        None,
        description=(
            "추가 확인이 필요한 이유. "
            "review_required가 false이면 null 가능"
        ),
    )

    signal_agreement: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "문자모델·규칙·평판 신호 간 일치도 0~1. "
            "1에 가까울수록 신호가 서로 유사함"
        ),
    )

    signal_disagreement: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description=(
            "문자모델·규칙·평판 신호 간 불일치도 0~1. "
            "1에 가까울수록 판단 차이가 큼"
        ),
    )


# --- ② /api/graph ------------------------------------------------------
class GraphNode(BaseModel):
    id: str = Field(
        ...,
        description="노드 id (예: 'url:xnr.ae1t.yachts')",
    )
    label: str = Field(
        ...,
        description="화면 표시 라벨",
    )
    type: Literal["number", "url", "phrase"] = Field(
        ...,
        description="노드 종류 (색 구분)",
    )
    cluster: int = Field(
        ...,
        description="클러스터 정수 id (그룹/색 묶음)",
    )


class GraphEdge(BaseModel):
    # 프론트 라이브러리 react-force-graph는 links를 기대하므로
    # 프론트에서 edges를 links로 이름만 매핑한다.
    source: str = Field(
        ...,
        description="시작 노드 id",
    )
    target: str = Field(
        ...,
        description="끝 노드 id",
    )


class GraphResponse(BaseModel):
    nodes: list[GraphNode] = Field(
        default_factory=list,
    )
    edges: list[GraphEdge] = Field(
        default_factory=list,
    )
    cluster_count: int = Field(
        0,
        ge=0,
        description="클러스터 개수",
    )


# --- ③ /api/report -----------------------------------------------------
class ReportRequest(BaseModel):
    text: str = Field(
        ...,
        description="신고할 문자 본문",
    )
    sender: Optional[str] = Field(
        None,
        description="발신번호 (선택)",
    )


ReportStatus = Literal[
    "pending",
    "suspected",
    "confirmed",
    "false_positive",
]

class ReportResponse(BaseModel):
    ok: bool = Field(
        True,
        description="신고 접수 여부",
    )

    cluster_count: int = Field(
        ...,
        ge=0,
        description="갱신 후 클러스터 개수",
    )

    status: ReportStatus = Field(
        ...,
        description=(
            "신고 검증 상태: "
            "pending | suspected | confirmed | false_positive"
        ),
    )

    report_count: int = Field(
        ...,
        ge=1,
        description="동일 사례의 누적 신고 횟수",
    )


# --- ④ /api/trends -----------------------------------------------------
# 사용자 신고(source='user')만 집계한다.
# 프론트 normalize.js가 label/count를 읽는다.
class TrendItem(BaseModel):
    label: str = Field(
        ...,
        description="문구 또는 도메인",
    )
    count: int = Field(
        ...,
        ge=0,
        description="사용자 신고 등장 횟수",
    )


class TrendsResponse(BaseModel):
    top_phrases: list[TrendItem] = Field(
        default_factory=list,
        description="최다 신고 문구 (사용자 신고 기준)",
    )
    top_urls: list[TrendItem] = Field(
        default_factory=list,
        description="최다 신고 도메인 (사용자 신고 기준)",
    )


# --- 헬스체크 ----------------------------------------------------------
class HealthResponse(BaseModel):
    status: str = Field(
        "ok",
        description="서버 상태",
    )

class AdversarialRequest(BaseModel):
    text: str = Field(
        ...,
        description="우회 공격 변형을 생성할 원본 문자",
    )


class AdversarialVariant(BaseModel):
    type: str = Field(
        ...,
        description="변형 유형 식별자",
    )

    label: str = Field(
        ...,
        description="화면 표시용 변형 유형명",
    )

    text: str = Field(
        ...,
        description="변형된 문자",
    )


class AdversarialResponse(BaseModel):
    original: str = Field(
        ...,
        description="원본 문자",
    )

    variants: list[AdversarialVariant] = Field(
        default_factory=list,
        description="생성된 우회 변형 목록",
    )

class ThreatFeedItem(BaseModel):
    id: str
    source: str
    title: str
    published_at: str
    category: str
    summary: str
    keywords: list[str] = Field(default_factory=list)
    url: str


class ThreatFeedResponse(BaseModel):
    items: list[ThreatFeedItem] = Field(default_factory=list)