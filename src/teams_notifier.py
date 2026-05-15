"""Microsoft Teams Workflows 웹훅 알림 (Adaptive Card 형식).

Power Automate Workflows의 "Post adaptive card in a chat or channel" 트리거가
받는 페이로드 형식 — `{"attachments": [{"contentType": "...adaptive", "content": {...}}]}`.

- 한 공고당 한 메시지, 여러 건이면 1초 간격
- requests.post(json=...) 가 UTF-8 자동 처리 → 한글 깨짐 없음
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
DEFAULT_DELAY_SECONDS = 1.0

ADAPTIVE_CARD_SCHEMA = "http://adaptivecards.io/schemas/adaptive-card.json"
ADAPTIVE_CARD_VERSION = "1.4"
ADAPTIVE_CARD_CONTENT_TYPE = "application/vnd.microsoft.card.adaptive"


def _safe_str(value) -> str:
    """None/빈 값을 '-'로 정규화."""
    if value is None:
        return "-"
    s = str(value).strip()
    return s if s else "-"


def _format_price(value) -> str:
    """추정가격 한국 원화 포맷. 비어있으면 '미공개'."""
    if value is None:
        return "미공개"
    s = str(value).strip()
    if not s:
        return "미공개"
    try:
        n = int(float(s))
        return f"{n:,}원"
    except (ValueError, TypeError):
        return s


def build_adaptive_card(bid_data: dict, matched_keywords: list[str]) -> dict:
    """공고 1건에 대한 Adaptive Card 페이로드 전체 생성.

    반환값은 그대로 requests.post(json=...) 에 넘길 수 있는 dict.
    """
    keywords = ", ".join(matched_keywords) if matched_keywords else "-"
    region = bid_data.get("_region_display") or "전국"
    price = _format_price(bid_data.get("presmptPrce"))
    url = bid_data.get("bidNtceDtlUrl") or bid_data.get("bidNtceUrl") or ""
    bid_no = (
        f"{_safe_str(bid_data.get('bidNtceNo'))}-"
        f"{_safe_str(bid_data.get('bidNtceOrd'))}"
    )

    body: list[dict[str, Any]] = [
        {
            "type": "TextBlock",
            "text": f"📢 [신규 공고] {_safe_str(bid_data.get('bidNtceNm'))}",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True,
        },
        {
            "type": "FactSet",
            "facts": [
                {"title": "🔍 매칭 키워드", "value": keywords},
                {"title": "🏢 발주기관", "value": _safe_str(bid_data.get("ntceInsttNm"))},
                {"title": "🏛️ 수요기관", "value": _safe_str(bid_data.get("dminsttNm"))},
                {"title": "📋 공고번호", "value": bid_no},
                {"title": "📑 계약방식", "value": _safe_str(bid_data.get("cntrctCnclsMthdNm"))},
                {"title": "💰 추정가격", "value": price},
                {"title": "📍 참가가능지역", "value": region},
                {"title": "📅 공고일시", "value": _safe_str(bid_data.get("bidNtceDate"))},
                {"title": "⏰ 입찰마감", "value": _safe_str(bid_data.get("bidClseDate"))},
                {"title": "🎯 개찰일시", "value": _safe_str(bid_data.get("opengDate"))},
            ],
        },
    ]

    card: dict[str, Any] = {
        "$schema": ADAPTIVE_CARD_SCHEMA,
        "type": "AdaptiveCard",
        "version": ADAPTIVE_CARD_VERSION,
        "body": body,
    }

    if url:
        card["actions"] = [
            {
                "type": "Action.OpenUrl",
                "title": "🔗 나라장터에서 상세 보기",
                "url": url,
            }
        ]

    return {
        "attachments": [
            {
                "contentType": ADAPTIVE_CARD_CONTENT_TYPE,
                "content": card,
            }
        ]
    }


def send_one(webhook_url: str, payload: dict, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Adaptive Card 페이로드 1건 전송."""
    try:
        resp = requests.post(webhook_url, json=payload, timeout=timeout)
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("[NOTIFY] Teams 전송 실패: %s", exc)
        resp_obj: Optional[requests.Response] = getattr(exc, "response", None)
        if resp_obj is not None:
            logger.error("[NOTIFY] 응답 본문: %s", resp_obj.text[:500])
        return False


def send_all(
    webhook_url: str,
    items: list[dict],
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
) -> tuple[int, int]:
    """공고 목록을 순차 전송. (성공, 실패) 반환."""
    sent = 0
    failed = 0
    for idx, item in enumerate(items):
        matched = item.get("_matched_keywords") or []
        payload = build_adaptive_card(item, matched)
        if send_one(webhook_url, payload):
            sent += 1
        else:
            failed += 1
        if idx < len(items) - 1:
            time.sleep(delay_seconds)
    return sent, failed
