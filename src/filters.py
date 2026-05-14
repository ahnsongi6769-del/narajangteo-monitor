"""4단계 필터: 키워드 / 계약방식 / 지역 / 업종1468.

각 필터는 list[dict] → list[dict] 시그니처이며, 통과 항목에 메타데이터를 주입할 수 있습니다:
- _matched_keywords: 매칭된 키워드 목록
- _region_display: 알림에 표시할 지역 텍스트
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# 응답 스펙에 따라 지역제한 필드명이 다를 수 있어 후보를 순차 탐색
REGION_FIELD_CANDIDATES: tuple[str, ...] = (
    "prtcptLmtRgnNm",
    "prtcptPsblRgnNm",
    "bidPrtcptLmtNm",
    "rgnLmtNm",
    "prtcptLmtRgnCd",
)

# 업종 필드 후보 (응답 스펙에 따라 다름)
INDUSTRY_FIELD_CANDIDATES: tuple[str, ...] = (
    "bidPrtcptLmtNm",
    "indstrytyNm",
    "indstrytyCd",
    "lcnsLmtNm",
    "prtcptLmtCnstwkLcnsNm",
    "prtcptLmtIndstrytyNm",
)


def _first_nonempty(item: dict, fields: tuple[str, ...]) -> str:
    """후보 필드들 중 비어있지 않은 첫 번째 값(문자열) 반환."""
    for f in fields:
        v = item.get(f)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            return s
    return ""


def filter_by_keywords(items: list[dict], keywords: list[str]) -> list[dict]:
    """공고명(bidNtceNm)에 키워드 하나라도 포함 (대소문자 무시, OR).

    매칭된 키워드를 item['_matched_keywords']에 저장.
    """
    lowered = [(k, k.lower()) for k in keywords]
    out: list[dict] = []
    for item in items:
        name_lower = str(item.get("bidNtceNm", "")).lower()
        matched = [orig for orig, low in lowered if low and low in name_lower]
        if matched:
            item["_matched_keywords"] = matched
            out.append(item)
    return out


def filter_by_contract_method(
    items: list[dict],
    exclude_keywords: list[str],
) -> list[dict]:
    """계약방식(cntrctCnclsMthdNm)에 제외 키워드가 하나도 없으면 통과."""
    out: list[dict] = []
    for item in items:
        method = str(item.get("cntrctCnclsMthdNm", ""))
        if any(ex and ex in method for ex in exclude_keywords):
            continue
        out.append(item)
    return out


def filter_by_region(
    items: list[dict],
    allowed_regions: list[str],
    allow_no_restriction: bool,
) -> list[dict]:
    """지역제한이 비어있거나(전국 가능), 허용 지역명 포함 시 통과."""
    out: list[dict] = []
    for item in items:
        region_text = _first_nonempty(item, REGION_FIELD_CANDIDATES)

        if not region_text:
            # 지역제한 필드가 없음/빈 값 = 전국 가능
            if allow_no_restriction:
                item["_region_display"] = "전국"
                out.append(item)
            continue

        if any(rg in region_text for rg in allowed_regions):
            item["_region_display"] = region_text
            out.append(item)
    return out


def filter_by_industry(
    items: list[dict],
    required_codes: list[str],
    detail_fetcher: Optional[Callable[[str, str], Optional[dict]]] = None,
) -> list[dict]:
    """업종코드 엄격 필터: required_codes가 모두 명시적으로 포함된 공고만 통과.

    1) 목록 응답의 후보 필드들을 먼저 검사.
    2) 비어있으면 detail_fetcher(bidNtceNo, bidNtceOrd)로 상세 조회 시도.
    3) 그래도 없으면 제외 (엄격 정책).
    """
    out: list[dict] = []
    for item in items:
        text = _first_nonempty(item, INDUSTRY_FIELD_CANDIDATES)

        if not text and detail_fetcher is not None:
            no = str(item.get("bidNtceNo", "") or "")
            ord_ = str(item.get("bidNtceOrd", "") or "")
            detail = detail_fetcher(no, ord_)
            if detail:
                text = _first_nonempty(detail, INDUSTRY_FIELD_CANDIDATES)

        if not text:
            # 1468 미확인 → 엄격 제외
            continue

        if all(code in text for code in required_codes):
            out.append(item)
    return out
