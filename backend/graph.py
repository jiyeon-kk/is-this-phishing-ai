"""조직 클러스터 그래프 (계약 ②, ⑤).

    graph.match_cluster(pre: dict) -> dict | None
    graph.to_json()               -> {nodes, edges, cluster_count}  (계약 ②)

신고 이력(reputation.get_reports())에서 세 종류 노드를 만든다:
  - url    : 도메인            id "url:<domain>"
  - number : 발신번호(sender)  id "num:<sender>"    (sender 있을 때만)
  - phrase : 의미 있는 문구 토큰 id "phrase:<token>"

같은 신고 안에서 공유되는 요소(도메인/번호/문구)로 신고들을 연결(union-find)해
연결요소 = 조직 클러스터. 각 노드에 정수 cluster 부여.

초기 시드엔 sender 가 전부 null 이라 url·phrase 노드만 생김.
유저가 신고하면 sender 가 저장되므로 그때부터 number 노드도 생성됨.

⚠️ 범용어(확인/조회/안내 등)를 문구 노드로 쓰면 조직이 하나로 뭉개짐 →
STOPWORDS + 최소 길이로 걸러 조직별 분리를 유지 (아래 값은 튜닝 가능).
"""

import config
from backend import reputation
from datetime import datetime, timedelta, timezone


# --- 등록도메인(eTLD+1) 접기 --------------------------------------------
# 풀호스트(a1.yhanwh.site)를 조직 단위(yhanwh.site)로 접어 같은 조직의
# 서브도메인이 한 노드/한 클러스터로 묶이게 한다. graph 내부에서만 접고,
# ai/preprocess 의 pre["domains"] 원본은 절대 건드리지 않는다.
try:
    import tldextract
    # suffix_list_urls=() → 네트워크 미접속(번들 스냅샷만 사용), 런타임 안정.
    _TLD = tldextract.TLDExtract(suffix_list_urls=())
except Exception:  # tldextract 미설치 시 간이 폴백
    _TLD = None


def _reg_domain(domain: str) -> str:
    """풀호스트/도메인 → 등록가능도메인(eTLD+1).

    예: "a1.yhanwh.site" → "yhanwh.site", "gic.o4gs.yachts" → "o4gs.yachts".
    tldextract 우선, 없으면 '마지막 두 레이블' 간이 폴백.
    """
    d = (domain or "").strip().lower()
    if not d:
        return d
    if _TLD is not None:
        ext = _TLD(d)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}"
    parts = d.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else d


# phrase 노드/트렌드 문구에서 제외할 범용어. 조직 식별력이 없는 조각·불완전어.
# graph 와 trends 가 이 한 곳을 공유한다(trends.py 가 _meaningful 을 재사용).
# 토큰화가 조사까지 붙여 "계좌가" 같은 조각이 생기므로 흔한 조각도 함께 제외.
STOPWORDS = {
    # 마스킹/발신 표기
    "URL", "발신", "수신", "국외발신", "국내발신", "Web발신", "웹발신", "발송",
    # 범용 동사·요청·안내어
    "확인", "조회", "안내", "본인확인", "확인요망", "필요", "요망", "요청",
    "접속", "클릭", "링크", "로그인", "이동", "다운로드", "설치",
    # 종결/어미 조각
    "안내드립니다", "드립니다", "바랍니다", "있습니다", "되었습니다",
    "정지되었습니다", "하세요", "하시기", "합니다", "됩니다", "습니다",
    "주세요", "십시오", "예정입니다",
    # 완결형 종결어(토큰이 통째로 굳은 형태 — 어간 추출은 범위 밖이라 흔한 것만 개별 등록)
    "진행하세요", "필요합니다", "신청하세요", "확인하세요", "클릭하세요",
    # 흔한 조사 붙은 조각 (토큰화 부산물)
    "계좌가", "고객님이", "귀하의", "고객님", "고객", "님",
    # 일반 명사(식별력 낮음)
    "은행", "카드", "센터", "서비스", "이용", "관련", "대상", "처리", "정보",
}
_MIN_TOKEN_LEN = 2  # 길이는 유지(환급 등 2자 유효어 보존). 필터는 STOPWORDS 확대로.

# 문구만으로 클러스터를 인정할 최소 공유 토큰 수 (도메인·번호 매칭이 없을 때만).
# 클러스터 토큰 집합이 커서 자카드는 희석됨 → 공유 "개수"로 판정.
_MIN_SHARED_PHRASES = 2


# --- union-find --------------------------------------------------------
class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)  # 작은 루트로 — 순서 안정화


def _meaningful(tokens: list[str]) -> set[str]:
    return {
        t for t in tokens
        if len(t) >= _MIN_TOKEN_LEN and t not in STOPWORDS
    }


# 토큰 끝에 붙은 흔한 조사를 떼어 어간으로 비교(그래프 내부 전용 — ai/preprocess 무변경).
# "절차를"→"절차", "계좌가"→"계좌". 토큰화가 조사를 붙여 "절차를"≠"절차가"로 갈라져
# 교집합이 쉽게 깨지던 문제를 완화한다. 여러 글자 조사를 먼저 검사(긴 것 우선).
_JOSA = (
    "으로", "에서", "에게", "한테", "부터", "까지", "보다",  # 2글자 조사(길이 우선)
    "을", "를", "이", "가", "은", "는", "의", "에", "로", "와", "과", "도", "만",
)


def _strip_josa(token: str) -> str:
    """토큰 끝 조사를 1개 제거. 어간이 2글자 미만이 되면 과잉 제거로 보고 원형 유지."""
    for j in _JOSA:
        if token.endswith(j) and len(token) - len(j) >= _MIN_TOKEN_LEN:
            return token[: -len(j)]
    return token


def _norm_tokens(tokens: list[str]) -> set[str]:
    """조사 제거 + STOPWORDS/길이 필터를 적용한 정규화 의미 토큰 집합(그래프 내부용).

    문구 비교·문구 노드·문구 union이 모두 이 정규화 토큰을 쓴다. STOPWORDS 필터는
    조사 제거 후 어간 기준으로 유지 → "계좌가"(조각)는 "계좌"로 정규화돼 살아남고,
    "정지되었습니다" 같은 종결어 STOPWORD는 그대로 걸러진다.
    """
    out: set[str] = set()
    for t in tokens:
        s = _strip_josa(t)
        if len(s) >= _MIN_TOKEN_LEN and s not in STOPWORDS:
            out.add(s)
    return out


# 그래프는 서버 시작 후 1회 계산해 캐시 재사용. 신고로 데이터가 바뀌면
# invalidate() 로 캐시를 비워 다음 접근 때 다시 계산 (그래프만 갱신).
_CACHE: dict | None = None


def invalidate() -> None:
    """신고 등으로 신고 데이터가 바뀌었을 때 그래프 캐시를 비운다."""
    global _CACHE
    _CACHE = None


def _build() -> dict:
    """그래프 구조(캐시). 없으면 계산해 캐시에 저장."""
    global _CACHE
    if _CACHE is None:
        _CACHE = _compute()
    return _CACHE


def _compute() -> dict:
    """현재 신고들로 그래프 구조를 계산해 rich dict 반환.

    반환: {
      reports, report_cluster: list[int],
      nodes: list[node], edges: list[edge], cluster_count,
      clusters: {cid: {reports,domains,senders,tokens,size}},
    }
    """
    reports = reputation.get_reports()
    n = len(reports)

    # 노드는 서브도메인(풀호스트) 단위, 클러스터링(union)은 등록도메인(eTLD+1) 단위로
    # 분리한다. 같은 조직(등록도메인)의 서브도메인들이 한 클러스터로 뭉치되, 노드는
    # 서브도메인마다 하나씩 생겨 조직 덩어리가 서브도메인 노드로 풍성해진다.
    # _reg_domain 묶기(클러스터 판정)는 그대로 유지 — 노드 해상도만 서브도메인으로 올림.
    hosts = [set(r["domains"]) for r in reports]                      # 노드용: 풀호스트
    regs = [{_reg_domain(d) for d in r["domains"]} for r in reports]  # 클러스터용: 등록도메인
    sends = [r["sender"] for r in reports]
    phrs = [_norm_tokens(r["tokens"]) for r in reports]  # 조사 제거된 정규화 의미 토큰

    # 요소 → 그 요소를 가진 신고 인덱스 목록
    host_idx: dict[str, list[int]] = {}   # 노드 생성용(서브도메인)
    reg_idx: dict[str, list[int]] = {}    # union(클러스터) 용(등록도메인)
    send_idx: dict[str, list[int]] = {}
    tok_idx: dict[str, list[int]] = {}
    for i in range(n):
        for h in hosts[i]:
            host_idx.setdefault(h, []).append(i)
        for rd in regs[i]:
            reg_idx.setdefault(rd, []).append(i)
        if sends[i]:
            send_idx.setdefault(sends[i], []).append(i)
        for t in phrs[i]:
            tok_idx.setdefault(t, []).append(i)

    # 공유 요소로 신고 union.
    # 등록도메인·번호는 1개만 공유해도 union(같은 조직 확실). 문구는 흔한 단어 1개로
    # 우연히 이어지는 것을 막기 위해 (조사 제거된) 의미 토큰을 2개 이상 공유할 때만 union.
    uf = _UF(n)
    for group in (reg_idx, send_idx):
        for _, idxs in group.items():
            for j in range(1, len(idxs)):
                uf.union(idxs[0], idxs[j])

    # 문구 union(조건부): 두 신고의 정규화 의미 토큰 교집합이 _MIN_SHARED_PHRASES 이상일 때만.
    # 후보를 "토큰이 그 임계치 이상인 신고"로 좁혀 비용을 줄인다(대부분의 KISA URL은
    # 문구가 0개라 후보에서 빠짐). n이 작아 후보쌍 O(m^2) 비교 허용.
    phrase_reports = [i for i in range(n) if len(phrs[i]) >= _MIN_SHARED_PHRASES]
    for a in range(len(phrase_reports)):
        i = phrase_reports[a]
        for b in range(a + 1, len(phrase_reports)):
            k = phrase_reports[b]
            if len(phrs[i] & phrs[k]) >= _MIN_SHARED_PHRASES:
                uf.union(i, k)

    # 연결요소 → 클러스터 정수 id (루트 순서대로 0..k-1)
    roots = sorted({uf.find(i) for i in range(n)})
    root_to_cid = {root: cid for cid, root in enumerate(roots)}
    report_cluster = [root_to_cid[uf.find(i)] for i in range(n)]

    # phrase 노드는 2건 이상 공유된 의미 토큰만 (싱글턴 클러터 방지)
    shared_tokens = {t for t, idxs in tok_idx.items() if len(idxs) >= 2}

    # --- 노드 --------------------------------------------------------
    nodes: list[dict] = []
    node_ids: set[str] = set()

    def _add_node(nid: str, label: str, ntype: str, cid: int) -> None:
        if nid in node_ids:
            return
        node_ids.add(nid)
        nodes.append({"id": nid, "label": label, "type": ntype, "cluster": cid})

    # url 노드는 서브도메인(풀호스트) 단위 — 한 조직(등록도메인)당 여러 노드가 생긴다.
    for h, idxs in host_idx.items():
        _add_node(f"url:{h}", h, "url", report_cluster[idxs[0]])
    for s, idxs in send_idx.items():
        _add_node(f"num:{s}", s, "number", report_cluster[idxs[0]])
    # 문구 노드는 클러스터별로 분리 생성(id = phrase:<cid>:<token>).
    # 같은 문구라도 조직이 다르면 별개 노드 → 문구가 조직 간 다리가 되지 않음.
    for t in shared_tokens:
        for i in tok_idx[t]:
            cid = report_cluster[i]
            _add_node(f"phrase:{cid}:{t}", t, "phrase", cid)

    # --- 엣지 (신고별 star: 앵커→나머지 포함 노드) --------------------
    # 문구 노드는 그 신고가 속한 클러스터의 문구 노드(phrase:<cid>:<t>)에만 매달림.
    # → 문구는 자기 조직의 URL/번호 앵커에만 연결되고 조직끼리 잇지 않는다.
    edge_set: set[tuple[str, str]] = set()
    # (1) 신고별 star: 한 신고 안의 url/번호/문구 노드를 앵커로 연결.
    #     사람이 쓴 문자(문구 노드 보유)의 덩어리는 이 경로로 유지된다.
    for i in range(n):
        cid = report_cluster[i]
        ents: list[str] = []
        ents += [f"url:{h}" for h in hosts[i]]
        if sends[i]:
            ents.append(f"num:{sends[i]}")
        ents += [f"phrase:{cid}:{t}" for t in phrs[i] if t in shared_tokens]
        ents = [e for e in ents if e in node_ids]
        if len(ents) < 2:
            continue
        anchor = ents[0]  # url 우선(위에서 url 먼저 넣음)
        for other in ents[1:]:
            key = tuple(sorted((anchor, other)))
            edge_set.add(key)
    # (2) 등록도메인별 star: 같은 조직(등록도메인)의 서브도메인 노드들을 한 앵커
    #     서브도메인에 매달아 조직 덩어리를 형성한다. mesh(O(k^2)) 대신 star(k-1)로
    #     엣지 수를 억제해 렌더 성능을 지킨다.
    reg_hosts: dict[str, list[str]] = {}
    for h in host_idx:
        reg_hosts.setdefault(_reg_domain(h), []).append(h)
    for _, hs in reg_hosts.items():
        if len(hs) < 2:
            continue
        hs_sorted = sorted(hs)
        anchor = f"url:{hs_sorted[0]}"
        for h in hs_sorted[1:]:
            edge_set.add(tuple(sorted((anchor, f"url:{h}"))))
    edges = [{"source": a, "target": b} for a, b in sorted(edge_set)]

    # --- 클러스터 집계 ----------------------------------------------
    clusters: dict[int, dict] = {}
    for cid in range(len(roots)):
        clusters[cid] = {
            "reports": [], "domains": set(), "senders": set(),
            "tokens": set(), "size": 0,
        }
    for i in range(n):
        cid = report_cluster[i]
        c = clusters[cid]
        c["reports"].append(reports[i]["id"])
        c["domains"] |= regs[i]  # 매칭·위험도는 등록도메인 기준 유지(match_cluster 계약)
        if sends[i]:
            c["senders"].add(sends[i])
        c["tokens"] |= phrs[i]
    for node in nodes:
        clusters[node["cluster"]]["size"] += 1

    return {
        "reports": reports,
        "report_cluster": report_cluster,
        "nodes": nodes,
        "edges": edges,
        "cluster_count": len(roots),
        "clusters": clusters,
    }


def _risk(report_count: int, domain_count: int) -> float:
    """클러스터 위험도 0~1. 신고 수·도메인 수가 많을수록 높음."""
    return round(min(0.95, 0.40 + 0.06 * report_count + 0.03 * domain_count), 4)


def to_json() -> dict:
    """계약 ② 형식으로 그래프 반환 (프론트 react-force-graph 용).

    {nodes:[{id,label,type,cluster}], edges:[{source,target}], cluster_count}
    """
    g = _build()
    return {
        "nodes": g["nodes"],
        "edges": g["edges"],
        "cluster_count": g["cluster_count"],
    }


def match_cluster(pre: dict) -> dict | None:
    """pre dict -> 매칭 클러스터 요약 dict | None (계약 ⑤).

    매칭 우선순위: 도메인 > 번호 > 문구 유사도. 아무것도 안 걸리면 None.
    반환: {id, size, report_count, risk}
    """
    g = _build()
    clusters = g["clusters"]
    if not clusters:
        return None

    # 입력 도메인도 같은 등록도메인 기준으로 접어서 클러스터 도메인과 비교
    in_doms = {_reg_domain(d) for d in (pre.get("domains") or [])}
    in_send = pre.get("sender")
    in_toks = _norm_tokens(pre.get("tokens", []) or [])  # 클러스터 토큰과 같은 정규화 기준

    chosen: int | None = None

    # 1) 도메인 매칭 (가장 강함)
    best_overlap = 0
    for cid, c in clusters.items():
        ov = len(in_doms & c["domains"])
        if ov > best_overlap:
            best_overlap, chosen = ov, cid

    # 2) 번호 매칭
    if chosen is None and in_send:
        for cid, c in clusters.items():
            if in_send in c["senders"]:
                chosen = cid
                break

    # 3) 문구 매칭 (공유 토큰 개수 — 짧은 입력이라 자카드 대신 개수 기준)
    if chosen is None and in_toks:
        best_shared = 0
        for cid, c in clusters.items():
            shared = len(in_toks & c["tokens"])
            if shared > best_shared:
                best_shared, chosen = shared, cid
        if best_shared < _MIN_SHARED_PHRASES:
            chosen = None

    if chosen is None:
        return None

    c = clusters[chosen]
    return {
        "id": f"조직-{chosen}",
        "size": c["size"],
        "report_count": len(c["reports"]),
        "risk": _risk(len(c["reports"]), len(c["domains"])),
    }

def match_campaign(pre: dict) -> dict | None:
    """입력 문자와 연결된 피싱 캠페인의 상세 정보를 반환한다.

    반환 예:
    {
        "matched": True,
        "campaign_id": "조직-0",
        "match_type": "domain" | "sender" | "phrase",
        "similar_case_count": 10,
        "shared_domain_count": 3,
        "shared_sender_count": 1,
        "similar_phrase_count": 5,
        "first_seen": "...",
        "last_seen": "...",
        "reports_last_24h": 2,
        "status": "active"
    }
    """

    g = _build()
    clusters = g["clusters"]

    if not clusters:
        return None

    in_domains = {
        _reg_domain(domain)
        for domain in (pre.get("domains") or [])
    }
    in_sender = pre.get("sender")
    in_tokens = _norm_tokens(pre.get("tokens", []) or [])

    chosen: int | None = None
    match_type: str | None = None

    # 1. 도메인 매칭
    best_domain_overlap = 0

    for cid, cluster in clusters.items():
        overlap = len(
            in_domains & cluster["domains"]
        )

        if overlap > best_domain_overlap:
            best_domain_overlap = overlap
            chosen = cid
            match_type = "domain"

    # 2. 발신번호 매칭
    if chosen is None and in_sender:
        for cid, cluster in clusters.items():
            if in_sender in cluster["senders"]:
                chosen = cid
                match_type = "sender"
                break

    # 3. 문구 매칭
    best_phrase_overlap = 0

    if chosen is None and in_tokens:
        for cid, cluster in clusters.items():
            overlap = len(
                in_tokens & cluster["tokens"]
            )

            if overlap > best_phrase_overlap:
                best_phrase_overlap = overlap
                chosen = cid
                match_type = "phrase"

        if best_phrase_overlap < _MIN_SHARED_PHRASES:
            chosen = None
            match_type = None

    if chosen is None:
        return None

    cluster = clusters[chosen]

    # 현재 클러스터에 속한 신고 행 추출
    cluster_reports = [
        report
        for report, cid in zip(
            g["reports"],
            g["report_cluster"],
        )
        if cid == chosen
    ]

    shared_domain_count = 0
    shared_sender_count = 0
    similar_phrase_count = 0

    created_times: list[datetime] = []

    for report in cluster_reports:
        report_domains = {
            _reg_domain(domain)
            for domain in report.get("domains", [])
        }

        report_tokens = _norm_tokens(
            report.get("tokens", []) or []
        )

        if in_domains and in_domains & report_domains:
            shared_domain_count += 1

        if (
            in_sender
            and report.get("sender") == in_sender
        ):
            shared_sender_count += 1

        if (
            in_tokens
            and len(in_tokens & report_tokens)
            >= _MIN_SHARED_PHRASES
        ):
            similar_phrase_count += 1

        created_at = report.get("created_at")

        if created_at:
            try:
                created_times.append(
                    datetime.fromisoformat(created_at)
                )
            except ValueError:
                pass

    first_seen = (
        min(created_times).isoformat()
        if created_times
        else None
    )

    last_seen = (
        max(created_times).isoformat()
        if created_times
        else None
    )

    now = datetime.now(timezone.utc)
    cutoff_24h = now - timedelta(hours=24)

    reports_last_24h = sum(
        created_at >= cutoff_24h
        for created_at in created_times
    )

    # 현재는 간단한 상태 기준 사용
    if reports_last_24h >= 5:
        campaign_status = "rapidly_spreading"
    elif reports_last_24h >= 1:
        campaign_status = "active"
    else:
        campaign_status = "historical"
    # 문구만으로 연결된 캠페인은 실제 유사 신고가
    # 최소 2건 이상 있을 때만 유효한 캠페인으로 인정한다.
    if (
        match_type == "phrase"
        and similar_phrase_count < 2
    ):
        return None
    return {
        "matched": True,
        "campaign_id": f"조직-{chosen}",
        "match_type": match_type,
        "similar_case_count": len(cluster_reports),
        "shared_domain_count": shared_domain_count,
        "shared_sender_count": shared_sender_count,
        "similar_phrase_count": similar_phrase_count,
        "first_seen": first_seen,
        "last_seen": last_seen,
        "reports_last_24h": reports_last_24h,
        "status": campaign_status,
    }