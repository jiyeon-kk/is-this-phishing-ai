
from __future__ import annotations

import hashlib
import json
import random
from pathlib import Path

import pandas as pd

from src.text_features import preprocess_for_model


SEED = 20260811
rng = random.Random(SEED)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RAW_DIR = PROJECT_ROOT / "data" / "raw"

SPEC_PATH = RAW_DIR / "hard_v2_frozen_spec.json"

HARD_V1_PATH = (
    RAW_DIR
    / "korean_phishing_hard_test_1000.csv"
)

OUTPUT_PATH = (
    RAW_DIR
    / "korean_phishing_hard_v2_ood_1000.csv"
)

META_PATH = (
    RAW_DIR
    / "korean_phishing_hard_v2_ood_1000_meta.json"
)


# ============================================================
# 1. 공통 재료
# ============================================================

NAMES = [
    "지민", "서준", "하윤", "도윤", "민서",
    "유진", "현우", "수빈", "예린", "정우",
]

AMOUNTS = [
    "3만 원", "5만 원", "7만 원", "12만 원",
    "18만 원", "25만 원", "37만 원", "48만 원",
]

DATES = [
    "오늘", "내일", "이번 주", "금요일",
    "다음 주 월요일",
]

TIMES = [
    "오전 9시", "오후 2시", "오후 6시",
    "오늘 자정 전", "1시간 이내",
]

SAFE_ACTIONS = [
    "공식 앱에서 확인해 주세요.",
    "직접 해당 기관 대표번호로 확인해 주세요.",
    "문자에 개인정보를 답장하지 마세요.",
    "공식 홈페이지에서만 처리해 주세요.",
    "링크가 아닌 공식 앱 메뉴를 이용해 주세요.",
]

PHISH_ACTIONS = [
    "이 문자에 인증번호를 회신해 주세요.",
    "안내된 계좌로 즉시 입금해 주세요.",
    "문자로 주민번호 앞자리를 보내 주세요.",
    "계좌번호와 생년월일을 답장해 주세요.",
    "아래 주소에서 본인인증을 완료해 주세요.",
]

SUSPICIOUS_URLS = [
    "http://secure-check24.xyz/a",
    "http://verify-now.top/b",
    "http://notice-help.click/c",
    "http://account-safe.vip/d",
    "http://service-confirm.cc/e",
]

OFFICIAL_STYLE_URLS = [
    "https://official.example/notice",
    "https://service.example/help",
]

BANK_ACCOUNTS = [
    "123-45-678901",
    "302-18-554321",
    "1002-889-774411",
    "110-456-778899",
]


# ============================================================
# 2. subtype별 정상/피싱 문장 생성
# ============================================================

def make_pair(
    scenario: str,
    subtype: str,
    idx: int,
) -> tuple[str, str]:

    name = rng.choice(NAMES)
    amount = rng.choice(AMOUNTS)
    date = rng.choice(DATES)
    time = rng.choice(TIMES)
    suspicious_url = rng.choice(SUSPICIOUS_URLS)
    bank = rng.choice(BANK_ACCOUNTS)

    # --------------------------------------------------------
    # 동일 subtype 내 10개 샘플의 자연스러운 변형
    # normal/phishing 양쪽에 동일한 context를 사용하므로
    # label을 직접 알려주는 단서가 아니다.
    # --------------------------------------------------------

    contexts = [
        "오늘 접수된 건입니다.",
        "조금 전 등록된 요청입니다.",
        "확인 대기 중인 건입니다.",
        "처리 상태가 변경된 건입니다.",
        "추가 확인이 필요한 건입니다.",
        "요청 내역이 갱신되었습니다.",
        "처리 예정 건으로 등록되었습니다.",
        "현재 확인 절차가 진행 중입니다.",
        "관련 요청이 시스템에 등록되었습니다.",
        "처리 결과 확인이 필요한 건입니다.",
    ]

    context = contexts[idx % len(contexts)]

    # 피싱 요구도 한 종류만 반복하지 않도록 분산
    phishing_actions = [
        f"{suspicious_url}에서 본인 확인을 완료해 주세요.",
        "안내 페이지에서 인증 절차를 다시 진행해 주세요.",
        f"{bank}로 확인용 금액을 먼저 보내 주세요.",
        "문자로 받은 확인 화면에서 정보를 다시 등록해 주세요.",
        "담당자 확인을 위해 계좌번호와 생년월일을 회신해 주세요.",
        f"{suspicious_url}에서 등록 정보를 확인해 주세요.",
        "본인 확인을 위해 문자로 전달된 절차를 완료해 주세요.",
        "처리 지연을 막으려면 안내된 인증 절차를 진행해 주세요.",
        "확인용 링크에서 연락처와 결제 정보를 갱신해 주세요.",
        "담당 부서 확인을 위해 요청된 정보를 문자로 보내 주세요.",
    ]

    phish_action = phishing_actions[idx % len(phishing_actions)]

    # 정상 쪽에도 '확인', '오늘까지', '결제' 등
    # 피싱에서 흔한 단어가 일부 존재하도록 구성
    safe_actions = [
        "자세한 내용은 공식 앱의 알림 메뉴에서 확인해 주세요.",
        "문자에 답장하지 말고 기존에 사용하던 공식 앱에서 확인해 주세요.",
        "필요한 확인은 기관 대표번호 또는 공식 홈페이지에서 진행해 주세요.",
        "등록된 공식 앱을 직접 실행해 처리 상태를 확인해 주세요.",
        "결제나 정보 수정이 필요하면 기존 공식 채널에서 직접 진행해 주세요.",
        "문자에 포함된 경로 대신 공식 홈페이지에 직접 접속해 확인해 주세요.",
        "추가 확인은 담당 부서의 기존 연락처를 통해 진행해 주세요.",
        "오늘까지 확인이 필요하며 공식 앱에서 직접 처리할 수 있습니다.",
        "본인 확인이 필요하면 기존에 이용하던 공식 서비스에서 진행해 주세요.",
        "관련 내용은 공식 고객센터 또는 앱 메뉴에서 다시 확인해 주세요.",
    ]

    safe_action = safe_actions[idx % len(safe_actions)]

    # --------------------------------------------------------
    # 가족·지인
    # --------------------------------------------------------

    if scenario == "가족·지인":

        lead = (
            f"{name}아, {subtype} 때문에 연락했어. "
            f"{context} 금액은 {amount} 정도야. "
        )

        normal = (
            lead
            + "급하게 보낼 필요는 없고 내역 먼저 확인한 뒤 "
              "평소 쓰던 계좌로 정산하면 돼."
        )

        phishing = (
            lead
            + f"지금 통화는 어렵고 {time}까지 처리해야 해. "
            + phish_action
        )

    # --------------------------------------------------------
    # 계정·보안
    # --------------------------------------------------------

    elif scenario == "계정·보안":

        lead = (
            f"[보안 알림] {subtype} 관련 안내입니다. "
            f"{context} {time}까지 확인이 필요합니다. "
        )

        normal = (
            lead
            + safe_action
        )

        phishing = (
            lead
            + phish_action
        )

    # --------------------------------------------------------
    # 공공기관
    # --------------------------------------------------------

    elif scenario == "공공기관":

        lead = (
            f"[행정 안내] {subtype} 관련 사항입니다. "
            f"{context} {date}까지 확인하지 않으면 "
            f"처리가 지연될 수 있습니다. "
        )

        normal = (
            lead
            + safe_action
        )

        phishing = (
            lead
            + phish_action
        )

    # --------------------------------------------------------
    # 금융·카드
    # --------------------------------------------------------

    elif scenario == "금융·카드":

        lead = (
            f"[금융 안내] {subtype} 요청과 관련된 알림입니다. "
            f"{context} {time}까지 본인 확인이 필요합니다. "
        )

        normal = (
            lead
            + safe_action
        )

        phishing = (
            lead
            + phish_action
        )

    # --------------------------------------------------------
    # 의료·보험
    # --------------------------------------------------------

    elif scenario == "의료·보험":

        lead = (
            f"[의료·보험 안내] {subtype} 관련 안내입니다. "
            f"{context} 확인 금액은 {amount}이며 "
            f"{date}까지 확인이 필요합니다. "
        )

        normal = (
            lead
            + safe_action
        )

        phishing = (
            lead
            + phish_action
        )

    # --------------------------------------------------------
    # 일상 요청
    # --------------------------------------------------------

    elif scenario == "일상 요청":

        lead = (
            f"{name}님, {subtype} 관련해서 연락드려요. "
            f"{context} 정산 금액은 {amount}입니다. "
        )

        normal = (
            lead
            + "영수증과 정산 내역을 먼저 확인하시고 "
              "기존에 공유한 방식으로 보내주시면 됩니다."
        )

        phishing = (
            lead
            + f"{time}까지 확인이 필요해서 바로 처리 부탁드려요. "
            + phish_action
        )

    # --------------------------------------------------------
    # 중고거래·쇼핑
    # --------------------------------------------------------

    elif scenario == "중고거래·쇼핑":

        lead = (
            f"[거래 안내] {subtype} 관련 상태가 변경되었습니다. "
            f"{context} 거래 금액은 {amount}입니다. "
        )

        normal = (
            lead
            + "구매확정이나 결제 변경은 이용 중인 거래 앱을 "
              "직접 실행해 확인해 주세요."
        )

        phishing = (
            lead
            + "거래 완료를 위해 추가 확인이 필요합니다. "
            + phish_action
        )

    # --------------------------------------------------------
    # 채용·업무
    # --------------------------------------------------------

    elif scenario == "채용·업무":

        lead = (
            f"[업무 안내] {subtype} 관련 요청입니다. "
            f"{context} {date}까지 확인이 필요합니다. "
        )

        normal = (
            lead
            + "회사 내부 시스템이나 기존 담당자 연락처를 통해 "
              "내용을 확인해 주세요."
        )

        phishing = (
            lead
            + "업무 진행을 위해 추가 인증이 필요합니다. "
            + phish_action
        )

    # --------------------------------------------------------
    # 택배·배송
    # --------------------------------------------------------

    elif scenario == "택배·배송":

        lead = (
            f"[배송 안내] {subtype} 관련 알림입니다. "
            f"{context} {time}까지 배송 정보를 확인해 주세요. "
        )

        normal = (
            lead
            + "택배사 공식 앱이나 기존 배송조회 화면에서 "
              "상태를 확인할 수 있습니다."
        )

        phishing = (
            lead
            + "배송 처리를 계속하려면 정보 확인이 필요합니다. "
            + phish_action
        )

    # --------------------------------------------------------
    # 학교·교육
    # --------------------------------------------------------

    elif scenario == "학교·교육":

        lead = (
            f"[학사 안내] {subtype} 관련 공지입니다. "
            f"{context} {date}까지 확인이 필요합니다. "
        )

        normal = (
            lead
            + "학교 포털에 직접 로그인하거나 담당 부서를 통해 "
              "처리 상태를 확인해 주세요."
        )

        phishing = (
            lead
            + "기한 내 처리를 위해 추가 본인 확인이 필요합니다. "
            + phish_action
        )

    else:
        raise ValueError(
            f"지원하지 않는 scenario: {scenario}"
        )

    return normal, phishing


# ============================================================
# 3. 생성
# ============================================================

def main():

    print("=" * 80)
    print("HARD-v2/OOD 생성 시작")
    print("=" * 80)

    if not SPEC_PATH.exists():
        raise FileNotFoundError(
            f"동결 spec 없음: {SPEC_PATH}"
        )

    with open(
        SPEC_PATH,
        "r",
        encoding="utf-8",
    ) as f:
        spec = json.load(f)

    rows = []

    # HARD-v2 전체에서 이미 사용된 원문 추적
    used_texts = set()

    pair_number = 0

    for scenario, subtypes in spec.items():

        for subtype in subtypes:

            for sample_idx in range(10):

                pair_number += 1

                # HARD-v2 내부 exact duplicate 방지
                for retry in range(1000):

                    normal, phishing = make_pair(
                        scenario=scenario,
                        subtype=subtype,
                        idx=sample_idx,
                    )

                    if (
                        normal not in used_texts
                        and phishing not in used_texts
                        and normal != phishing
                    ):
                        used_texts.add(normal)
                        used_texts.add(phishing)
                        break

                else:
                    raise RuntimeError(
                        f"고유 문장 생성 실패: "
                        f"{scenario} / {subtype} / {sample_idx}"
                    )

                pair_id = (
                    f"HV2_{pair_number:04d}"
                )

                rows.append(
                    {
                        "id": (
                            f"{pair_id}_N"
                        ),
                        "pair_id": pair_id,
                        "content": normal,
                        "text": (
                            preprocess_for_model(
                                normal
                            )
                        ),
                        "label": 0,
                        "class": "NORMAL",
                        "label_name": "normal",
                        "scenario": scenario,
                        "subtype": subtype,
                        "difficulty": "OOD",
                        "hard_reason": (
                            "new_subtype_frozen_ood"
                        ),
                        "source": (
                            "synthetic_hard_v2"
                        ),
                    }
                )

                rows.append(
                    {
                        "id": (
                            f"{pair_id}_P"
                        ),
                        "pair_id": pair_id,
                        "content": phishing,
                        "text": (
                            preprocess_for_model(
                                phishing
                            )
                        ),
                        "label": 1,
                        "class": "PHISHING",
                        "label_name": "phishing",
                        "scenario": scenario,
                        "subtype": subtype,
                        "difficulty": "OOD",
                        "hard_reason": (
                            "new_subtype_frozen_ood"
                        ),
                        "source": (
                            "synthetic_hard_v2"
                        ),
                    }
                )

    df = pd.DataFrame(rows)

    # ========================================================
    # 4. 기본 검증
    # ========================================================

    assert len(df) == 1000
    assert df["pair_id"].nunique() == 500

    counts = (
        df["label"]
        .value_counts()
        .sort_index()
    )

    assert counts.get(0, 0) == 500
    assert counts.get(1, 0) == 500

    assert (
        df["subtype"].nunique()
        == 50
    )

    assert (
        df["scenario"].nunique()
        == 10
    )

    # HARD-v2 내부 exact duplicate 검사
    duplicate_count = int(
        df["content"]
        .duplicated()
        .sum()
    )

    print(
        "HARD-v2 내부 exact duplicate:",
        duplicate_count,
    )

    # ========================================================
    # 5. HARD-v1 exact overlap 검사
    # ========================================================

    overlap_count = None

    if HARD_V1_PATH.exists():

        hard_v1 = pd.read_csv(
            HARD_V1_PATH,
            encoding="utf-8-sig",
        )

        if "content" in hard_v1.columns:

            old_texts = set(
                hard_v1["content"]
                .astype(str)
            )

            new_texts = set(
                df["content"]
                .astype(str)
            )

            overlap_count = len(
                old_texts & new_texts
            )

            print(
                "HARD-v1과 exact text overlap:",
                overlap_count,
            )

            assert overlap_count == 0

    # ========================================================
    # 6. 저장
    # ========================================================

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    sha256 = hashlib.sha256(
        OUTPUT_PATH.read_bytes()
    ).hexdigest()

    meta = {
        "seed": SEED,
        "rows": len(df),
        "normal": int(
            (df["label"] == 0).sum()
        ),
        "phishing": int(
            (df["label"] == 1).sum()
        ),
        "pairs": int(
            df["pair_id"].nunique()
        ),
        "scenarios": int(
            df["scenario"].nunique()
        ),
        "subtypes": int(
            df["subtype"].nunique()
        ),
        "internal_exact_duplicates": (
            duplicate_count
        ),
        "hard_v1_exact_overlap": (
            overlap_count
        ),
        "sha256": sha256,
        "frozen": True,
    }

    with open(
        META_PATH,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            meta,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("\n" + "=" * 80)
    print("HARD-v2/OOD 생성 완료")
    print("=" * 80)

    print("shape:", df.shape)

    print(
        "\nlabel 분포:"
    )
    print(
        df["label"]
        .value_counts()
        .sort_index()
    )

    print(
        "\nscenario 수:",
        df["scenario"].nunique(),
    )

    print(
        "subtype 수:",
        df["subtype"].nunique(),
    )

    print(
        "pair 수:",
        df["pair_id"].nunique(),
    )

    print(
        "\nCSV:",
        OUTPUT_PATH,
    )

    print(
        "META:",
        META_PATH,
    )

    print(
        "SHA256:",
        sha256,
    )


if __name__ == "__main__":
    main()
