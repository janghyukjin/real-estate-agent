"""
재분석 스크립트 — API 호출 없이 저장된 raw 데이터로 analysis.json 재생성
"""
import json
import os
from datetime import datetime, timedelta

from src.api_client import SEOUL_TIERS
from src.building_ledger import get_household_count
from src.kb_client import calculate_jeonse_ratio

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def reanalyze():
    now = datetime.now()

    # raw 데이터 로드
    with open(os.path.join(DATA_DIR, "raw_trades.json")) as f:
        all_trades = json.load(f)
    with open(os.path.join(DATA_DIR, "raw_rents.json")) as f:
        all_rents = json.load(f)

    print(f"로드: 매매 {len(all_trades):,}건 / 전세 {len(all_rents):,}건")

    # 25~34평 필터
    apt_trades = {}
    for t in all_trades:
        if 59 <= t["area"] <= 112:
            key = (t["gu"], t["apt"])
            apt_trades.setdefault(key, []).append(t)

    apt_rents = {}
    for r in all_rents:
        if 59 <= r["area"] <= 112:
            key = (r["gu"], r["apt"])
            apt_rents.setdefault(key, []).append(r["deposit"])

    # 최근 3개월 (현재가 계산용)
    recent_ymds = set()
    for i in range(3):
        dt = now - timedelta(days=30 * i)
        recent_ymds.add((dt.year, dt.month))

    analysis = []
    for (gu, apt), trades in apt_trades.items():
        all_prices = [t["price"] for t in trades]
        if len(all_prices) < 2:
            continue

        # 현재가 = 최근 3개월
        recent_prices = [t["price"] for t in trades if (t["year"], t["month"]) in recent_ymds]
        if not recent_prices:
            continue
        avg_price = int(sum(recent_prices) / len(recent_prices))
        recent_high = max(recent_prices)  # 최근 3개월 최고가

        hhld = get_household_count(apt)
        if not hhld or hhld < 300:
            continue

        # 전세가율
        rent_prices = apt_rents.get((gu, apt), [])
        if not rent_prices:
            continue
        avg_rent = int(sum(rent_prices) / len(rent_prices))
        if avg_rent <= 0:
            continue
        ratio = calculate_jeonse_ratio(avg_price, avg_rent)
        gap = avg_price - avg_rent

        # 전고점/전저점 (전체 기간)
        peak = max(all_prices)
        trough = min(all_prices)
        peak_trades = [t for t in trades if t["price"] == peak]
        trough_trades = [t for t in trades if t["price"] == trough]
        peak_ym = f"{peak_trades[0]['year']}-{peak_trades[0]['month']:02d}"
        trough_ym = f"{trough_trades[0]['year']}-{trough_trades[0]['month']:02d}"

        # 현재 최고점 판단: 최근 최고가 >= 전고점이면 "현재 최고점"
        is_at_peak = recent_high >= peak

        if is_at_peak:
            diff_peak = round((recent_high - peak) / peak * 100, 1) if peak > 0 else 0
        else:
            diff_peak = round((avg_price - peak) / peak * 100, 1) if peak > 0 else 0
        diff_trough = round((avg_price - trough) / trough * 100, 1) if trough > 0 else 0

        # 시기별 분석: 상승기(2020~2022) 고점 vs 하락기(2023~2024) 저점
        pre_crash = [t for t in trades if t["year"] <= 2022]
        crash_period = [t for t in trades if 2023 <= t["year"] <= 2024]
        recovery = [t for t in trades if t["year"] >= 2025]

        pre_crash_peak = max([t["price"] for t in pre_crash]) if pre_crash else 0
        pre_crash_ym = ""
        if pre_crash and pre_crash_peak > 0:
            pt = [t for t in pre_crash if t["price"] == pre_crash_peak][0]
            pre_crash_ym = f"{pt['year']}-{pt['month']:02d}"

        crash_trough = min([t["price"] for t in crash_period]) if crash_period else 0
        crash_trough_ym = ""
        if crash_period and crash_trough > 0:
            tt = [t for t in crash_period if t["price"] == crash_trough][0]
            crash_trough_ym = f"{tt['year']}-{tt['month']:02d}"

        # 회복률: (현재 - 하락기저점) / (상승기고점 - 하락기저점)
        if pre_crash_peak > 0 and crash_trough > 0 and pre_crash_peak > crash_trough:
            recovery_rate = round((avg_price - crash_trough) / (pre_crash_peak - crash_trough) * 100, 1)
        else:
            recovery_rate = 0

        # 월별 가격 추이 (그래프용)
        monthly_prices = {}
        for t in trades:
            ym = f"{t['year']}-{t['month']:02d}"
            monthly_prices.setdefault(ym, []).append(t["price"])
        price_history = {ym: int(sum(ps) / len(ps)) for ym, ps in sorted(monthly_prices.items())}

        tier = SEOUL_TIERS.get(gu, "")

        analysis.append({
            "apt": apt, "gu": gu, "tier": tier, "hhld": hhld,
            "avg_price": avg_price, "recent_high": recent_high,
            "is_at_peak": is_at_peak,
            "count": len(recent_prices),
            "count_total": len(all_prices),
            "avg_rent": avg_rent, "ratio": ratio, "gap": gap,
            "peak": peak, "peak_ym": peak_ym,
            "pre_crash_peak": pre_crash_peak, "pre_crash_ym": pre_crash_ym,
            "crash_trough": crash_trough, "crash_trough_ym": crash_trough_ym,
            "recovery_rate": recovery_rate,
            "trough": trough, "trough_ym": trough_ym,
            "diff_peak": diff_peak, "diff_trough": diff_trough,
            "price_history": price_history,
        })

    with open(os.path.join(DATA_DIR, "analysis.json"), "w") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    print(f"분석 완료: {len(analysis)}개 아파트")

    # 검증
    test = [a for a in analysis if "태영" in a["apt"]]
    for t in test:
        print(f"  {t['apt']} ({t['gu']}): 현재가 {t['avg_price']/10000:.1f}억 (최근{t['count']}건) / 고점 {t['peak']/10000:.1f}억 ({t['peak_ym']}) / 저점 {t['trough']/10000:.1f}억 ({t['trough_ym']})")

    meta = {
        "collected_at": now.strftime("%Y-%m-%d %H:%M"),
        "trade_count": len(all_trades),
        "rent_count": len(all_rents),
        "apt_count": len(analysis),
        "reanalyzed": True,
    }
    with open(os.path.join(DATA_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    reanalyze()
