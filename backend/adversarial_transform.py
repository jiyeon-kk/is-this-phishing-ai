"""스미싱 우회 공격 시뮬레이션용 결정론적 문자 변형.

실제 공격을 생성하는 목적이 아니라,
피싱 탐지 시스템의 강건성을 검증하고 데모하기 위한 변형을 제공한다.

동일한 입력에는 동일한 결과를 반환한다.
"""

import re


def insert_spaces(text: str) -> str:
    """주요 위험 단어 내부에 공백을 삽입한다."""

    replacements = {
        "계좌": "계 좌",
        "정지": "정 지",
        "인증": "인 증",
        "송금": "송 금",
        "결제": "결 제",
        "확인": "확 인",
        "클릭": "클 릭",
        "설치": "설 치",
    }

    result = text

    for original, transformed in replacements.items():
        result = result.replace(original, transformed)

    return result


def insert_special_characters(text: str) -> str:
    """주요 위험 단어 사이에 특수문자를 삽입한다."""

    replacements = {
        "계좌": "계·좌",
        "정지": "정-지",
        "인증": "인_증",
        "송금": "송.금",
        "결제": "결/제",
        "확인": "확·인",
        "클릭": "클-릭",
        "설치": "설_치",
    }

    result = text

    for original, transformed in replacements.items():
        result = result.replace(original, transformed)

    return result


def mix_english(text: str) -> str:
    """일부 한글 표현을 영문 혼용 형태로 바꾼다."""

    replacements = {
        "정지": "정zi",
        "클릭": "click",
        "로그인": "log-in",
        "계좌": "계jwa",
        "확인": "확in",
        "인증": "인jeung",
    }

    result = text

    for original, transformed in replacements.items():
        result = result.replace(original, transformed)

    return result


def obfuscate_url(text: str) -> str:
    """URL 프로토콜과 도메인 구분 문자를 변형한다."""

    result = re.sub(
        r"https?://",
        "hxxp://",
        text,
        flags=re.IGNORECASE,
    )

    result = result.replace(".com", "[.]com")
    result = result.replace(".net", "[.]net")
    result = result.replace(".org", "[.]org")
    result = result.replace(".xyz", "[.]xyz")
    result = result.replace(".top", "[.]top")

    return result


def split_hangul_like(text: str) -> str:
    """핵심 단어를 자모가 섞인 형태로 변형한다."""

    replacements = {
        "정지": "정ㅈㅣ",
        "인증": "인ㅈㅡㅇ",
        "계좌": "계ㅈㅘ",
        "송금": "송ㄱㅡㅁ",
        "확인": "확ㅇㅣㄴ",
        "결제": "결ㅈㅔ",
    }

    result = text

    for original, transformed in replacements.items():
        result = result.replace(original, transformed)

    return result


def generate_variants(text: str) -> list[dict]:
    """원본 문자에서 데모용 우회 변형 목록을 생성한다."""

    variants = [
        {
            "type": "spacing",
            "label": "공백 삽입",
            "text": insert_spaces(text),
        },
        {
            "type": "special_character",
            "label": "특수문자 삽입",
            "text": insert_special_characters(text),
        },
        {
            "type": "english_mix",
            "label": "한글·영문 혼용",
            "text": mix_english(text),
        },
        {
            "type": "url_obfuscation",
            "label": "URL 형태 변형",
            "text": obfuscate_url(text),
        },
        {
            "type": "hangul_split",
            "label": "자모 유사 변형",
            "text": split_hangul_like(text),
        },
    ]

    return [
        variant
        for variant in variants
        if variant["text"] != text
    ]