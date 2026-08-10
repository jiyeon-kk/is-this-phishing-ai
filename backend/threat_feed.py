"""공식기관 피싱·스미싱 위협 경보 수집기.

현재 지원:
- KISA 불법스팸대응센터 공지사항

동작:
1. 캐시가 최근 6시간 이내면 캐시 사용
2. 캐시가 오래됐으면 KISA 공개 게시판 확인
3. 피싱·스미싱·사칭 등 보안 관련 공지만 추출
4. backend/threat_feed_cache.json 갱신
5. 수집 실패 시 기존 캐시를 그대로 사용

사용자가 페이지를 열 때마다 외부 사이트를 요청하지 않도록
캐시 기반으로 동작한다.
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# ----------------------------------------------------------------------
# 설정
# ----------------------------------------------------------------------

_CACHE_PATH = "backend/threat_feed_cache.json"

KISA_LIST_URL = (
    "https://spam.kisa.or.kr/spam/na/ntt/"
    "selectNttList.do?bbsId=1001&mi=1019"
)

CACHE_HOURS = 6
REQUEST_TIMEOUT = 10

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/120 Safari/537.36"
    )
}


# 피싱 관련 공지만 남길 때 사용하는 단어
SECURITY_KEYWORDS = (
    "피싱",
    "스미싱",
    "보이스피싱",
    "사칭",
    "해킹",
    "악성",
    "개인정보",
    "문자 무단발송",
)


# ----------------------------------------------------------------------
# 캐시
# ----------------------------------------------------------------------

def load_feed() -> list[dict]:
    """캐시에서 경보 목록을 읽는다."""

    if not os.path.exists(_CACHE_PATH):
        return []

    try:
        with open(
            _CACHE_PATH,
            encoding="utf-8",
        ) as f:
            data = json.load(f)

        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            return data.get("items", [])

    except (
        OSError,
        json.JSONDecodeError,
    ):
        pass

    return []


def save_feed(
    items: list[dict],
) -> None:
    """수집한 경보 목록을 캐시에 저장한다."""

    os.makedirs(
        os.path.dirname(_CACHE_PATH) or ".",
        exist_ok=True,
    )

    with open(
        _CACHE_PATH,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            items,
            f,
            ensure_ascii=False,
            indent=2,
        )


def _cache_is_fresh() -> bool:
    """캐시가 최근 CACHE_HOURS 이내인지 확인한다."""

    if not os.path.exists(_CACHE_PATH):
        return False

    try:
        modified = datetime.fromtimestamp(
            os.path.getmtime(_CACHE_PATH),
            tz=timezone.utc,
        )

    except OSError:
        return False

    return (
        datetime.now(timezone.utc) - modified
        < timedelta(hours=CACHE_HOURS)
    )


# ----------------------------------------------------------------------
# 공통 유틸
# ----------------------------------------------------------------------

def _normalize_date(
    value: str,
) -> str:
    """2026.08.06 형태를 2026-08-06으로 변환."""

    value = value.strip()

    match = re.search(
        r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})",
        value,
    )

    if not match:
        return ""

    year, month, day = match.groups()

    return (
        f"{int(year):04d}-"
        f"{int(month):02d}-"
        f"{int(day):02d}"
    )


def _is_security_alert(
    title: str,
) -> bool:
    """피싱·스미싱 관련 공지인지 확인."""

    return any(
        keyword in title
        for keyword in SECURITY_KEYWORDS
    )


def _category_from_title(
    title: str,
) -> str:
    """게시물 제목으로 화면 표시용 유형을 결정."""

    if (
        "보이스피싱" in title
        and "스미싱" in title
    ):
        return "피싱·스미싱"

    if "스미싱" in title:
        return "스미싱"

    if "보이스피싱" in title:
        return "보이스피싱"

    if "피싱" in title:
        return "피싱"

    if "사칭" in title:
        return "사칭 주의"

    if "해킹" in title:
        return "보안 주의"

    return "위협 경보"


def _keywords_from_title(
    title: str,
) -> list[str]:
    """제목에서 화면 태그용 핵심 키워드를 생성한다."""

    candidate_keywords = [
        "택배",
        "배송",
        "카드",
        "은행",
        "금융",
        "정부",
        "공공기관",
        "KISA",
        "SKT",
        "유심",
        "환불",
        "피해보상",
        "스미싱",
        "피싱",
        "보이스피싱",
        "사칭",
        "해킹",
        "악성앱",
        "개인정보",
    ]

    result = []

    for keyword in candidate_keywords:
        if (
            keyword.lower() in title.lower()
            and keyword not in result
        ):
            result.append(keyword)

    # 너무 비면 유형이라도 표시
    if not result:
        result.append("피싱주의")

    return result[:5]


def _make_summary(
    title: str,
    category: str,
) -> str:
    """상세 본문 수집 실패 시 사용할 화면용 요약."""

    clean_title = re.sub(
        r"^\s*\[.*?\]\s*",
        "",
        title,
    ).strip()

    return (
        f"KISA에서 '{clean_title}' 관련 경보를 안내하고 있습니다. "
        "의심스러운 문자·링크·전화는 즉시 반응하지 말고 "
        "공식 기관의 홈페이지나 대표번호를 통해 직접 확인하세요."
    )


# ----------------------------------------------------------------------
# KISA
# ----------------------------------------------------------------------

def fetch_kisa_alerts(
    limit: int = 10,
) -> list[dict]:
    """KISA 불법스팸대응센터 최신 피싱·스미싱 관련 공지를 수집한다."""

    response = requests.get(
        KISA_LIST_URL,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or response.encoding
    )

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    results: list[dict] = []

    # 실제 KISA 구조:
    # <a href="javascript:" data-id="2921" class="nttInfoBtn">제목</a>
    post_links = soup.select(
        "a.nttInfoBtn[data-id]"
    )

    print(
        "[threat-feed] "
        f"KISA 게시물 링크 {len(post_links)}개 발견"
    )

    for link in post_links:
        ntt_sn = str(
            link.get("data-id", "")
        ).strip()

        title = " ".join(
            link.get_text(
                " ",
                strip=True,
            ).split()
        )

        if not ntt_sn:
            continue

        if not title:
            continue

        # 피싱/스미싱/사칭 등 보안 관련 공지만 유지
        if not _is_security_alert(title):
            continue

        # 게시글이 포함된 tr에서 날짜 추출
        row = link.find_parent("tr")

        published_at = ""

        if row:
            row_text = " ".join(
                row.get_text(
                    " ",
                    strip=True,
                ).split()
            )

            published_at = _normalize_date(
                row_text
            )

        category = _category_from_title(
            title
        )

        # KISA 상세 페이지는 GET query 방식으로도 접근 가능
        detail_url = (
            "https://spam.kisa.or.kr"
            "/spam/na/ntt/selectNttInfo.do"
            f"?bbsId=1001"
            f"&mi=1019"
            f"&nttSn={ntt_sn}"
        )

        # ----------------------------------------------------------
        # 상세 페이지에서 본문 요약 시도
        # ----------------------------------------------------------
        summary = ""

        try:
            detail_response = requests.get(
                detail_url,
                headers=HEADERS,
                timeout=REQUEST_TIMEOUT,
            )

            detail_response.raise_for_status()

            detail_response.encoding = (
                detail_response.apparent_encoding
                or detail_response.encoding
            )

            detail_soup = BeautifulSoup(
                detail_response.text,
                "html.parser",
            )

            # KISA 상세 페이지 본문 후보
            body_selectors = [
                ".bbs_view",
                ".bbs_view_cont",
                ".view_cont",
                ".board_view",
                ".board-view",
                ".ntt_view",
                ".content",
                "article",
            ]

            for selector in body_selectors:
                node = detail_soup.select_one(
                    selector
                )

                if not node:
                    continue

                body_text = " ".join(
                    node.get_text(
                        " ",
                        strip=True,
                    ).split()
                )

                if len(body_text) >= 40:
                    summary = body_text[:220]

                    if len(body_text) > 220:
                        summary += "..."

                    break

        except Exception as exc:
            print(
                "[threat-feed] "
                f"KISA 상세 본문 수집 실패 "
                f"(nttSn={ntt_sn}): {exc}"
            )

        # 본문을 못 읽어도 카드 자체는 노출
        if not summary:
            summary = _make_summary(
                title,
                category,
            )

        results.append(
            {
                "id": f"kisa-{ntt_sn}",
                "source": "KISA",
                "title": title,
                "published_at": published_at,
                "category": category,
                "summary": summary,
                "keywords": _keywords_from_title(
                    title
                ),
                "url": detail_url,
            }
        )

        if len(results) >= limit:
            break

    print(
        "[threat-feed] "
        f"KISA 필터 통과 {len(results)}건"
    )

    return results


# ----------------------------------------------------------------------
# 통합
# ----------------------------------------------------------------------

def _deduplicate(
    items: list[dict],
) -> list[dict]:
    """동일 URL 또는 동일 id를 제거한다."""

    result = []
    seen_ids = set()
    seen_urls = set()

    for item in items:
        item_id = item.get("id")
        url = item.get("url")

        if item_id in seen_ids:
            continue

        if url and url in seen_urls:
            continue

        seen_ids.add(item_id)

        if url:
            seen_urls.add(url)

        result.append(item)

    return result


def refresh_feed() -> list[dict]:
    """공식기관 사이트에서 최신 경보를 다시 수집한다."""

    items: list[dict] = []

    try:
        kisa_items = fetch_kisa_alerts(
            limit=10
        )

        items.extend(kisa_items)

    except Exception as exc:
        # 공모전 데모 안정성을 위해
        # 외부 사이트 장애가 앱 전체 장애로 이어지지 않게 한다.
        print(
            "[threat-feed] "
            f"KISA 수집 실패: {exc}"
        )

    items = _deduplicate(items)

    # 날짜 최신순
    items.sort(
        key=lambda item: (
            item.get(
                "published_at",
                "",
            )
        ),
        reverse=True,
    )

    # 하나라도 정상 수집됐을 때만
    # 기존 캐시를 덮어쓴다.
    if items:
        save_feed(items)

        print(
            "[threat-feed] "
            f"공식기관 경보 {len(items)}건 갱신"
        )

        return items

    # 수집 실패 시 기존 캐시 유지
    cached = load_feed()

    print(
        "[threat-feed] "
        f"신규 수집 없음, 기존 캐시 {len(cached)}건 사용"
    )

    return cached


def get_feed(
    limit: int = 20,
) -> list[dict]:
    """프론트에 전달할 최신 위협 경보를 반환한다.

    캐시가 6시간 이내면 외부 사이트에 접속하지 않는다.
    오래됐을 때만 공식기관 페이지를 다시 확인한다.
    """

    if _cache_is_fresh():
        items = load_feed()

    else:
        items = refresh_feed()

    items.sort(
        key=lambda item: (
            item.get(
                "published_at",
                "",
            )
        ),
        reverse=True,
    )

    return items[:limit]