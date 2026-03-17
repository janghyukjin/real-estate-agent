"""
재분석 스크립트 — API 호출 없이 저장된 raw 데이터로 analysis.json 재생성
"""
import json
import os
from datetime import datetime, timedelta

from src.api_client import SEOUL_TIERS
from src.building_ledger import get_household_count, get_build_year
from src.kb_client import calculate_jeonse_ratio

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def get_area_type(area: float) -> str:
    """전용면적 → 그룹 키 (소수점 버림, 예: 84㎡)"""
    return f"{int(area)}㎡"


def reanalyze():
    now = datetime.now()

    # raw 데이터 로드
    with open(os.path.join(DATA_DIR, "raw_trades.json")) as f:
        all_trades = json.load(f)
    with open(os.path.join(DATA_DIR, "raw_rents.json")) as f:
        all_rents = json.load(f)

    print(f"로드: 매매 {len(all_trades):,}건 / 전세 {len(all_rents):,}건")

    # 직거래 제외 (deal_type 필드가 있는 경우만)
    has_deal_type = any("deal_type" in t for t in all_trades[:100])
    if has_deal_type:
        before = len(all_trades)
        all_trades = [t for t in all_trades if t.get("deal_type", "") != "직거래"]
        print(f"직거래 제외: {before:,} → {len(all_trades):,}건 ({before - len(all_trades):,}건 제외)")

    # 1층 제외 (층 데이터 있는 경우, 평균가 왜곡 방지)
    has_floor = any("floor" in t for t in all_trades[:100])
    if has_floor:
        before = len(all_trades)
        all_trades = [t for t in all_trades if t.get("floor", 0) != 1]
        print(f"1층 제외: {before:,} → {len(all_trades):,}건 ({before - len(all_trades):,}건 제외)")

    # 25~34평 필터 (평형별 분리)
    apt_trades = {}
    for t in all_trades:
        if 59 <= t["area"] <= 112:
            area_type = get_area_type(t["area"])
            key = (t["gu"], t["apt"], t.get("dong", ""), area_type)
            apt_trades.setdefault(key, []).append(t)

    apt_rents = {}
    for r in all_rents:
        if 59 <= r["area"] <= 112:
            area_type = get_area_type(r["area"])
            key = (r["gu"], r["apt"], area_type)
            apt_rents.setdefault(key, []).append(r["deposit"])

    # 최근 3개월 (현재가 계산용)
    recent_ymds = set()
    for i in range(3):
        dt = now - timedelta(days=30 * i)
        recent_ymds.add((dt.year, dt.month))

    analysis = []
    for (gu, apt, dong, area_type), trades in apt_trades.items():
        all_prices = [t["price"] for t in trades]
        if len(all_prices) < 2:
            continue

        # 최근 3개월 거래
        recent_trades = [t for t in trades if (t["year"], t["month"]) in recent_ymds]
        if not recent_trades:
            continue
        recent_prices = [t["price"] for t in recent_trades]
        avg_price = int(sum(recent_prices) / len(recent_prices))
        recent_high = max(recent_prices)

        # 가장 최근 거래가 (날짜순 정렬)
        recent_trades_sorted = sorted(
            recent_trades,
            key=lambda t: (t["year"], t["month"], t.get("day", 0)),
            reverse=True,
        )
        latest_price = recent_trades_sorted[0]["price"]
        latest_ym = f"{recent_trades_sorted[0]['year']}-{recent_trades_sorted[0]['month']:02d}"

        hhld = get_household_count(apt, dong)
        if not hhld or hhld < 300:
            continue
        build_year = get_build_year(apt, dong) or 0

        # 전세가율
        rent_prices = apt_rents.get((gu, apt, area_type), [])
        if not rent_prices:
            continue
        avg_rent = int(sum(rent_prices) / len(rent_prices))
        if avg_rent <= 0:
            continue
        ratio = calculate_jeonse_ratio(avg_price, avg_rent)
        if ratio >= 100:
            ratio = 99.9  # 역전세(전세>매매) cap 처리
        gap = max(avg_price - avg_rent, 0)  # 역전세 시 갭 0으로

        # 전고점/전저점 (전체 기간)
        peak = max(all_prices)
        trough = min(all_prices)
        peak_trades = [t for t in trades if t["price"] == peak]
        trough_trades = [t for t in trades if t["price"] == trough]
        peak_ym = f"{peak_trades[0]['year']}-{peak_trades[0]['month']:02d}"
        trough_ym = f"{trough_trades[0]['year']}-{trough_trades[0]['month']:02d}"

        # 현재 최고점 판단: 최근 거래가 >= 전고점이면 "현재 최고점"
        is_at_peak = latest_price >= peak

        diff_peak = round((latest_price - peak) / peak * 100, 1) if peak > 0 else 0
        diff_trough = round((latest_price - trough) / trough * 100, 1) if trough > 0 else 0

        # 시기별 분석: 상승기(2020~2022) 고점 vs 하락기(2023~2024) 저점
        pre_crash = [t for t in trades if t["year"] <= 2022]
        crash_period = [t for t in trades if 2023 <= t["year"] <= 2024]

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

        # 회복률: 최근 거래가 / 상승기고점(~2022) × 100%
        # 2021~2022년 거래가 없으면 고점이 의미없음 (데이터 희소) → 0 처리
        has_peak_era = any(2021 <= t["year"] <= 2022 for t in trades)
        if pre_crash_peak > 0 and has_peak_era:
            recovery_rate = round(latest_price / pre_crash_peak * 100, 1)
        else:
            recovery_rate = 0

        # 10.15 토허제 직전 가격 (2024년 7~9월 우선 → 4~9월 → 토허제 전 마지막 거래)
        pre_policy = [t for t in trades if t["year"] == 2024 and 7 <= t["month"] <= 9]
        if not pre_policy:
            pre_policy = [t for t in trades if t["year"] == 2024 and 4 <= t["month"] <= 9]
        if not pre_policy:
            # 토허제(2024.10.15) 이전 마지막 거래
            before_policy = [t for t in trades if (t["year"], t["month"]) < (2024, 10)]
            if before_policy:
                before_policy.sort(key=lambda t: (t["year"], t["month"], t.get("day", 0)), reverse=True)
                pre_policy = [before_policy[0]]
        policy_avg = int(sum(t["price"] for t in pre_policy) / len(pre_policy)) if pre_policy else 0

        # 월별 가격 추이 (그래프용)
        monthly_prices = {}
        for t in trades:
            ym = f"{t['year']}-{t['month']:02d}"
            monthly_prices.setdefault(ym, []).append(t["price"])
        price_history = {ym: int(sum(ps) / len(ps)) for ym, ps in sorted(monthly_prices.items())}

        tier = SEOUL_TIERS.get(gu, "")

        analysis.append({
            "apt": apt, "gu": gu, "dong": trades[0].get("dong", ""), "tier": tier,
            "hhld": hhld, "build_year": build_year, "area_type": area_type,
            "avg_price": avg_price, "recent_high": recent_high,
            "latest_price": latest_price, "latest_ym": latest_ym,
            "is_at_peak": is_at_peak,
            "count": len(recent_prices),
            "count_total": len(all_prices),
            "avg_rent": avg_rent, "ratio": ratio, "gap": gap,
            "policy_avg": policy_avg,
            "peak": peak, "peak_ym": peak_ym,
            "pre_crash_peak": pre_crash_peak, "pre_crash_ym": pre_crash_ym,
            "crash_trough": crash_trough, "crash_trough_ym": crash_trough_ym,
            "recovery_rate": recovery_rate,
            "trough": trough, "trough_ym": trough_ym,
            "diff_peak": diff_peak, "diff_trough": diff_trough,
            "price_history": price_history,
        })

    # 동명이인 해소: 같은 (gu, apt, area_type)인데 dong이 다른 경우 이름에 동 표기
    from collections import defaultdict
    key_groups = defaultdict(list)
    for i, a in enumerate(analysis):
        key_groups[(a["gu"], a["apt"], a["area_type"])].append(i)
    disambiguated = 0
    for key, indices in key_groups.items():
        if len(indices) > 1:
            dongs = set(analysis[i]["dong"] for i in indices)
            if len(dongs) > 1:  # 실제로 dong이 다를 때만
                for i in indices:
                    dong = analysis[i]["dong"]
                    if dong:
                        analysis[i]["apt"] = f"{analysis[i]['apt']}({dong})"
                        disambiguated += 1
    if disambiguated:
        print(f"동명이인 해소: {disambiguated}개 아파트명에 동 표기 추가")

    with open(os.path.join(DATA_DIR, "analysis.json"), "w") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    print(f"분석 완료: {len(analysis)}개 아파트")

    # 검증
    test = [a for a in analysis if "신동아" in a["apt"] and "송파" in a["gu"]]
    if not test:
        test = [a for a in analysis if "태영" in a["apt"]]
    for t in test:
        print(f"  {t['apt']} ({t['gu']}): 최근거래가 {t['latest_price']/10000:.1f}억 / 평균 {t['avg_price']/10000:.1f}억 / 최고 {t['recent_high']/10000:.1f}억 / 22년고점 {t['pre_crash_peak']/10000:.1f}억 / 회복률 {t['recovery_rate']}%")

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
