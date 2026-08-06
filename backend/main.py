"""FastAPI 진입점 (계약 ①②③⑦).

실행: 레포 최상위에서
    uvicorn backend.main:app --reload

엔드포인트:
    GET  /api/health   헬스체크
    POST /api/analyze  문자 분석 (계약 ①)
    GET  /api/graph    조직 그래프 (계약 ②)
    POST /api/report   신고 저장 + 그래프 갱신 (계약 ③)
    GET  /api/trends   위협 트렌드 (유저 신고만 집계, 계약 ④)

엔진(classifier·rules·reputation·graph)은 서버 시작 시 lifespan 에서 1회
초기화해 프로세스 내내 재사용. 신고로 데이터가 바뀌면 그래프만 갱신됨.
CORS 허용 오리진은 config 에서 가져옴(전원 공유, 계약 ⑦).
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.adversarial_transform import generate_variants

import config
from backend import analyze as analyze_svc
from backend import graph, reputation
from backend import trends as trends_svc
from backend.schemas import (
    AdversarialRequest,
    AdversarialResponse,
    AnalyzeRequest,
    AnalyzeResponse,
    GraphResponse,
    HealthResponse,
    ReportRequest,
    ReportResponse,
    TrendsResponse,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- 서버 시작 시 1회 초기화 ---
    reputation.init_db()      # 테이블 생성 + 시드(빈 경우)
    graph.invalidate()        # 캐시 초기화 후
    graph.to_json()           # 그래프 미리 계산(워밍업) → 첫 요청 지연 제거
    print("[startup] 엔진 초기화 완료 "
          f"(reports={reputation.report_count()}, "
          f"clusters={graph.to_json()['cluster_count']})")
    yield
    # --- 종료 시 정리할 자원 없음 ---


app = FastAPI(title="PhishGuard API", version="0.1.0", lifespan=lifespan)

# CORS (계약 ⑦) — 프론트(Vite) 오리진만 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest) -> dict:
    """문자 한 건 분석 → 위험도·근거·신호·클러스터 (계약 ①)."""
    return analyze_svc.analyze(req.text, req.sender)


@app.get("/api/graph", response_model=GraphResponse)
def get_graph() -> dict:
    """조직 클러스터 그래프 (계약 ②)."""
    return graph.to_json()


@app.post("/api/report", response_model=ReportResponse)
def report(req: ReportRequest) -> ReportResponse:
    """신고 저장 + 그래프 갱신 + 신고 상태 반환 (계약 ③)."""

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


@app.get("/api/trends", response_model=TrendsResponse)
def get_trends() -> dict:
    """위협 트렌드 — 유저 신고(source='user')만 집계 (계약 ④)."""
    return trends_svc.get_trends()

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
        "variants": generate_variants(req.text),
    }
