"""나라장터 입찰공고 API 클라이언트.

- 메인 엔드포인트: 조달청_나라장터 입찰공고정보서비스 (용역)
- 5xx/네트워크 오류 시 최대 3회 재시도 (1·2·4초 exponential backoff)
- 4xx는 재시도하지 않음 (인증키 오류 등은 즉시 실패)
- DEBUG_DUMP=1 시 첫 응답 항목의 모든 필드를 stdout에 출력
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

BASE_URL = "https://apis.data.go.kr/1230000/ad/BidPublicInfoService"
LIST_OPERATION = "getBidPblancListInfoServc"  # 용역 입찰공고 목록

MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 1.0
DEFAULT_TIMEOUT = 30


def _now_kst() -> datetime:
    return datetime.now(KST)


def build_window(window_minutes: int, now: Optional[datetime] = None) -> tuple[str, str]:
    """최근 window_minutes분의 (시작, 끝)을 yyyyMMddHHmm으로."""
    end = now or _now_kst()
    start = end - timedelta(minutes=window_minutes)
    fmt = "%Y%m%d%H%M"
    return start.strftime(fmt), end.strftime(fmt)


def _request_with_retry(url: str, params: dict) -> dict:
    """5xx/네트워크 오류 시 재시도하며 JSON dict 반환."""
    last_exc: Optional[Exception] = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            # 4xx — 재시도 의미 없음, 즉시 실패
            if 400 <= resp.status_code < 500:
                logger.error("[API] 4xx 응답 (재시도 안 함): %d %s",
                             resp.status_code, resp.text[:200])
                resp.raise_for_status()
            # 5xx — 재시도 대상
            if resp.status_code >= 500:
                raise requests.HTTPError(
                    f"5xx server error: {resp.status_code}", response=resp
                )
            resp.raise_for_status()
            return resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            if attempt < MAX_RETRIES - 1:
                wait = BACKOFF_BASE_SECONDS * (2 ** attempt)
                logger.warning(
                    "[API] 호출 실패 (attempt %d/%d): %s — %.1fs 후 재시도",
                    attempt + 1, MAX_RETRIES, exc, wait,
                )
                time.sleep(wait)
            else:
                logger.error("[API] 최종 실패 (attempt %d/%d): %s",
                             attempt + 1, MAX_RETRIES, exc)
    assert last_exc is not None
    raise last_exc


def _extract_items(data: dict) -> list[dict]:
    """공공데이터포털 응답 envelope에서 item 리스트를 안전 추출."""
    try:
        body = (data or {}).get("response", {}).get("body", {}) or {}
        items = body.get("items", [])
        if isinstance(items, dict):
            items = items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        if not isinstance(items, list):
            return []
        return items
    except (AttributeError, TypeError):
        return []


def fetch_bid_list(
    service_key: str,
    window_minutes: int = 35,
    page_no: int = 1,
    num_of_rows: int = 200,
    now: Optional[datetime] = None,
    debug_dump: bool = False,
) -> list[dict]:
    """용역 입찰공고 목록 조회 (입찰공고일 기준 최근 window_minutes분)."""
    bgn, end = build_window(window_minutes, now=now)
    url = f"{BASE_URL}/{LIST_OPERATION}"
    params = {
        "serviceKey": service_key,  # requests가 자동 URL-인코딩
        "pageNo": page_no,
        "numOfRows": num_of_rows,
        "inqryDiv": 1,              # 입찰공고일 기준
        "inqryBgnDt": bgn,
        "inqryEndDt": end,
        "type": "json",
    }
    logger.info("[API] 호출 윈도우: %s ~ %s", bgn, end)
    data = _request_with_retry(url, params)

    items = _extract_items(data)
    logger.info("[API] 응답 OK, 총 %d건 수신", len(items))

    if debug_dump and items:
        print("[DEBUG_DUMP] 첫 응답 항목의 모든 필드 ↓↓↓")
        print(json.dumps(items[0], ensure_ascii=False, indent=2))
        print("[DEBUG_DUMP] ↑↑↑ 위 필드명으로 filters.py의 후보 리스트를 조정하세요.")

    return items


def fetch_bid_detail(
    service_key: str,
    bid_ntce_no: str,
    bid_ntce_ord: str,
) -> Optional[dict]:
    """입찰공고 상세 조회 (목록에 업종 정보가 없을 때 fallback hook).

    공공데이터포털의 상세 endpoint·파라미터는 운영명세에 따라 다를 수 있어
    현재는 hook만 노출하고 None을 반환합니다. 결과적으로 filter_by_industry가
    "1468 미확인 → 제외" 로 처리하므로 엄격 필터가 유지됩니다.

    실제 상세 op명을 확인한 뒤 아래 주석 부분을 활성화하세요.
    """
    if not bid_ntce_no:
        return None

    # 실제 상세 endpoint를 알게 되면 여기를 활성화:
    #
    # url = f"{BASE_URL}/getBidPblancListInfoServcDtl"
    # params = {
    #     "serviceKey": service_key,
    #     "bidNtceNo": bid_ntce_no,
    #     "bidNtceOrd": bid_ntce_ord,
    #     "type": "json",
    # }
    # try:
    #     data = _request_with_retry(url, params)
    #     items = _extract_items(data)
    #     return items[0] if items else None
    # except Exception as exc:
    #     logger.warning("[API:DETAIL] 상세 조회 실패: %s-%s (%s)",
    #                    bid_ntce_no, bid_ntce_ord, exc)
    #     return None

    logger.debug("[API:DETAIL] hook 미구현 — %s-%s 는 목록 정보로만 판정",
                 bid_ntce_no, bid_ntce_ord)
    return None
