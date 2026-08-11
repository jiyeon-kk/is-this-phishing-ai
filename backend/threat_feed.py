"""공식기관 피싱·스미싱 위협 경보 수집기.

현재 지원:
- KISA 불법스팸대응센터
- 경찰청 보도자료
- 금융감독원 소비자경보

동작:
1. 서버 시작 시 백그라운드 갱신 스레드 시작
2. 30분 주기로 3개 공식기관 공개 페이지 확인
3. 피싱·스미싱·보이스피싱·사칭·금융사기 관련 게시물만 추출
4. 기관별 원문의 작성자·조회수·첨부파일 등 메타데이터는 카드에서 제거
5. 기관별 결과를 통합하고 날짜 최신순으로 정렬
6. backend/threat_feed_cache.json 갱신
7. 외부 사이트 수집 실패 시 기존 캐시를 유지

프론트 요청 시에는 최근 캐시를 우선 사용해
외부 기관 사이트 장애가 앱 전체 장애로 이어지지 않도록 한다.
"""

import json
import os
import re
import threading
import time
from collections import Counter
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
POLICE_LIST_URL = (
    "https://www.police.go.kr/user/bbs/"
    "BD_selectBbsList.do?q_bbsCode=1002"
)

FSS_LIST_URL = (
    "https://www.fss.or.kr/fss/bbs/"
    "B0000175/list.do?menuNo=200204"
)

CACHE_MINUTES = 30
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
    "전기통신금융사기",
    "금융사기",
    "사칭",
    "해킹",
    "악성",
    "악성앱",
    "개인정보",
    "문자 무단발송",
    "스캠",
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
    """캐시가 최근 CACHE_MINUTES 이내인지 확인한다."""

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
        < timedelta(minutes=CACHE_MINUTES)
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


def _clean_title(
    title: str,
) -> str:
    """카드 표시용 제목을 정리한다."""

    title = (title or "").replace("\xa0", " ")

    return re.sub(
        r"\s+",
        " ",
        title,
    ).strip()


def _friendly_summary(
    source: str,
    title: str,
    category: str,
) -> str:
    """기관별 원문 메타데이터를 제거한 짧고 통일된 카드 요약문."""

    clean_title = re.sub(
        r"^\s*\[.*?\]\s*",
        "",
        _clean_title(title),
    ).strip()

    if source == "KISA":
        return (
            f"KISA에서 '{clean_title}' 관련 경보를 안내하고 있습니다. "
            "의심스러운 문자·링크·전화는 즉시 반응하지 말고 "
            "공식 기관의 홈페이지나 대표번호를 통해 직접 확인하세요."
        )

    if source == "경찰청":
        return (
            f"경찰청에서 '{clean_title}' 관련 피싱·금융사기 정보를 안내하고 있습니다. "
            "출처가 불분명한 연락이나 링크에는 응답하지 말고 "
            "경찰청 또는 해당 기관의 공식 채널을 통해 사실 여부를 확인하세요."
        )

    if source == "금융감독원":
        return (
            f"금융감독원에서 '{clean_title}' 관련 소비자경보를 안내하고 있습니다. "
            "보이스피싱·금융사기가 의심되는 연락에는 응답하지 말고 "
            "금융회사나 공식 기관의 대표번호를 통해 직접 확인하세요."
        )

    return (
        f"{source}에서 '{clean_title}' 관련 안전 정보를 안내하고 있습니다. "
        "의심스러운 연락은 공식 기관의 채널을 통해 직접 확인하세요."
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

        # 화면에는 기관 사이트의 작성자·조회수·첨부파일 등
        # 원문 메타데이터가 섞이지 않도록 통일된 요약문을 사용한다.
        summary = _friendly_summary(
            "KISA",
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



# ----------------------------------------------------------------------
# 경찰청
# ----------------------------------------------------------------------

def fetch_police_alerts(
    limit: int = 10,
) -> list[dict]:
    """경찰청 보도자료 중 피싱·보이스피싱 관련 게시물을 수집한다."""

    response = requests.get(
        POLICE_LIST_URL,
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

    # 경찰청 보도자료 상세 링크
    links = soup.select(
        'a[href*="BD_selectBbs.do"]'
    )

    print(
        "[threat-feed] "
        f"경찰청 게시물 링크 {len(links)}개 발견"
    )

    seen_urls = set()

    for link in links:
        title = " ".join(
            link.get_text(
                " ",
                strip=True,
            ).split()
        )

        href = str(
            link.get(
                "href",
                "",
            )
        ).strip()

        if not title or not href:
            continue

        # 피싱 관련 보도자료만
        if not _is_security_alert(title):
            continue

        detail_url = urljoin(
            POLICE_LIST_URL,
            href,
        )

        if detail_url in seen_urls:
            continue

        seen_urls.add(detail_url)

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

        summary = ""

        # ----------------------------------------------------------
        # 상세 페이지 본문 수집
        # ----------------------------------------------------------

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

            body_selectors = [
                ".bbs_view",
                ".bbs-view",
                ".board_view",
                ".board-view",
                ".view_cont",
                ".view-content",
                ".content",
                ".bbs_detail",
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

            # 선택자로 못 찾았으면 전체 페이지에서
            # 피싱 관련 본문 후보를 한 번 더 찾는다.
            if not summary:
                page_text = " ".join(
                    detail_soup.get_text(
                        " ",
                        strip=True,
                    ).split()
                )

                if len(page_text) >= 80:
                    # 제목 위치 이후를 우선 사용
                    title_pos = page_text.find(
                        title
                    )

                    if title_pos >= 0:
                        text = page_text[
                            title_pos:
                            title_pos + 500
                        ]

                        summary = text[:220]

        except Exception as exc:
            print(
                "[threat-feed] "
                f"경찰청 상세 본문 수집 실패: {exc}"
            )

        # 상세 페이지 원문에는 메뉴·작성자·첨부파일 등의
        # 메타데이터가 섞일 수 있으므로 카드에서는 정리된 요약문만 사용한다.
        summary = _friendly_summary(
            "경찰청",
            title,
            category,
        )

        # URL 끝의 게시물 번호를 id에 활용
        id_match = re.search(
            r"q_bbscttSn=([^&]+)",
            detail_url,
        )

        post_id = (
            id_match.group(1)
            if id_match
            else str(abs(hash(detail_url)))
        )

        results.append(
            {
                "id": f"police-{post_id}",
                "source": "경찰청",
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
        f"경찰청 필터 통과 {len(results)}건"
    )

    return results


# ----------------------------------------------------------------------
# 금융감독원
# ----------------------------------------------------------------------

def fetch_fss_alerts(
    limit: int = 10,
) -> list[dict]:
    """금융감독원 소비자경보 중 피싱·금융사기 관련 게시물을 수집한다."""

    response = requests.get(
        FSS_LIST_URL,
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

    # 소비자경보 상세 링크
    links = soup.select(
        'a[href*="B0000175"][href*="view.do"], '
        'a[href*="/view.do"]'
    )

    print(
        "[threat-feed] "
        f"금융감독원 게시물 링크 {len(links)}개 발견"
    )

    seen_urls = set()

    for link in links:
        title = " ".join(
            link.get_text(
                " ",
                strip=True,
            ).split()
        )

        href = str(
            link.get(
                "href",
                "",
            )
        ).strip()

        if not title or not href:
            continue

        # 보이스피싱·금융사기 등 관련 경보만 유지
        if not _is_security_alert(title):
            continue

        detail_url = urljoin(
            FSS_LIST_URL,
            href,
        )

        if detail_url in seen_urls:
            continue

        seen_urls.add(detail_url)

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

        summary = ""

        # ----------------------------------------------------------
        # 상세 페이지 본문 수집
        # ----------------------------------------------------------

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

            body_selectors = [
                ".board-view",
                ".board_view",
                ".view_cont",
                ".view-content",
                ".bbs_view",
                ".bbs-view",
                ".content",
                ".cont",
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

            # 날짜가 목록에서 안 잡힌 경우
            # 상세 페이지에서도 날짜를 찾아본다.
            if not published_at:
                page_text = " ".join(
                    detail_soup.get_text(
                        " ",
                        strip=True,
                    ).split()
                )

                published_at = _normalize_date(
                    page_text
                )

            if not summary:
                page_text = " ".join(
                    detail_soup.get_text(
                        " ",
                        strip=True,
                    ).split()
                )

                title_pos = page_text.find(
                    title
                )

                if title_pos >= 0:
                    text = page_text[
                        title_pos:
                        title_pos + 600
                    ]

                    summary = text[:220]

        except Exception as exc:
            print(
                "[threat-feed] "
                f"금융감독원 상세 본문 수집 실패: {exc}"
            )

        # 상세 페이지 원문에는 작성자·조회수·첨부파일 등의
        # 메타데이터가 섞일 수 있으므로 카드에서는 정리된 요약문만 사용한다.
        summary = _friendly_summary(
            "금융감독원",
            title,
            category,
        )

        id_match = re.search(
            r"nttId=(\d+)",
            detail_url,
        )

        post_id = (
            id_match.group(1)
            if id_match
            else str(abs(hash(detail_url)))
        )

        results.append(
            {
                "id": f"fss-{post_id}",
                "source": "금융감독원",
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
        f"금융감독원 필터 통과 {len(results)}건"
    )

    return results


# ----------------------------------------------------------------------
# 통합 수집
# ----------------------------------------------------------------------

def refresh_feed() -> list[dict]:
    """KISA·경찰청·금융감독원에서 최신 피싱 정보를 다시 수집한다."""

    items: list[dict] = []

    # 기관 하나가 실패해도 다른 기관 수집은 계속 진행한다.
    collectors = (
        ("KISA", fetch_kisa_alerts),
        ("경찰청", fetch_police_alerts),
        ("금융감독원", fetch_fss_alerts),
    )

    for source_name, collector in collectors:
        try:
            source_items = collector(limit=10)
            items.extend(source_items)

        except Exception as exc:
            # 공모전 데모 안정성을 위해
            # 외부 기관 한 곳의 장애가 전체 API 장애로 이어지지 않게 한다.
            print(
                "[threat-feed] "
                f"{source_name} 수집 실패: {exc}"
            )

    # 동일 id / URL 중복 제거
    items = _deduplicate(items)

    # 날짜 최신순 정렬
    items.sort(
        key=lambda item: item.get("published_at", ""),
        reverse=True,
    )

    # 하나라도 정상 수집됐을 때만 캐시 갱신
    if items:
        save_feed(items)

        source_counter = Counter(
            item.get("source", "기타")
            for item in items
        )

        print(
            "[threat-feed] "
            f"공식기관 경보 {len(items)}건 갱신 "
            f"{dict(source_counter)}"
        )

        return items

    # 세 기관 모두 수집하지 못했으면 기존 캐시 유지
    cached = load_feed()

    print(
        "[threat-feed] "
        f"신규 수집 없음, 기존 캐시 {len(cached)}건 사용"
    )

    return cached


def get_feed(
    limit: int = 20,
) -> list[dict]:
    """프론트에 전달할 최신 공식기관 피싱 정보를 반환한다.

    캐시가 30분 이내면 저장된 데이터를 바로 반환한다.
    캐시가 오래됐으면 공식기관 페이지를 다시 확인한다.

    백그라운드 updater도 30분 주기로 refresh_feed()를 호출하므로,
    일반적으로 프론트 요청은 최신 캐시를 빠르게 읽게 된다.
    """

    if _cache_is_fresh():
        items = load_feed()
    else:
        items = refresh_feed()

    items.sort(
        key=lambda item: item.get("published_at", ""),
        reverse=True,
    )

    return items[:limit]


# ----------------------------------------------------------------------
# 백그라운드 자동 갱신
# ----------------------------------------------------------------------

_BACKGROUND_STARTED = False
_BACKGROUND_LOCK = threading.Lock()


def _background_refresh_loop() -> None:
    """30분마다 공식기관 정보를 자동으로 갱신한다."""

    while True:
        try:
            print(
                "[threat-feed] "
                "공식기관 최신 정보 자동 갱신 시작"
            )

            refresh_feed()

        except Exception as exc:
            # 백그라운드 갱신 실패가 서버 전체 장애로
            # 이어지지 않도록 예외를 막는다.
            print(
                "[threat-feed] "
                f"자동 갱신 실패: {exc}"
            )

        # 30분 대기
        time.sleep(
            CACHE_MINUTES * 60
        )


def start_background_updater() -> None:
    """공식기관 위협정보 백그라운드 갱신 스레드를 시작한다.

    서버 프로세스당 한 번만 실행한다.
    """

    global _BACKGROUND_STARTED

    with _BACKGROUND_LOCK:

        if _BACKGROUND_STARTED:
            return

        thread = threading.Thread(
            target=_background_refresh_loop,
            name="threat-feed-updater",
            daemon=True,
        )

        thread.start()

        _BACKGROUND_STARTED = True

        print(
            "[threat-feed] "
            f"백그라운드 자동 갱신 활성화 "
            f"({CACHE_MINUTES}분 주기)"
        )