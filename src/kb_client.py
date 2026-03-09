"""
KB부동산 시세 + 전세가율 분석 모듈

PublicDataReader의 Kbland를 활용하여
- KB 아파트 시세 (호가 대용)
- 매매가격지수 추이
- 전세가율 계산 (갭투자 분석)
을 제공합니다.

별도 API 키 불필요.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    pass


def _get_kbland():
    """Lazy import to avoid hard dependency at module load time."""
    from PublicDataReader import Kbland
    return Kbland()


@dataclass
class GapAnalysis:
    """갭투자 분석 결과"""
    apt_name: str
    region: str
    trade_price: int          # 최근 매매 실거래가 (만원)
    jeonse_price: int         # 최근 전세 실거래가 (만원)
    gap: int                  # 갭 = 매매가 - 전세가 (만원)
    jeonse_ratio: float       # 전세가율 (%) = 전세/매매 × 100
    investment_grade: str     # 투자 등급 판정


def get_kb_price_index(
    region_code: str = "서울",
    period: int = 12,
) -> pd.DataFrame:
    """KB 아파트 매매가격지수 조회

    Args:
        region_code: 지역명 ("서울", "경기" 등)
        period: 조회 기간 (개월)

    Returns:
        월별 매매가격지수 DataFrame
    """
    api = _get_kbland()

    # 매매가격지수 조회
    df = api.get_market_trend(
        메뉴코드="01",           # 01: 매매
        월간주간구분코드="01",     # 01: 월간
        기간=str(period),
    )

    return df


def get_kb_jeonse_index(
    region_code: str = "서울",
    period: int = 12,
) -> pd.DataFrame:
    """KB 아파트 전세가격지수 조회"""
    api = _get_kbland()

    df = api.get_market_trend(
        메뉴코드="02",           # 02: 전세
        월간주간구분코드="01",
        기간=str(period),
    )

    return df


def calculate_jeonse_ratio(
    trade_price: int,
    jeonse_price: int,
) -> float:
    """전세가율 계산

    전세가율 = (전세가 / 매매가) × 100

    - 70% 이상: 갭이 작아 소액 투자 가능, 하지만 역전세 리스크
    - 60~70%: 적정 수준
    - 50~60%: 갭이 커서 자본금 많이 필요
    - 50% 미만: 투자 매력 낮음 (or 매매가가 과열)
    """
    if trade_price <= 0:
        return 0.0
    return round(jeonse_price / trade_price * 100, 1)


def grade_gap_investment(jeonse_ratio: float, gap: int) -> str:
    """갭투자 등급 판정

    Args:
        jeonse_ratio: 전세가율 (%)
        gap: 매매가 - 전세가 (만원)
    """
    if jeonse_ratio >= 80:
        return "⚠️ 위험 (역전세 리스크 높음)"
    elif jeonse_ratio >= 70:
        if gap <= 10000:
            return "🟢 소액갭투자 가능 (갭 1억 이하)"
        else:
            return "🟡 갭투자 적정 (전세가율 높음)"
    elif jeonse_ratio >= 60:
        if gap <= 20000:
            return "🟡 적정 (안정적 갭)"
        else:
            return "🟠 자본금 다소 필요"
    elif jeonse_ratio >= 50:
        return "🟠 갭 큼 (자본금 2억+ 필요)"
    else:
        return "🔴 갭투자 부적합 (매매가 과열 or 전세 수요 약)"


def analyze_gap(
    apt_name: str,
    region: str,
    trade_price: int,
    jeonse_price: int,
) -> GapAnalysis:
    """갭투자 종합 분석"""
    gap = trade_price - jeonse_price
    ratio = calculate_jeonse_ratio(trade_price, jeonse_price)
    grade = grade_gap_investment(ratio, gap)

    return GapAnalysis(
        apt_name=apt_name,
        region=region,
        trade_price=trade_price,
        jeonse_price=jeonse_price,
        gap=gap,
        jeonse_ratio=ratio,
        investment_grade=grade,
    )


async def analyze_area_gap(
    trade_data: list,  # list[AptTrade] from api_client
    rent_data: list,   # list[AptRent] - 전월세 데이터
    min_area: float = 59.0,
    max_area: float = 85.0,
) -> pd.DataFrame:
    """지역 내 아파트별 갭투자 분석 (매매 vs 전세 실거래가 매칭)

    같은 아파트 + 비슷한 면적의 최근 매매가와 전세가를 매칭하여
    전세가율과 갭을 계산합니다.
    """
    # 아파트별 최근 매매가 평균
    trade_by_apt: dict[str, list[int]] = {}
    for t in trade_data:
        if min_area <= t.area <= max_area:
            trade_by_apt.setdefault(t.apt_name, []).append(t.deal_amount)

    # 아파트별 최근 전세가 평균 (rent_data가 dict 형태라고 가정)
    rent_by_apt: dict[str, list[int]] = {}
    for r in rent_data:
        if hasattr(r, "area") and min_area <= r.area <= max_area:
            if hasattr(r, "deposit") and r.deposit > 0:
                rent_by_apt.setdefault(r.apt_name, []).append(r.deposit)

    # 매칭하여 갭 분석
    results = []
    for apt_name, trade_prices in trade_by_apt.items():
        if apt_name not in rent_by_apt:
            continue

        avg_trade = int(sum(trade_prices) / len(trade_prices))
        rent_prices = rent_by_apt[apt_name]
        avg_rent = int(sum(rent_prices) / len(rent_prices))

        analysis = analyze_gap(apt_name, "", avg_trade, avg_rent)
        results.append({
            "아파트": apt_name,
            "평균매매가(만원)": avg_trade,
            "평균전세가(만원)": avg_rent,
            "갭(만원)": analysis.gap,
            "전세가율(%)": analysis.jeonse_ratio,
            "투자등급": analysis.investment_grade,
            "매매건수": len(trade_prices),
            "전세건수": len(rent_prices),
        })

    df = pd.DataFrame(results)
    if not df.empty:
        df = df.sort_values("전세가율(%)", ascending=False)
    return df
