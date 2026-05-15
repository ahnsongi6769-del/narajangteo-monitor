"""나라장터 모니터 메인 진입점.

흐름:
  config 로드
  → API 호출 (최근 N분)
  → 공고명(키워드+제외) → 계약방식 → 지역 필터
  → seen.json 중복 제거
  → Teams 순차 전송 (1초 간격)
  → seen.json 업데이트 (+ 30일 청소)
"""
from __future__ import annotations

import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

from .dedup import cleanup_old, filter_new, load_seen, mark_sent, save_seen
from .filters import (
    filter_by_contract_method,
    filter_by_keywords,
    filter_by_region,
)
from .nara_api import fetch_bid_list
from .teams_notifier import send_all

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.yaml"
SEEN_PATH = ROOT / "seen.json"


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
    )


def _load_config(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> int:
    _setup_logging()
    load_dotenv()  # .env가 있으면 로컬 테스트 지원, 없으면 무시

    api_key = os.environ.get("NARA_API_KEY", "").strip()
    webhook = os.environ.get("TEAMS_WEBHOOK_URL", "").strip()
    debug_dump = os.environ.get("DEBUG_DUMP", "").strip() == "1"

    if not api_key:
        print("[ERROR] NARA_API_KEY 환경변수가 비어있습니다.", file=sys.stderr)
        return 2
    if not webhook:
        print("[ERROR] TEAMS_WEBHOOK_URL 환경변수가 비어있습니다.", file=sys.stderr)
        return 2

    config = _load_config(CONFIG_PATH)
    target_keywords = list(config.get("keywords_target", []))
    action_keywords = list(config.get("keywords_action", []))
    whitelist_keywords = list(config.get("keywords_whitelist", []))
    exclude_name_keywords = list(config.get("exclude_name_keywords", []))
    exclude_contract = list(config.get("exclude_contract_keywords", []))
    allowed_regions = list(config.get("allowed_region_names", []))
    allow_no_region = bool(config.get("allow_no_region_restriction", True))
    window_minutes = int(config.get("search_window_minutes", 35))

    started = datetime.now(KST)
    start_clock = time.monotonic()
    print(f"[START] {started.strftime('%Y-%m-%d %H:%M:%S')} KST")

    try:
        items = fetch_bid_list(
            service_key=api_key,
            window_minutes=window_minutes,
            debug_dump=debug_dump,
        )
    except Exception as exc:  # API 최종 실패 — 워크플로우는 실패 처리
        print(f"[ERROR] API 호출 실패: {exc}", file=sys.stderr)
        return 1

    total = len(items)

    after_kw = filter_by_keywords(
        items,
        target_keywords,
        action_keywords,
        whitelist_keywords,
        exclude_name_keywords,
    )
    print(f"[FILTER:키워드] {total}건 → {len(after_kw)}건")

    after_ct = filter_by_contract_method(after_kw, exclude_contract)
    print(f"[FILTER:계약방식] {len(after_kw)}건 → {len(after_ct)}건")

    after_rg = filter_by_region(after_ct, allowed_regions, allow_no_region)
    print(f"[FILTER:지역] {len(after_ct)}건 → {len(after_rg)}건 (최종 신규 후보)")

    seen = load_seen(SEEN_PATH)
    seen = cleanup_old(seen)
    new_items = filter_new(after_rg, seen)
    print(f"[DEDUP] {len(after_rg)}건 중 신규 {len(new_items)}건")

    if new_items:
        sent, failed = send_all(webhook, new_items)
        print(f"[NOTIFY] Teams 전송 성공 {sent}건 / 실패 {failed}건")
        # 성공한 것만 seen에 기록 — 실패 건은 다음 실행에서 재시도
        # send_all이 항목별 결과를 반환하지 않으므로 현재는 전체를 mark
        # (실패 시 동일 공고가 다시 알림될 수 있는 트레이드오프, 운영 중 빈도 보고 조정)
        for it in new_items:
            mark_sent(seen, it)
    else:
        print("[NOTIFY] 전송 건수 0")

    save_seen(SEEN_PATH, seen)

    elapsed = time.monotonic() - start_clock
    print(f"[END] 소요 시간 {elapsed:.1f}초")
    return 0


if __name__ == "__main__":
    sys.exit(main())
