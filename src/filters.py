"""3단계 필터: 공고명(키워드+제외) / 계약방식 / 지역.

각 필터는 list[dict] → list[dict] 시그니처이며, 통과 항목에 메타데이터를 주입할 수 있습니다:
- _matched_keywords: 매칭된 키워드 목록 (알림에 표시)
- _region_display: 알림에 표시할 지역 텍스트
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# 응답 스펙에 따라 지역제한 필드명이 다를 수 있어 후보를 순차 탐색
REGION_FIELD_CANDIDATES: tuple[str, ...] = (
    "prtcptLmtRgnNm",
    "prtcptPsblRgnNm",
    "bidPrtcptLmtNm",
    "rgnLmtNm",
    "prtcptLmtRgnCd",
)

# 조달분류 필드(대분류/중분류/세부분류). 어느 하나에라도 제외 키워드가 잡히면 컷.
CLSFC_FIELD_CANDIDATES: tuple[str, ...] = (
    "pubPrcrmntLrgClsfcNm",
    "pubPrcrmntMidClsfcNm",
    "pubPrcrmntClsfcNm",
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


def _dedup_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def filter_by_keywords(
    items: list[dict],
    target_keywords: list[str],
    action_keywords: list[str],
    whitelist_keywords: list[str],
    exclude_keywords: list[str],
) -> list[dict]:
    """공고명(bidNtceNm) 통합 매칭.

    통과 조건:
      ( (target 중 하나 포함) AND (action 중 하나 포함) )
      OR (whitelist 중 하나 포함)
      AND  NOT (exclude 중 하나 포함)

    매칭된 키워드를 item['_matched_keywords']에 저장.
    """
    targets = [(k, k.lower()) for k in target_keywords if k]
    actions = [(k, k.lower()) for k in action_keywords if k]
    whitelists = [(k, k.lower()) for k in whitelist_keywords if k]
    excludes = [low for k in exclude_keywords if k for low in (k.lower(),)]

    out: list[dict] = []
    for item in items:
        name_lower = str(item.get("bidNtceNm", "")).lower()

        if any(ex in name_lower for ex in excludes):
            continue

        matched_targets = [orig for orig, low in targets if low in name_lower]
        matched_actions = [orig for orig, low in actions if low in name_lower]
        matched_whitelists = [orig for orig, low in whitelists if low in name_lower]

        passes_and = bool(matched_targets and matched_actions)
        passes_whitelist = bool(matched_whitelists)

        if not (passes_and or passes_whitelist):
            continue

        item["_matched_keywords"] = _dedup_preserve_order(
            matched_targets + matched_actions + matched_whitelists
        )
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


def filter_by_classification(
    items: list[dict],
    exclude_keywords: list[str],
) -> list[dict]:
    """조달분류(대/중/세부) 어디든 제외 키워드가 포함되면 제외."""
    if not exclude_keywords:
        return list(items)
    out: list[dict] = []
    for item in items:
        joined = " ".join(str(item.get(f, "")) for f in CLSFC_FIELD_CANDIDATES)
        if any(ex and ex in joined for ex in exclude_keywords):
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
