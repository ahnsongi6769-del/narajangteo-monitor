"""seen.json 기반 중복 방지.

- 키: f"{bidNtceNo}-{bidNtceOrd}"
- 값: 발송 시각 (ISO 8601, KST)
- 매 실행마다 30일 이상 된 항목 정리
- 파일 없거나 손상 시 빈 dict로 시작 (안전 fallback)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
RETENTION_DAYS = 30


def make_key(bid_ntce_no, bid_ntce_ord) -> str:
    """f'{공고번호}-{차수}' 형식의 dedup 키."""
    no = "" if bid_ntce_no is None else str(bid_ntce_no)
    ord_ = "" if bid_ntce_ord is None else str(bid_ntce_ord)
    return f"{no}-{ord_}"


def load_seen(path: Path) -> dict[str, str]:
    """seen.json 로드. 없거나 망가졌으면 빈 dict."""
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        logger.warning("[DEDUP] seen.json 형식 오류 (dict 아님) — 빈 dict로 초기화")
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[DEDUP] seen.json 로드 실패 (%s) — 빈 dict로 초기화", exc)
        return {}


def save_seen(path: Path, seen: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(seen, f, ensure_ascii=False, indent=2, sort_keys=True)
        f.write("\n")


def cleanup_old(
    seen: dict[str, str],
    retention_days: int = RETENTION_DAYS,
) -> dict[str, str]:
    """retention_days보다 오래된 항목 제거. 타임스탬프 파싱 실패는 보수적으로 보존."""
    cutoff = datetime.now(KST) - timedelta(days=retention_days)
    fresh: dict[str, str] = {}
    for key, ts_str in seen.items():
        try:
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=KST)
            if ts >= cutoff:
                fresh[key] = ts_str
        except (ValueError, TypeError):
            fresh[key] = ts_str
    removed = len(seen) - len(fresh)
    if removed:
        logger.info("[DEDUP] %d일 이상 된 항목 %d건 정리", retention_days, removed)
    return fresh


def filter_new(items: list[dict], seen: dict[str, str]) -> list[dict]:
    """seen에 없는 항목만 반환."""
    return [
        it for it in items
        if make_key(it.get("bidNtceNo"), it.get("bidNtceOrd")) not in seen
    ]


def mark_sent(seen: dict[str, str], item: dict) -> None:
    """발송 완료 표시 — KST ISO 8601 타임스탬프."""
    key = make_key(item.get("bidNtceNo"), item.get("bidNtceOrd"))
    seen[key] = datetime.now(KST).isoformat(timespec="seconds")
