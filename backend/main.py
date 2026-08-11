"""FastAPI 진입점 (계약 ①②③⑦).

실행: 레포 최상위에서
uvicorn backend.main:app --reload

엔드포인트:
GET  /api/health       헬스체크
POST /api/analyze      문자 분석 (계약 ①)
GET  /api/graph        조직 그래프 (계약 ②)
POST /api/report       신고 저장 + 그래프 갱신 (계약 ③)
GET  /api/trends       신고 트렌드 (유저 신고만 집계, 계약 ④)
POST /api/adversarial  우회 문자 변형 생성
GET  /api/threat-feed  공식기관 최신 피싱 정보

엔진(classifier·rules·reputation·graph)은 서버 시작 시 lifespan 에서 1회
초기화해 프로세스 내내 재사용한다.

공식기관 피싱 정보는 threat_feed 백그라운드 updater가
30분 주기로 자동 갱신한다.

신고로 데이터가 바뀌면 그래프만 갱신된다.
CORS 허용 오리진은 config 에서 가져온다(전원 공유, 계약 ⑦).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config

from backend import analyze as analyze_svc
from backend import graph, reputation
from backend import threat_feed as threat_feed_svc
from backend import trends as trends_svc
from backend.adversarial_transform import generate_variants
from backend.schemas import (
    AdversarialRequest,
    AdversarialResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    GraphResponse,
    HealthResponse,
    ReportRequest,
    ReportResponse,
    ThreatFeedResponse,
    TrendsResponse,
)


# ============================================================
# 서버 Lifespan
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 필요한 초기화 작업."""

    # --------------------------------------------------------
    # 서버 시작 시 1회 초기화
    # --------------------------------------------------------

    # 신고 DB 테이블 생성 + 빈 경우 시드 삽입
    reputation.init_db()

    # 그래프 캐시 초기화
    graph.invalidate()

    # 그래프 미리 계산
    # 첫 /api/graph 요청 시 지연을 줄이기 위한 워밍업
    graph_data = graph.to_json()

    # 공식기관 최신 피싱 정보
    # 30분 주기 백그라운드 자동 갱신 시작
    threat_feed_svc.start_background_updater()

    print(
        "[startup] 엔진 초기화 완료 "
        f"(reports={reputation.report_count()}, "
        f"clusters={graph_data['cluster_count']})"
    )

    yield

    # --------------------------------------------------------
    # 서버 종료
    # --------------------------------------------------------
    # 현재 별도로 정리할 자원 없음


# ============================================================
# FastAPI 앱
# ============================================================

app = FastAPI(
    title="PhishGuard API",
    version="0.1.0",
    lifespan=lifespan,
)


# ============================================================
# CORS (계약 ⑦)
# ============================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Health
# ============================================================

@app.get(
    "/api/health",
    response_model=HealthResponse,
)
def health() -> HealthResponse:
    """서버 상태 확인."""

    return HealthResponse(
        status="ok"
    )


# ============================================================
# 문자 분석 (계약 ①)
# ============================================================

@app.post(
    "/api/analyze",
    response_model=AnalyzeResponse,
)
def analyze(
    req: AnalyzeRequest,
) -> dict:
    """문자 한 건 분석.

    반환:
    - 위험도
    - 판단 신뢰도
    - 탐지 근거
    - 개별 신호
    - 연관 피싱 사례
    """

    return analyze_svc.analyze(
        req.text,
        req.sender,
    )


# ============================================================
# 그래프 (계약 ②)
# ============================================================

@app.get(
    "/api/graph",
    response_model=GraphResponse,
)
def get_graph() -> dict:
    """연관 피싱 사례 그래프."""

    return graph.to_json()


# ============================================================
# 신고 (계약 ③)
# ============================================================

@app.post(
    "/api/report",
    response_model=ReportResponse,
)
def report(
    req: ReportRequest,
) -> ReportResponse:
    """신고 저장 + 그래프 갱신 + 신고 상태 반환."""

    result = analyze_svc.record_report(
        req.text,
        req.sender,
    )

    return ReportResponse(
        ok=True,
        cluster_count=result["cluster_count"],
        status=result["status"],
        report_count=result["report_count"],
    )


# ============================================================
# 신고 트렌드 (계약 ④)
# ============================================================

@app.get(
    "/api/trends",
    response_model=TrendsResponse,
)
def get_trends() -> dict:
    """유저 신고(source='user') 기반 피싱 트렌드."""

    return trends_svc.get_trends()


# ============================================================
# 우회 공격 시뮬레이션
# ============================================================

@app.post(
    "/api/adversarial",
    response_model=AdversarialResponse,
)
def generate_adversarial(
    req: AdversarialRequest,
) -> dict:
    """원본 문자에서 데모용 우회 변형을 생성한다."""

    return {
        "original": req.text,
        "variants": generate_variants(
            req.text
        ),
    }


# ============================================================
# 공식기관 최신 피싱 정보
# ============================================================

@app.get(
    "/api/threat-feed",
    response_model=ThreatFeedResponse,
)
def get_threat_feed() -> dict:
    """공식기관 최신 피싱·스미싱 정보를 반환한다."""

    return {
        "items": threat_feed_svc.get_feed()
    }