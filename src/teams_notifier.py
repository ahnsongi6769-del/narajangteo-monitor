"""Microsoft Teams Workflows 웹훅 알림.

- POST {"text": "<HTML>"} 형식 (Workflows의 'Post to chat' 표준)
- 한 공고당 한 메시지, 여러 건이면 1초 간격
- 호출당 (성공, 실패) 카운트 반환
"""
from __future__ import annotations

import html
import logging
import time

import requests

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 30
DEFAULT_DELAY_SECONDS = 1.0


def _e(value) -> str:
    """HTML 이스케이프 + None/공백 안전 처리."""
    if value is None:
        return ""
    return html.escape(str(value))


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


def build_html(item: dict) -> str:
    """알림 HTML 본문 생성 (스펙 그대로)."""
    keywords_list = item.get("_matched_keywords") or []
    keywords = ", ".join(keywords_list) if keywords_list else "-"
    region = item.get("_region_display") or "전국"
    price = _format_price(item.get("presmptPrce"))
    url = item.get("bidNtceDtlUrl") or item.get("bidNtceUrl") or ""

    lines = [
        f"<h2>📢 [신규 공고] {_e(item.get('bidNtceNm'))}</h2>",
        f"<p><b>🔍 매칭 키워드:</b> {_e(keywords)}</p>",
        f"<p><b>🏢 발주기관:</b> {_e(item.get('ntceInsttNm'))}</p>",
        f"<p><b>🏛️ 수요기관:</b> {_e(item.get('dminsttNm'))}</p>",
        f"<p><b>📋 공고번호:</b> {_e(item.get('bidNtceNo'))}-{_e(item.get('bidNtceOrd'))}</p>",
        f"<p><b>📑 계약방식:</b> {_e(item.get('cntrctCnclsMthdNm'))}</p>",
        f"<p><b>💰 추정가격:</b> {_e(price)}</p>",
        f"<p><b>📍 참가가능지역:</b> {_e(region)}</p>",
        f"<p><b>🏭 업종:</b> 1468 포함 ✅</p>",
        f"<p><b>📅 공고일시:</b> {_e(item.get('bidNtceDate'))}</p>",
        f"<p><b>⏰ 입찰마감:</b> {_e(item.get('bidClseDate'))}</p>",
        f"<p><b>🎯 개찰일시:</b> {_e(item.get('opengDate'))}</p>",
    ]
    if url:
        lines.append(f'<p>🔗 <a href="{_e(url)}">나라장터에서 상세 보기</a></p>')
    return "".join(lines)


def send_one(webhook_url: str, html_body: str, timeout: int = DEFAULT_TIMEOUT) -> bool:
    try:
        resp = requests.post(
            webhook_url,
            json={"text": html_body},
            timeout=timeout,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.error("[NOTIFY] Teams 전송 실패: %s", exc)
        return False


def send_all(
    webhook_url: str,
    items: list[dict],
    delay_seconds: float = DEFAULT_DELAY_SECONDS,
) -> tuple[int, int]:
    """순차 전송. (성공 건수, 실패 건수) 반환."""
    sent = 0
    failed = 0
    for idx, item in enumerate(items):
        body = build_html(item)
        if send_one(webhook_url, body):
            sent += 1
        else:
            failed += 1
        if idx < len(items) - 1:
            time.sleep(delay_seconds)
    return sent, failed
