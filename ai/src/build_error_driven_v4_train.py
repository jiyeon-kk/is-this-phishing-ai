from __future__ import annotations

from pathlib import Path
import random

import pandas as pd

from src.text_features import preprocess_for_model


# ============================================================
# 1. 기본 설정
# ============================================================

SEED = 42
random.seed(SEED)

AI_ROOT = Path(__file__).resolve().parent.parent

V3_PATH = (
    AI_ROOT
    / "data"
    / "processed"
    / "train_augmented_v3.csv"
)

OUTPUT_PATH = (
    AI_ROOT
    / "data"
    / "processed"
    / "train_augmented_v4.csv"
)

NEW_SAMPLE_PATH = (
    AI_ROOT
    / "data"
    / "processed"
    / "error_driven_v4_samples.csv"
)

# HARD 테스트와 문장 중복 여부 확인용
HARD_PATH = (
    AI_ROOT
    / "data"
    / "raw"
    / "korean_phishing_hard_test_1000.csv"
)


# ============================================================
# 2. 공통 표현 후보
# ============================================================

NAMES = [
    "민수",
    "수빈",
    "지우",
    "현우",
    "예린",
    "유진",
    "서준",
    "하린",
]

FAMILY = [
    "엄마",
    "아빠",
    "언니",
    "누나",
    "형",
    "오빠",
    "이모",
    "삼촌",
]

AMOUNTS = [
    "3만 원",
    "5만 원",
    "8만 원",
    "12만 원",
    "18만 원",
    "25만 원",
    "37만 원",
    "48만 원",
]

TIME_EXPRESSIONS = [
    "오늘",
    "내일",
    "이번 주",
    "다음 주",
]

CARD_COMPANIES = [
    "한빛카드",
    "새봄카드",
    "가온카드",
    "미래카드",
]

DELIVERY_COMPANIES = [
    "한빛택배",
    "새봄택배",
    "가온택배",
    "미래택배",
]

UNIVERSITIES = [
    "한빛대학교",
    "새봄대학교",
    "가온대학교",
    "미래대학교",
]

PUBLIC_ORGS = [
    "민원센터",
    "구청 민원실",
    "시청 민원실",
    "행정민원 안내",
]


# ============================================================
# 3. Hard Normal 생성
#
# 목적:
# 위험 키워드가 있어도 실제 행동은 안전한 정상 문장 학습
#
# HARD 오류 분석에서:
# 가족·지인 정상 → FP 다수
# 일상 요청 정상 → FP 다수
# ============================================================

def generate_hard_normals(
    n_per_type: int = 50,
) -> list[dict]:

    rows = []

    # --------------------------------------------------------
    # A. 가족·지인 + 인증번호
    # --------------------------------------------------------

    templates = [
        "{family}, 인증번호가 와도 나한테 보내지 말고 바로 삭제해줘.",
        "{family}, 내가 로그인 중이어도 인증번호는 절대 알려주지 않아도 돼.",
        "{family}, 인증번호 문자가 오면 아무한테도 전달하지 말고 무시해줘.",
        "{family}, 내 이름으로 인증 문자가 와도 숫자는 보내지 말고 삭제해줘.",
        "{family}, 인증번호를 부탁하는 연락이 와도 내가 아니니까 알려주지 마.",
    ]

    generated = set()

    while len(generated) < n_per_type:

        text = random.choice(
            templates
        ).format(
            family=random.choice(FAMILY),
        )

        generated.add(text)

    for text in generated:
        rows.append(
            {
                "raw_text": text,
                "label": 0,
                "scenario": "가족·지인",
                "subtype": "안전 인증번호 안내",
                "augmentation_type": "error_driven_hard_normal",
            }
        )

    # --------------------------------------------------------
    # B. 가족·지인 + 송금/결제
    # --------------------------------------------------------

    templates = [
        "{family}, {amount}은 내가 이미 직접 결제했으니까 따로 송금하지 않아도 돼.",
        "{family}, 병원비 {amount}은 내가 창구에서 낼 거라서 계좌이체할 필요 없어.",
        "{family}, 수리비 {amount} 결제는 끝났으니까 돈 보내지 말고 물건만 찾아오면 돼.",
        "{family}, 아까 말한 {amount}은 해결됐어. 내 계좌로 보내지 않아도 돼.",
        "{family}, 상품권은 이미 취소했으니까 결제 문자 와도 승인하지 마.",
    ]

    generated = set()

    while len(generated) < n_per_type:

        text = random.choice(
            templates
        ).format(
            family=random.choice(FAMILY),
            amount=random.choice(AMOUNTS),
        )

        generated.add(text)

    for text in generated:
        rows.append(
            {
                "raw_text": text,
                "label": 0,
                "scenario": "가족·지인",
                "subtype": "안전 송금·결제 안내",
                "augmentation_type": "error_driven_hard_normal",
            }
        )

    # --------------------------------------------------------
    # C. 일상 요청 + 모임 회비
    # --------------------------------------------------------

    templates = [
        "{name}아, 모임 회비 {amount}은 단체방에 공지된 기존 계좌로 보내면 돼. 개인 메시지로 온 새 계좌에는 보내지 마.",
        "{name}님, 회비 계좌는 변경되지 않았습니다. 개인 답장으로 새 계좌를 안내받으면 송금하지 마세요.",
        "이번 모임 회비는 {amount}이고 기존 공지 계좌만 사용해. 갑자기 다른 계좌를 보내면 확인부터 해.",
        "{name}아, 회비는 이미 정산됐으니까 지금 추가로 송금할 돈은 없어.",
        "회비 {amount}은 단체방 공지에서 확인하고, 개인 메시지로 받은 계좌에는 보내지 않아도 돼.",
    ]

    generated = set()

    while len(generated) < n_per_type:

        text = random.choice(
            templates
        ).format(
            name=random.choice(NAMES),
            amount=random.choice(AMOUNTS),
        )

        generated.add(text)

    for text in generated:
        rows.append(
            {
                "raw_text": text,
                "label": 0,
                "scenario": "일상 요청",
                "subtype": "안전 모임 회비",
                "augmentation_type": "error_driven_hard_normal",
            }
        )

    # --------------------------------------------------------
    # D. 일상 요청 + 링크/사진/결제 안전 안내
    # --------------------------------------------------------

    templates = [
        "{name}아, 사진 링크 보냈는데 로그인 화면이 나오면 열지 말고 나한테 먼저 확인해줘.",
        "공연 환불은 결제했던 카드로 자동 처리된대. 따로 온 링크에는 정보 입력하지 마.",
        "도시락 비용 {amount}은 이미 가게에 결제했으니까 추가 송금은 필요 없어.",
        "{name}아, 택시비는 내가 먼저 냈으니 지금 계좌이체하지 않아도 돼.",
        "공유 링크에서 비밀번호나 인증번호를 요구하면 입력하지 말고 공식 앱에서 확인해.",
    ]

    generated = set()

    while len(generated) < n_per_type:

        text = random.choice(
            templates
        ).format(
            name=random.choice(NAMES),
            amount=random.choice(AMOUNTS),
        )

        generated.add(text)

    for text in generated:
        rows.append(
            {
                "raw_text": text,
                "label": 0,
                "scenario": "일상 요청",
                "subtype": "안전 행동 안내",
                "augmentation_type": "error_driven_hard_normal",
            }
        )

    return rows


# ============================================================
# 4. Hard Phishing 생성
#
# 목적:
# URL이 없어도 개인정보/금전/민감 행동을 요구하는 피싱 보강
#
# HARD 오류 분석에서:
# 배송지 변경
# 민원 서류
# 카드 재발급
# 수강신청
# 유형의 FN 집중
# ============================================================

def generate_hard_phishing(
    n_per_type: int = 50,
) -> list[dict]:

    rows = []

    # --------------------------------------------------------
    # A. 배송지 변경 + 개인정보 회신
    # --------------------------------------------------------

    templates = [
        "[{company}] 배송지 오류가 확인되었습니다. 배송을 계속하려면 주민번호 앞자리를 문자로 보내주세요.",
        "[{company}] 주소 변경 확인이 필요합니다. 수령인 생년월일과 휴대폰 번호를 답장해주세요.",
        "[{company}] 배송지가 일치하지 않아 상품이 보류되었습니다. 본인 확인을 위해 주민등록번호 앞자리를 회신하세요.",
        "[{company}] 주소 수정 요청이 접수되었습니다. 취소하려면 이름과 생년월일을 문자로 보내주세요.",
        "[{company}] 배송 정보 확인이 필요합니다. 수령인의 개인정보를 이 번호로 답장해야 배송이 진행됩니다.",
    ]

    generated = set()

    while len(generated) < n_per_type:

        text = random.choice(
            templates
        ).format(
            company=random.choice(
                DELIVERY_COMPANIES
            ),
        )

        generated.add(text)

    for text in generated:
        rows.append(
            {
                "raw_text": text,
                "label": 1,
                "scenario": "택배·배송",
                "subtype": "배송지 변경 개인정보 요구",
                "augmentation_type": "error_driven_hard_phishing",
            }
        )

    # --------------------------------------------------------
    # B. 민원 서류 + 신분정보 회신
    # --------------------------------------------------------

    templates = [
        "[{org}] 신청 서류에 오류가 발견되었습니다. 처리를 계속하려면 신분증 사진을 문자로 보내주세요.",
        "[{org}] 주민등록 정보 확인이 필요합니다. 생년월일과 주민번호 앞자리를 회신해주세요.",
        "[{org}] 민원 서류가 반려될 예정입니다. 본인 확인을 위해 신분증 앞면을 이 번호로 전송하세요.",
        "[{org}] 신청자 정보가 일치하지 않습니다. 이름과 주민번호 앞자리를 문자로 답장해주세요.",
        "[{org}] 오늘까지 개인정보 확인이 완료되지 않으면 민원이 취소됩니다. 신분증 사진을 회신하세요.",
    ]

    generated = set()

    while len(generated) < n_per_type:

        text = random.choice(
            templates
        ).format(
            org=random.choice(
                PUBLIC_ORGS
            ),
        )

        generated.add(text)

    for text in generated:
        rows.append(
            {
                "raw_text": text,
                "label": 1,
                "scenario": "공공기관",
                "subtype": "민원 개인정보 요구",
                "augmentation_type": "error_driven_hard_phishing",
            }
        )

    # --------------------------------------------------------
    # C. 카드 재발급 + 답장/개인정보 요구
    # --------------------------------------------------------

    templates = [
        "[{company}] 카드 재발급 신청이 접수되었습니다. 본인이 아니라면 '취소'라고 답장해주세요.",
        "[{company}] 새 카드 발급이 진행 중입니다. 취소하려면 생년월일을 문자로 회신하세요.",
        "[{company}] 재발급 카드 배송 전 확인이 필요합니다. 카드 비밀번호 앞 두 자리를 답장해주세요.",
        "[{company}] 카드 재발급 확인을 위해 주민번호 앞자리와 이름을 문자로 보내주세요.",
        "[{company}] 재발급 신청을 취소하려면 본인 인증번호를 이 번호로 회신해주세요.",
    ]

    generated = set()

    while len(generated) < n_per_type:

        text = random.choice(
            templates
        ).format(
            company=random.choice(
                CARD_COMPANIES
            ),
        )

        generated.add(text)

    for text in generated:
        rows.append(
            {
                "raw_text": text,
                "label": 1,
                "scenario": "금융·카드",
                "subtype": "카드 재발급 개인정보 요구",
                "augmentation_type": "error_driven_hard_phishing",
            }
        )

    # --------------------------------------------------------
    # D. 수강신청 + 금전/개인정보 요구
    # --------------------------------------------------------

    templates = [
        "[{univ}] 수강신청 오류가 확인되었습니다. 좌석 유지를 위해 복구 비용 {amount}을 납부해주세요.",
        "[{univ}] 수강신청이 취소될 예정입니다. 유지하려면 학번과 비밀번호를 문자로 보내주세요.",
        "[{univ}] 추가 수강 승인을 위해 처리 비용 {amount}을 개인 계좌로 입금해야 합니다.",
        "[{univ}] 수강신청 복구를 위해 본인 확인이 필요합니다. 학번과 포털 비밀번호를 회신하세요.",
        "[{univ}] {time}까지 수강정보를 확인하지 않으면 신청이 취소됩니다. 주민번호 앞자리를 문자로 보내주세요.",
    ]

    generated = set()

    while len(generated) < n_per_type:

        text = random.choice(
            templates
        ).format(
            univ=random.choice(
                UNIVERSITIES
            ),
            amount=random.choice(
                AMOUNTS
            ),
            time=random.choice(
                TIME_EXPRESSIONS
            ),
        )

        generated.add(text)

    for text in generated:
        rows.append(
            {
                "raw_text": text,
                "label": 1,
                "scenario": "학교·교육",
                "subtype": "수강신청 금전·개인정보 요구",
                "augmentation_type": "error_driven_hard_phishing",
            }
        )

    return rows


# ============================================================
# 5. HARD 테스트셋과 정확히 같은 문장 제거
#
# 중요:
# HARD 테스트의 문장을 학습 데이터에 직접 넣지 않음
# ============================================================

def remove_hard_test_overlap(
    new_df: pd.DataFrame,
) -> pd.DataFrame:

    if not HARD_PATH.exists():

        print(
            "[주의] HARD 테스트 파일을 찾지 못해 "
            "정확 문자열 중복 검사를 생략합니다."
        )

        return new_df

    hard_df = pd.read_csv(
        HARD_PATH,
        encoding="utf-8-sig",
    )

    if "content" not in hard_df.columns:

        print(
            "[주의] HARD 테스트에 content 컬럼이 없어 "
            "정확 문자열 중복 검사를 생략합니다."
        )

        return new_df

    hard_texts = set(
        hard_df["content"]
        .dropna()
        .astype(str)
        .str.strip()
    )

    before = len(new_df)

    new_df = new_df[
        ~new_df["raw_text"]
        .astype(str)
        .str.strip()
        .isin(hard_texts)
    ].copy()

    removed = before - len(new_df)

    print(
        f"HARD 테스트와 정확히 같은 문장 제거: {removed}건"
    )

    return new_df


# ============================================================
# 6. V3 데이터의 텍스트 컬럼 탐색
# ============================================================

def detect_text_column(
    df: pd.DataFrame,
) -> str:

    candidates = [
        "text",
        "content",
        "message",
        "sentence",
    ]

    for col in candidates:

        if col in df.columns:
            return col

    raise ValueError(
        "V3 데이터에서 텍스트 컬럼을 찾을 수 없습니다.\n"
        f"현재 컬럼: {list(df.columns)}"
    )


# ============================================================
# 7. V3 형식에 맞춰 신규 샘플 변환
# ============================================================

def convert_to_v3_schema(
    v3_df: pd.DataFrame,
    new_df: pd.DataFrame,
    text_col: str,
) -> pd.DataFrame:

    records = []

    for _, row in new_df.iterrows():

        record = {
            col: pd.NA
            for col in v3_df.columns
        }

        # 기존 V3가 text 컬럼이면
        # 기존 학습과 동일한 전처리 적용
        if text_col == "text":

            record[text_col] = (
                preprocess_for_model(
                    str(
                        row["raw_text"]
                    )
                )
            )

        else:

            record[text_col] = (
                str(
                    row["raw_text"]
                )
            )

        record["label"] = int(
            row["label"]
        )

        # V3에 아래 컬럼들이 이미 있다면 정보도 저장
        optional_columns = [
            "scenario",
            "subtype",
            "augmentation_type",
            "source",
        ]

        for col in optional_columns:

            if col not in record:
                continue

            if col == "source":
                record[col] = "synthetic_error_driven_v4"

            elif col in row.index:
                record[col] = row[col]

        records.append(
            record
        )

    return pd.DataFrame(
        records,
        columns=v3_df.columns,
    )


# ============================================================
# 8. 실행
# ============================================================

def main() -> None:

    print("=" * 100)
    print("Error-driven V4 증강 데이터 생성")
    print("=" * 100)

    # --------------------------------------------------------
    # V3 로드
    # --------------------------------------------------------

    if not V3_PATH.exists():

        raise FileNotFoundError(
            f"V3 파일이 없습니다:\n{V3_PATH}"
        )

    v3_df = pd.read_csv(
        V3_PATH,
        encoding="utf-8-sig",
    )

    print(
        f"\nV3 데이터: {len(v3_df):,}건"
    )

    print(
        "\nV3 label 분포:"
    )

    print(
        v3_df["label"]
        .value_counts()
        .sort_index()
    )

    # --------------------------------------------------------
    # 신규 데이터 생성
    # --------------------------------------------------------

    normal_rows = generate_hard_normals(
        n_per_type=20,
    )

    phishing_rows = generate_hard_phishing(
        n_per_type=20,
    )

    new_df = pd.DataFrame(
        normal_rows
        + phishing_rows
    )

    new_df = new_df.drop_duplicates(
        subset=[
            "raw_text",
            "label",
        ]
    ).reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # HARD 직접 중복 제거
    # --------------------------------------------------------

    new_df = remove_hard_test_overlap(
        new_df
    )

    # --------------------------------------------------------
    # 신규 샘플 내부 통계
    # --------------------------------------------------------

    print(
        "\n신규 Error-driven 샘플:"
    )

    print(
        f"총 {len(new_df):,}건"
    )

    print(
        "\n신규 label 분포:"
    )

    print(
        new_df["label"]
        .value_counts()
        .sort_index()
    )

    print(
        "\n신규 scenario × label:"
    )

    print(
        pd.crosstab(
            new_df["scenario"],
            new_df["label"],
        )
    )

    print(
        "\n신규 subtype:"
    )

    print(
        new_df[
            [
                "subtype",
                "label",
            ]
        ]
        .value_counts()
        .sort_index()
    )

    # --------------------------------------------------------
    # 신규 샘플 원문 별도 저장
    # --------------------------------------------------------

    NEW_SAMPLE_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    new_df.to_csv(
        NEW_SAMPLE_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # V3 스키마 탐색
    # --------------------------------------------------------

    text_col = detect_text_column(
        v3_df
    )

    print(
        f"\nV3 텍스트 컬럼: {text_col}"
    )

    formatted_new_df = (
        convert_to_v3_schema(
            v3_df=v3_df,
            new_df=new_df,
            text_col=text_col,
        )
    )

    # --------------------------------------------------------
    # 기존 V3와 신규 데이터 중복 제거
    # --------------------------------------------------------

    existing_texts = set(
        v3_df[text_col]
        .dropna()
        .astype(str)
        .str.strip()
    )

    before = len(
        formatted_new_df
    )

    formatted_new_df = (
        formatted_new_df[
            ~formatted_new_df[
                text_col
            ]
            .astype(str)
            .str.strip()
            .isin(
                existing_texts
            )
        ]
        .copy()
    )

    duplicate_with_v3 = (
        before
        - len(
            formatted_new_df
        )
    )

    print(
        f"\n기존 V3와 중복되어 제거: "
        f"{duplicate_with_v3}건"
    )

    # --------------------------------------------------------
    # V4 생성
    # --------------------------------------------------------

    v4_df = pd.concat(
        [
            v3_df,
            formatted_new_df,
        ],
        ignore_index=True,
    )


    # 재현 가능한 shuffle
    v4_df = (
        v4_df
        .sample(
            frac=1.0,
            random_state=SEED,
        )
        .reset_index(
            drop=True
        )
    )

    # --------------------------------------------------------
    # 저장
    # --------------------------------------------------------

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    v4_df.to_csv(
        OUTPUT_PATH,
        index=False,
        encoding="utf-8-sig",
    )

    # --------------------------------------------------------
    # 최종 출력
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 100
    )

    print(
        "V4 생성 결과"
    )

    print(
        "=" * 100
    )

    print(
        f"기존 V3: {len(v3_df):,}건"
    )

    print(
        f"실제 신규 추가: "
        f"{len(formatted_new_df):,}건"
    )

    print(
        f"최종 V4: {len(v4_df):,}건"
    )

    print(
        "\nV4 label 분포:"
    )

    print(
        v4_df["label"]
        .value_counts()
        .sort_index()
    )

    print(
        "\n저장 완료:"
    )

    print(
        f"- 신규 샘플: {NEW_SAMPLE_PATH}"
    )

    print(
        f"- V4 학습 데이터: {OUTPUT_PATH}"
    )

    print(
        "\n중요:"
    )

    print(
        "- HARD 테스트 문장 자체를 학습하지 않았습니다."
    )

    print(
        "- HARD 오분류에서 발견한 오류 패턴만 이용해 "
        "새로운 합성 문장을 생성했습니다."
    )

    print(
        "- HARD 테스트는 이후에도 독립 평가용으로 유지합니다."
    )


if __name__ == "__main__":
    main()