"""
급매 알림 모듈

관심 아파트를 등록하면 실거래가가 특정 조건을 만족할 때
알림을 보내주는 기능.

구현 방식:
1. 사용자가 관심 아파트 + 목표 가격 등록
2. 주기적으로 실거래가 API 조회 (cron 또는 스케줄러)
3. 목표 가격 이하 거래 발생 시 알림 발송
"""

import json
import os
import asyncio
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from .api_client import fetch_recent_trades, REGION_CODES


WATCHLIST_PATH = Path.home() / ".real-estate-agent" / "watchlist.json"


@dataclass
class WatchItem:
    """관심 매물"""
    apt_name: str              # 아파트명
    region: str                # 시군구 (예: "노원구")
    target_price: int          # 목표가 (만원)
    min_area: float = 59.0     # 최소 면적
    max_area: float = 85.0     # 최대 면적
    created_at: str = ""       # 등록일
    last_checked: str = ""     # 마지막 체크일
    alert_count: int = 0       # 알림 발생 횟수


def load_watchlist() -> list[WatchItem]:
    """관심 목록 로드"""
    if not WATCHLIST_PATH.exists():
        return []
    with open(WATCHLIST_PATH) as f:
        data = json.load(f)
    return [WatchItem(**item) for item in data]


def save_watchlist(items: list[WatchItem]) -> None:
    """관심 목록 저장"""
    WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHLIST_PATH, "w") as f:
        json.dump([asdict(item) for item in items], f, ensure_ascii=False, indent=2)


def add_watch(
    apt_name: str,
    region: str,
    target_price: int,
    min_area: float = 59.0,
    max_area: float = 85.0,
) -> WatchItem:
    """관심 아파트 등록"""
    items = load_watchlist()
    item = WatchItem(
        apt_name=apt_name,
        region=region,
        target_price=target_price,
        min_area=min_area,
        max_area=max_area,
        created_at=datetime.now().isoformat(),
    )
    items.append(item)
    save_watchlist(items)
    return item


def remove_watch(apt_name: str, region: str) -> bool:
    """관심 아파트 제거"""
    items = load_watchlist()
    before = len(items)
    items = [
        i for i in items
        if not (i.apt_name == apt_name and i.region == region)
    ]
    save_watchlist(items)
    return len(items) < before


@dataclass
class AlertResult:
    """알림 결과"""
    apt_name: str
    region: str
    target_price: int
    found_price: int
    area: float
    floor: int
    deal_date: str
    price_gap: int  # 목표가 - 실거래가 (양수면 급매)


async def check_alerts(months: int = 2) -> list[AlertResult]:
    """관심 목록 전체를 체크하여 급매 알림 생성

    Returns:
        목표가 이하로 거래된 매물 리스트
    """
    items = load_watchlist()
    alerts: list[AlertResult] = []

    for item in items:
        if item.region not in REGION_CODES:
            continue

        code = REGION_CODES[item.region]
        try:
            trades = await fetch_recent_trades(code, months)
        except Exception:
            continue

        # 해당 아파트 + 면적 범위 + 목표가 이하 필터
        matched = [
            t for t in trades
            if t.apt_name == item.apt_name
            and item.min_area <= t.area <= item.max_area
            and t.deal_amount <= item.target_price
        ]

        for t in matched:
            alerts.append(AlertResult(
                apt_name=t.apt_name,
                region=item.region,
                target_price=item.target_price,
                found_price=t.deal_amount,
                area=t.area,
                floor=t.floor,
                deal_date=f"{t.year}-{t.month:02d}-{t.day:02d}",
                price_gap=item.target_price - t.deal_amount,
            ))

        # 마지막 체크 시간 업데이트
        item.last_checked = datetime.now().isoformat()

    save_watchlist(items)
    return alerts


async def check_and_notify() -> str:
    """체크 후 알림 메시지 생성 (CLI/텔레그램/슬랙 등에서 사용)"""
    alerts = await check_alerts()

    if not alerts:
        return "새로운 급매 알림이 없습니다."

    lines = [f"🚨 급매 알림 {len(alerts)}건 발견!\n"]
    for a in alerts:
        lines.append(
            f"  📍 {a.region} {a.apt_name}\n"
            f"     거래가: {a.found_price:,}만 (목표가 대비 -{a.price_gap:,}만)\n"
            f"     {a.area}㎡ / {a.floor}층 / {a.deal_date}\n"
        )

    return "\n".join(lines)
