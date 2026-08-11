"""평판 DB + 조회 (계약 ⑤).

    reputation.lookup(pre: dict) -> (score: float, evidence: list[dict])

신고 이력(SQLite)에 근거해 위험 점수·증거를 생성한다.
evidence 원소는 항상 다음 형식을 유지한다.

    {
        "type": str,
        "detail": str,
        "weight": float
    }

DB(reputation.db)는 로컬에서 생성되며 .gitignore로 추적하지 않는다.
서버 첫 기동 시 DB가 비어 있으면 seed/reports.json으로 초기화한다.

우리 데이터에는 발신번호가 없는 경우가 많기 때문에
URL·도메인·문구 토큰 공유를 중심으로 평판을 조회한다.

저장소 역할도 겸한다.
graph.py는 get_reports()로 신고 데이터를 읽어 클러스터를 만든다.

신고 상태:
- pending: 사용자 신고 1건
- suspected: 동일 사례 사용자 신고 2~4건
- confirmed: 동일 사례 사용자 신고 5건 이상 또는 시드 데이터
- false_positive: 추후 관리자 검토를 통해 정상으로 판정된 사례

주의:
현재 로그인·신고자 식별 기능이 없으므로,
동일 사용자의 반복 신고와 서로 다른 사용자의 신고를 구분하지 않는다.
"""

import hashlib
import json
import os
import sqlite3
from datetime import datetime, timezone

import config
from ai.preprocess import preprocess


_DB_PATH = config.REPUTATION_DB_PATH


# ----------------------------------------------------------------------
# 평판 점수 가중치
# ----------------------------------------------------------------------
_W_DOMAIN_HISTORY = 0.35
_W_PHRASE_SIMILAR = 0.30
_W_PER_EXTRA_REPORT = 0.05

# 토큰 자카드 유사도 기준
_SIMILARITY_THRESHOLD = 0.30


# ----------------------------------------------------------------------
# 신고 상태
# ----------------------------------------------------------------------
_STATUS_PENDING = "pending"
_STATUS_SUSPECTED = "suspected"
_STATUS_CONFIRMED = "confirmed"
_STATUS_FALSE_POSITIVE = "false_positive"

# 상태 자동 승격 기준
_SUSPECTED_REPORT_COUNT = 2
_CONFIRMED_REPORT_COUNT = 5


# 문구 유사도 계산에서 제외할 의미 없는 공통 토큰
_GENERIC_TOKENS = {
    "url",
    "http",
    "https",
    "www",
    "com",
    "net",
    "org",
}


def _connect() -> sqlite3.Connection:
    """SQLite 연결을 생성한다."""

    con = sqlite3.connect(
        _DB_PATH,
        check_same_thread=False,
    )
    con.row_factory = sqlite3.Row

    return con


def _now() -> str:
    """현재 UTC 시각을 ISO 문자열로 반환한다."""

    return datetime.now(timezone.utc).isoformat()


def _make_case_key(
    text: str,
    sender=None,
) -> str:
    """동일·반복 신고를 묶기 위한 안정적인 식별 키를 생성한다.

    발신번호, 도메인, URL, 정규화된 본문을 함께 사용한다.

    완전히 동일한 문자와 발신번호가 다시 신고되면
    같은 case_key가 생성된다.
    """

    pre = preprocess(text, sender)

    payload = {
        "sender": pre.get("sender"),
        "domains": sorted(
            pre.get("domains", []) or []
        ),
        "urls": sorted(
            pre.get("urls", []) or []
        ),
        "norm": pre.get("norm", ""),
    }

    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def _status_from_count(
    report_count: int,
    source: str = "user",
) -> str:
    """신고 횟수와 출처를 기준으로 상태를 결정한다."""

    # 시드 데이터는 이미 확보된 과거 사례이므로 확정 처리
    if source == "seed":
        return _STATUS_CONFIRMED

    if report_count >= _CONFIRMED_REPORT_COUNT:
        return _STATUS_CONFIRMED

    if report_count >= _SUSPECTED_REPORT_COUNT:
        return _STATUS_SUSPECTED

    return _STATUS_PENDING


def _backfill_existing_rows(
    con: sqlite3.Connection,
) -> None:
    """기존 DB 행의 case_key와 status를 자동 보정한다.

    관리자에 의해 정상(label=0)으로 검증된 사례는
    신고 횟수보다 관리자 검증 결과를 우선하여
    false_positive 상태를 유지한다.
    """

    rows = con.execute(
        """
        SELECT
            id,
            text,
            sender,
            source,
            case_key,
            status
        FROM reports
        """
    ).fetchall()

    if not rows:
        return

    # 1. case_key가 없는 기존 행에 case_key 생성
    for row in rows:
        case_key = row["case_key"]

        if not case_key:
            case_key = _make_case_key(
                row["text"],
                row["sender"],
            )

            con.execute(
                """
                UPDATE reports
                SET case_key = ?
                WHERE id = ?
                """,
                (
                    case_key,
                    row["id"],
                ),
            )

    con.commit()

    # 2. case_key별 상태 판단 정보 계산
    grouped_rows = con.execute(
        """
        SELECT
            case_key,
            COUNT(*) AS report_count,

            MAX(
                CASE
                    WHEN source = 'seed'
                    THEN 1
                    ELSE 0
                END
            ) AS has_seed,

            MAX(
                CASE
                    WHEN training_approved = 1
                     AND training_label = 0
                    THEN 1
                    ELSE 0
                END
            ) AS verified_normal

        FROM reports
        WHERE case_key IS NOT NULL
        GROUP BY case_key
        """
    ).fetchall()

    # 3. 상태 보정
    for row in grouped_rows:
        case_key = row["case_key"]
        report_count = int(row["report_count"])
        has_seed = bool(row["has_seed"])
        verified_normal = bool(
            row["verified_normal"]
        )

        # 관리자 정상 판정이 최우선
        if verified_normal:
            status = _STATUS_FALSE_POSITIVE

        else:
            status = _status_from_count(
                report_count=report_count,
                source=(
                    "seed"
                    if has_seed
                    else "user"
                ),
            )

        con.execute(
            """
            UPDATE reports
            SET status = ?
            WHERE case_key = ?
            """,
            (
                status,
                case_key,
            ),
        )

    con.commit()


def init_db() -> None:
    """테이블 생성, 기존 DB 마이그레이션, 시드 초기화를 수행한다."""

    os.makedirs(
        os.path.dirname(_DB_PATH) or ".",
        exist_ok=True,
    )

    con = _connect()

    try:
        # 신규 DB 생성 시 사용하는 최신 테이블 구조
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                text              TEXT    NOT NULL,
                sender            TEXT,
                urls              TEXT    NOT NULL,
                domains           TEXT    NOT NULL,
                tokens             TEXT    NOT NULL,
                source            TEXT    NOT NULL DEFAULT 'user',
                case_key          TEXT,
                status            TEXT    NOT NULL DEFAULT 'pending',
                training_approved   INTEGER NOT NULL DEFAULT 0,
                training_label      INTEGER,
                approved_at         TEXT,
                used_for_training   INTEGER NOT NULL DEFAULT 0,
                trained_model_version TEXT,
                trained_at          TEXT,
                created_at          TEXT    NOT NULL
            )
            """
        )

        con.commit()

        # 기존 reputation.db에는 신규 컬럼이 없을 수 있으므로
        # PRAGMA로 실제 컬럼을 확인한 뒤 자동 추가한다.
        existing_columns = {
            row["name"]
            for row in con.execute(
                "PRAGMA table_info(reports)"
            ).fetchall()
        }

        if "case_key" not in existing_columns:
            con.execute(
                """
                ALTER TABLE reports
                ADD COLUMN case_key TEXT
                """
            )

        if "status" not in existing_columns:
            con.execute(
                """
                ALTER TABLE reports
                ADD COLUMN status TEXT
                NOT NULL DEFAULT 'pending'
                """
            )

        if "training_approved" not in existing_columns:
            con.execute(
                """
                ALTER TABLE reports
                ADD COLUMN training_approved INTEGER
                NOT NULL DEFAULT 0
                """
            )

        if "training_label" not in existing_columns:
            con.execute(
                """
                ALTER TABLE reports
                ADD COLUMN training_label INTEGER
                """
            )

        if "approved_at" not in existing_columns:
            con.execute(
                """
                ALTER TABLE reports
                ADD COLUMN approved_at TEXT
                """
            )

        if "used_for_training" not in existing_columns:
            con.execute(
                """
                ALTER TABLE reports
                ADD COLUMN used_for_training INTEGER
                NOT NULL DEFAULT 0
                """
            )

        if "trained_model_version" not in existing_columns:
            con.execute(
                """
                ALTER TABLE reports
                ADD COLUMN trained_model_version TEXT
                """
            )

        if "trained_at" not in existing_columns:
            con.execute(
                """
                ALTER TABLE reports
                ADD COLUMN trained_at TEXT
                """
            )
        con.commit()

        # DB가 완전히 비어 있으면 시드 데이터 삽입
        count = con.execute(
            """
            SELECT COUNT(*)
            FROM reports
            """
        ).fetchone()[0]

        if count == 0:
            _seed(con)

        # 기존·시드 데이터를 포함해 case_key와 status 정리
        _backfill_existing_rows(con)

    finally:
        con.close()


def _seed(
    con: sqlite3.Connection,
) -> None:
    """seed/reports.json을 DB에 삽입한다."""

    if not os.path.exists(
        config.REPORTS_SEED_PATH
    ):
        return

    with open(
        config.REPORTS_SEED_PATH,
        encoding="utf-8",
    ) as f:
        rows = json.load(f)

    for row in rows:
        text = row.get("text", "")
        sender = row.get("sender")

        if not str(text).strip():
            continue

        _insert(
            con=con,
            text=text,
            sender=sender,
            source="seed",
        )

    con.commit()


def _insert(
    con: sqlite3.Connection,
    text: str,
    sender=None,
    source: str = "user",
) -> dict:
    """신고 1건을 저장하고 해당 사례의 최신 상태를 반환한다.

    text와 sender를 전처리해 URL·도메인·토큰을 함께 저장한다.

    source:
    - seed: 시드 데이터
    - user: 사용자 신고
    """

    pre = preprocess(text, sender)
    case_key = _make_case_key(text, sender)

    # 현재 저장 전 동일 사례 신고 수
    existing_count = con.execute(
        """
        SELECT COUNT(*)
        FROM reports
        WHERE case_key = ?
        """,
        (case_key,),
    ).fetchone()[0]

    report_count = int(existing_count) + 1

    # 동일 사례에 시드 데이터가 이미 존재하는지 확인
    has_seed = con.execute(
        """
        SELECT EXISTS(
            SELECT 1
            FROM reports
            WHERE case_key = ?
              AND source = 'seed'
        )
        """,
        (case_key,),
    ).fetchone()[0]

    effective_source = (
        "seed"
        if source == "seed" or has_seed
        else "user"
    )

    status = _status_from_count(
        report_count=report_count,
        source=effective_source,
    )

    cursor = con.execute(
        """
        INSERT INTO reports (
            text,
            sender,
            urls,
            domains,
            tokens,
            source,
            case_key,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            text,
            pre.get("sender"),
            json.dumps(
                pre.get("urls", []) or [],
                ensure_ascii=False,
            ),
            json.dumps(
                pre.get("domains", []) or [],
                ensure_ascii=False,
            ),
            json.dumps(
                pre.get("tokens", []) or [],
                ensure_ascii=False,
            ),
            source,
            case_key,
            status,
            _now(),
        ),
    )

    # 같은 사례로 묶인 기존 신고도 최신 상태로 맞춘다.
    con.execute(
        """
        UPDATE reports
        SET status = ?
        WHERE case_key = ?
        """,
        (
            status,
            case_key,
        ),
    )

    return {
        "id": cursor.lastrowid,
        "case_key": case_key,
        "status": status,
        "report_count": report_count,
    }


def add_report(
    text: str,
    sender=None,
) -> dict:
    """사용자 신고를 저장하고 저장 결과를 반환한다."""

    con = _connect()

    try:
        saved = _insert(
            con=con,
            text=text,
            sender=sender,
            source="user",
        )

        con.commit()

    finally:
        con.close()

    return {
        "id": saved["id"],
        "text": text,
        "sender": sender,
        "case_key": saved["case_key"],
        "status": saved["status"],
        "report_count": saved["report_count"],
    }


def _row_to_dict(
    row: sqlite3.Row,
) -> dict:
    """SQLite Row를 일반 dict로 변환한다."""

    return {
        "id": row["id"],
        "text": row["text"],
        "sender": row["sender"],
        "urls": json.loads(
            row["urls"]
        ),
        "domains": json.loads(
            row["domains"]
        ),
        "tokens": json.loads(
            row["tokens"]
        ),
        "source": row["source"],
        "case_key": row["case_key"],
        "status": row["status"],
        "created_at": row["created_at"],
    }


def get_reports() -> list[dict]:
    """저장된 모든 신고를 반환한다.

    seed와 user 신고를 모두 포함하며 graph.py가 사용한다.
    """

    con = _connect()

    try:
        rows = con.execute(
            """
            SELECT
                id,
                text,
                sender,
                urls,
                domains,
                tokens,
                source,
                case_key,
                status,
                created_at
            FROM reports
            """
        ).fetchall()

    finally:
        con.close()

    return [
        _row_to_dict(row)
        for row in rows
    ]


def get_reports_by_source(
    source: str,
) -> list[dict]:
    """특정 출처의 신고만 반환한다.

    source:
    - seed
    - user
    """

    con = _connect()

    try:
        rows = con.execute(
            """
            SELECT
                id,
                text,
                sender,
                urls,
                domains,
                tokens,
                source,
                case_key,
                status,
                created_at
            FROM reports
            WHERE source = ?
            """,
            (source,),
        ).fetchall()

    finally:
        con.close()

    return [
        _row_to_dict(row)
        for row in rows
    ]


def get_reports_by_status(
    status: str,
) -> list[dict]:
    """특정 검증 상태의 신고만 반환한다."""

    valid_statuses = {
        _STATUS_PENDING,
        _STATUS_SUSPECTED,
        _STATUS_CONFIRMED,
        _STATUS_FALSE_POSITIVE,
    }

    if status not in valid_statuses:
        raise ValueError(
            f"지원하지 않는 신고 상태입니다: {status}"
        )

    con = _connect()

    try:
        rows = con.execute(
            """
            SELECT
                id,
                text,
                sender,
                urls,
                domains,
                tokens,
                source,
                case_key,
                status,
                created_at
            FROM reports
            WHERE status = ?
            """,
            (status,),
        ).fetchall()

    finally:
        con.close()

    return [
        _row_to_dict(row)
        for row in rows
    ]

def get_training_candidates() -> list[dict]:
    """AI 재학습 전 검토가 필요한 confirmed 고유 사례를 반환한다.

    조건:
    - 사용자 신고(source='user')
    - confirmed 상태
    - 아직 학습 승인되지 않음
    - 동일 case_key는 1개의 후보로만 반환
    """

    con = _connect()

    try:
        rows = con.execute(
            """
            SELECT
                case_key,
                MIN(text) AS text,
                MIN(sender) AS sender,
                COUNT(*) AS report_count,
                MIN(created_at) AS first_seen,
                MAX(created_at) AS last_seen,
                MAX(training_approved) AS training_approved
            FROM reports
            WHERE source = 'user'
              AND status = ?
            GROUP BY case_key
            HAVING MAX(training_approved) = 0
            ORDER BY report_count DESC, last_seen DESC
            """,
            (_STATUS_CONFIRMED,),
        ).fetchall()

    finally:
        con.close()

    return [
        {
            "case_key": row["case_key"],
            "text": row["text"],
            "sender": row["sender"],
            "status": _STATUS_CONFIRMED,
            "report_count": int(row["report_count"]),
            "training_approved": bool(
                row["training_approved"]
            ),
            "first_seen": row["first_seen"],
            "last_seen": row["last_seen"],
        }
        for row in rows
    ]

def approve_training_candidate(
    case_key: str,
    label: int,
) -> dict:
    """confirmed 신고 사례를 AI 재학습용 데이터로 승인한다.

    label:
    - 1 = phishing
    - 0 = normal
    """

    if label not in (0, 1):
        raise ValueError(
            "training label은 0 또는 1이어야 합니다."
        )

    con = _connect()

    try:
        row = con.execute(
            """
            SELECT
                case_key,
                status,
                COUNT(*) AS report_count
            FROM reports
            WHERE case_key = ?
            GROUP BY case_key, status
            """,
            (case_key,),
        ).fetchone()

        if row is None:
            raise ValueError(
                "해당 case_key의 신고 사례를 찾을 수 없습니다."
            )

        if row["status"] != _STATUS_CONFIRMED:
            raise ValueError(
                "confirmed 상태의 사례만 학습 승인할 수 있습니다."
            )

        approved_at = _now()

        # 관리자가 정상(label=0)으로 판정한 경우
        # 반복 신고 사례라도 false_positive로 상태를 변경한다.
        new_status = (
            _STATUS_CONFIRMED
            if label == 1
            else _STATUS_FALSE_POSITIVE
        )

        con.execute(
            """
            UPDATE reports
            SET
                status = ?,
                training_approved = 1,
                training_label = ?,
                approved_at = ?
            WHERE case_key = ?
            """,
            (
                new_status,
                label,
                approved_at,
                case_key,
            ),
        )

        con.commit()

    finally:
        con.close()

    return {
        "case_key": case_key,
        "status": new_status,
        "training_approved": True,
        "training_label": label,
        "approved_at": approved_at,
        "report_count": int(row["report_count"]),
    }

def get_approved_training_samples() -> list[dict]:
    """AI 재학습에 사용할 승인 완료 고유 사례를 반환한다.

    조건:
    - training_approved = 1
    - training_label이 0 또는 1
    - 동일 case_key는 1개의 학습 샘플로만 반환
    """

    con = _connect()

    try:
        rows = con.execute(
            """
            SELECT
                case_key,
                MIN(text) AS text,
                MIN(sender) AS sender,
                MAX(training_label) AS training_label,
                COUNT(*) AS report_count,
                MIN(approved_at) AS approved_at
            FROM reports
            WHERE training_approved = 1
            AND training_label IN (0, 1)
            AND used_for_training = 0
            GROUP BY case_key
            ORDER BY approved_at ASC
            """
        ).fetchall()

    finally:
        con.close()

    return [
        {
            "case_key": row["case_key"],
            "text": row["text"],
            "sender": row["sender"],
            "label": int(row["training_label"]),
            "report_count": int(row["report_count"]),
            "approved_at": row["approved_at"],
            "source": "user_report",
        }
        for row in rows
    ]

def mark_training_samples_used(
    case_keys: list[str],
    model_version: str,
) -> dict:
    """재학습에 사용한 사례들을 사용 완료 상태로 표시한다."""

    if not case_keys:
        return {
            "updated_count": 0,
            "model_version": model_version,
        }

    trained_at = _now()

    placeholders = ",".join(
        "?"
        for _ in case_keys
    )

    con = _connect()

    try:
        cursor = con.execute(
            f"""
            UPDATE reports
            SET
                used_for_training = 1,
                trained_model_version = ?,
                trained_at = ?
            WHERE case_key IN ({placeholders})
              AND training_approved = 1
            """,
            (
                model_version,
                trained_at,
                *case_keys,
            ),
        )

        con.commit()

        updated_count = cursor.rowcount

    finally:
        con.close()

    return {
        "updated_count": updated_count,
        "model_version": model_version,
        "trained_at": trained_at,
    }

def get_case_summary(
    case_key: str,
) -> dict | None:
    """특정 신고 사례의 누적 상태를 반환한다."""

    con = _connect()

    try:
        row = con.execute(
            """
            SELECT
                case_key,
                status,
                COUNT(*) AS report_count,
                MIN(created_at) AS first_seen,
                MAX(created_at) AS last_seen
            FROM reports
            WHERE case_key = ?
            GROUP BY case_key, status
            """,
            (case_key,),
        ).fetchone()

    finally:
        con.close()

    if row is None:
        return None

    return {
        "case_key": row["case_key"],
        "status": row["status"],
        "report_count": int(
            row["report_count"]
        ),
        "first_seen": row["first_seen"],
        "last_seen": row["last_seen"],
    }


def report_count() -> int:
    """전체 신고 행 수를 반환한다."""

    con = _connect()

    try:
        return int(
            con.execute(
                """
                SELECT COUNT(*)
                FROM reports
                """
            ).fetchone()[0]
        )

    finally:
        con.close()


def _clean_similarity_tokens(
    tokens,
) -> set[str]:
    """문구 유사도 계산에서 공통 URL 토큰과 빈 토큰을 제거한다."""

    cleaned: set[str] = set()

    for token in tokens or []:
        value = str(token).strip().lower()

        if not value:
            continue

        if value in _GENERIC_TOKENS:
            continue

        cleaned.add(value)

    return cleaned


def _jaccard(
    a: set,
    b: set,
) -> float:
    """의미 없는 URL 공통 토큰을 제외한 토큰 자카드 유사도."""

    clean_a = _clean_similarity_tokens(a)
    clean_b = _clean_similarity_tokens(b)

    # 토큰이 너무 적으면 우연히 일치할 가능성이 높으므로 제외
    if len(clean_a) < 3 or len(clean_b) < 3:
        return 0.0

    union = clean_a | clean_b

    if not union:
        return 0.0

    return len(
        clean_a & clean_b
    ) / len(union)


def lookup(
    pre: dict,
) -> tuple[float, list[dict]]:
    """pre dict를 받아 평판 위험 점수와 근거를 반환한다.

    판정 기준:
    1. 신고 이력에 존재하는 도메인인지
    2. 기존 신고 문구와 토큰 유사도가 높은지
    """

    in_domains = set(
        pre.get("domains", []) or []
    )
    in_tokens = set(
        pre.get("tokens", []) or []
    )

    reports = get_reports()

    score = 0.0
    evidence: list[dict] = []

    # ------------------------------------------------------------------
    # 1. 도메인 신고 이력
    # ------------------------------------------------------------------
    domain_hits: dict[str, int] = {}

    for report in reports:
        # false_positive로 판정된 신고는 위험 평판 계산에서 제외
        if report.get("status") == _STATUS_FALSE_POSITIVE:
            continue

        for domain in report["domains"]:
            if domain in in_domains:
                domain_hits[domain] = (
                    domain_hits.get(domain, 0) + 1
                )

    for domain, count in domain_hits.items():
        weight = round(
            min(
                _W_DOMAIN_HISTORY
                + _W_PER_EXTRA_REPORT
                * (count - 1),
                0.60,
            ),
            4,
        )

        score += weight

        evidence.append(
            {
                "type": "신고 이력 도메인",
                "detail": (
                    f"{domain} "
                    f"(신고 {count}건)"
                ),
                "weight": weight,
            }
        )

    # ------------------------------------------------------------------
    # 2. 유사 신고 문구
    # ------------------------------------------------------------------
    best_similarity = 0.0

    for report in reports:
        if report.get("status") == _STATUS_FALSE_POSITIVE:
            continue

        similarity = _jaccard(
            in_tokens,
            set(report["tokens"]),
        )

        if similarity > best_similarity:
            best_similarity = similarity

    if best_similarity >= _SIMILARITY_THRESHOLD:
        weight = round(
            min(
                _W_PHRASE_SIMILAR
                * best_similarity
                / _SIMILARITY_THRESHOLD,
                _W_PHRASE_SIMILAR,
            ),
            4,
        )

        score += weight

        evidence.append(
            {
                "type": "유사 신고 문구",
                "detail": (
                    "기존 신고와 "
                    f"{round(best_similarity * 100)}% 유사"
                ),
                "weight": weight,
            }
        )

    return (
        round(
            min(score, 1.0),
            4,
        ),
        evidence,
    )


# 모듈 로드 시 DB 준비
# - 테이블 생성
# - 기존 DB 자동 마이그레이션
# - 비어 있으면 시드 삽입
# - case_key/status 자동 보정
init_db()