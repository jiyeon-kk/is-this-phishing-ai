"""피싱 신고 트렌드 집계 (계약 ④ /api/trends).

trends.get_trends() -> {top_phrases, top_urls}

⚠️ 유저 신고(source='user')만 집계한다.
시드(KISA·기본 시드)는 제외한다.

- top_phrases:
  기존의 단어(token) 빈도 집계가 아니라
  사용자가 이해하기 쉬운 '피싱 유형' 단위로 집계한다.

  예:
  계좌 정지 / 본인 인증 / 배송 조회 /
  환급금 / 결제 취소 / 개인정보

- top_urls:
  신고 문자에 포함된 실제 등록도메인(eTLD+1)을
  신고 건수 기준으로 집계한다.

한 신고가 여러 피싱 유형에 해당할 경우
복수 유형에 각각 1건씩 반영할 수 있다.
"""

from collections import Counter

from backend import graph, reputation


_TOP_N = 5


# ============================================================
# 주요 피싱 유형 정의
# ============================================================

PHISHING_CATEGORIES = {
    "계좌 정지": [
        "계좌 정지",
        "계좌가 정지",
        "계좌정지",
        "거래 정지",
        "거래정지",
        "이용 정지",
        "이용정지",
        "계좌 제한",
        "계좌제한",
        "금융거래 제한",
        "출금 정지",
        "출금정지",
    ],

    "본인 인증": [
        "본인 인증",
        "본인인증",
        "본인 확인",
        "본인확인",
        "인증 절차",
        "인증절차",
        "신원 확인",
        "신원확인",
        "인증번호",
        "본인 여부",
    ],

    "배송 조회": [
        "배송 조회",
        "배송조회",
        "배송지",
        "배송 주소",
        "배송주소",
        "택배",
        "운송장",
        "주소 확인",
        "주소확인",
        "배송 확인",
        "배송확인",
    ],

    "환급금": [
        "환급금",
        "환급",
        "환불",
        "피해 환급",
        "피해환급",
        "보상금",
        "지원금",
        "지원 금액",
        "정부지원금",
        "세금 환급",
        "세금환급",
    ],

    "결제 취소": [
        "결제 취소",
        "결제취소",
        "승인 취소",
        "승인취소",
        "결제 승인",
        "결제승인",
        "결제 내역",
        "결제내역",
        "카드 승인",
        "카드승인",
        "자동 결제",
        "자동결제",
    ],

    "개인정보": [
        "개인정보",
        "개인 정보",
        "정보 유출",
        "정보유출",
        "개인정보 유출",
        "개인정보유출",
        "보안 사고",
        "보안사고",
        "해킹",
        "유출 사고",
        "유출사고",
    ],

    "기관 사칭": [
        "국민은행",
        "신한은행",
        "우리은행",
        "하나은행",
        "농협",
        "금융감독원",
        "검찰",
        "경찰청",
        "경찰",
        "국세청",
        "정부24",
        "공공기관",
        "기관 사칭",
        "직원 사칭",
    ],

    "악성 링크 유도": [
        "링크",
        "URL",
        "주소에서",
        "접속하세요",
        "접속 바랍니다",
        "클릭하세요",
        "바로가기",
        "홈페이지 접속",
    ],
}


def _top(
    counter: Counter,
    n: int = _TOP_N,
) -> list[dict]:
    """빈도 상위 n개를 프론트 계약 형태로 반환."""

    return [
        {
            "label": label,
            "count": count,
        }
        for label, count in counter.most_common(n)
    ]


def _normalize_text(text: str) -> str:
    """유형 매칭을 위한 간단한 문자 정규화."""

    if not text:
        return ""

    return " ".join(
        text.lower().split()
    )


def _classify_phishing_categories(
    text: str,
) -> set[str]:
    """신고 문자에서 해당되는 피싱 유형을 찾는다.

    한 신고가 여러 유형에 동시에 해당할 수 있다.

    예:
    '계좌가 정지되었습니다. 본인 인증하세요.'
        → {'계좌 정지', '본인 인증'}
    """

    normalized = _normalize_text(text)

    matched: set[str] = set()

    for category, keywords in PHISHING_CATEGORIES.items():
        for keyword in keywords:
            if keyword.lower() in normalized:
                matched.add(category)
                break

    return matched


def get_trends() -> dict:
    """유저 신고만 집계한 트렌드.

    반환 계약은 기존과 동일:
    {
        "top_phrases": [...],
        "top_urls": [...]
    }

    단, top_phrases는 이제 raw token이 아니라
    사람이 이해하기 쉬운 '피싱 유형'을 의미한다.
    """

    reports = reputation.get_reports_by_source(
        "user"
    )

    url_counter: Counter = Counter()
    category_counter: Counter = Counter()

    for report in reports:

        # --------------------------------------------------------
        # 1. 실제 신고 URL 집계
        # --------------------------------------------------------

        # 한 신고 안에서 동일 등록도메인이 여러 번 나와도
        # 신고 건수 기준으로 1회만 반영한다.
        domains = {
            graph._reg_domain(domain)
            for domain in report.get("domains", [])
            if domain
        }

        for domain in domains:
            if domain:
                url_counter[domain] += 1

        # --------------------------------------------------------
        # 2. 주요 피싱 유형 집계
        # --------------------------------------------------------

        text = report.get("text", "")

        categories = _classify_phishing_categories(
            text
        )

        # 한 신고에서는 같은 유형을 최대 1회만 카운트
        for category in categories:
            category_counter[category] += 1

    return {
        "top_phrases": _top(category_counter),
        "top_urls": _top(url_counter),
    }