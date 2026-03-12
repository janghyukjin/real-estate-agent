"""
데이터 수집 스크립트 — 하루 1번 실행
서울 25개구 + 경기 주요 시군구 매매+전세 실거래가 수집 → data/analysis.json 저장
"""
import asyncio
import json
import os
from datetime import datetime, timedelta

from src.api_client import (
    REGION_CODES, SEOUL_TIERS, HWASEONG_CODES,
    fetch_apt_trades, fetch_apt_rents,
)
from src.building_ledger import get_household_count
from src.kb_client import calculate_jeonse_ratio

# SEOUL_TIERS에 등록된 모든 지역 (서울 + 경기)
ALL_GU_CODES = {k: v for k, v in REGION_CODES.items() if k in SEOUL_TIERS}
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


async def collect_all(months: int = 3):
    api_key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not api_key:
        print("DATA_GO_KR_API_KEY 환경변수를 설정해주세요.")
        return

    now = datetime.now()
    ymds = [(now - timedelta(days=30 * i)).strftime("%Y%m") for i in range(months)]
    all_trades = []
    all_rents = []

    sem = asyncio.Semaphore(10)

    async def fetch_one(gu_name, code, ymd):
        async with sem:
            t_list, r_list = [], []
            try:
                trades = await fetch_apt_trades(code, ymd, api_key)
                for t in trades:
                    t_list.append({
                        "apt": t.apt_name, "price": t.deal_amount,
                        "area": t.area, "gu": gu_name, "dong": t.dong,
                        "year": t.year, "month": t.month, "day": t.day,
                        "floor": t.floor, "deal_type": t.deal_type,
                    })
            except Exception as e:
                print(f"  매매 실패: {gu_name} {ymd} - {e}")
            try:
                rents = await fetch_apt_rents(code, ymd, api_key)
                for r in rents:
                    if r.monthly_rent == 0 and r.deposit > 0:
                        r_list.append({
                            "apt": r.apt_name, "deposit": r.deposit,
                            "area": r.area, "gu": gu_name,
                        })
            except Exception as e:
                print(f"  전세 실패: {gu_name} {ymd} - {e}")
            return t_list, r_list

    # 병렬 수집
    tasks = []
    for gu_name, code in ALL_GU_CODES.items():
        if gu_name == "화성시":
            # 화성시는 4개 API 코드로 분리 → 모두 gu="화성시"로 통일
            for hcode in HWASEONG_CODES:
                for ymd in ymds:
                    tasks.append(fetch_one("화성시", hcode, ymd))
        else:
            for ymd in ymds:
                tasks.append(fetch_one(gu_name, code, ymd))

    print(f"수집 시작: {len(ALL_GU_CODES)}개 지역 × {months}개월 = {len(tasks)}건 (병렬 10개)")
    results = await asyncio.gather(*tasks)

    for t_list, r_list in results:
        all_trades.extend(t_list)
        all_rents.extend(r_list)

    print(f"수집 완료: 매매 {len(all_trades):,}건 / 전세 {len(all_rents):,}건")

    # 분석: 25~34평(59~112㎡) 아파트별 집계
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

    # 최근 3개월 기준 연월 (현재가 계산용)
    recent_ymds = set()
    for i in range(3):
        dt = now - timedelta(days=30 * i)
        recent_ymds.add((dt.year, dt.month))

    # 최근 6개월 전세 기준
    recent_rent_ymds = set()
    for i in range(6):
        dt = now - timedelta(days=30 * i)
        recent_rent_ymds.add((dt.year, dt.month))

    analysis = []
    for (gu, apt), trades in apt_trades.items():
        all_prices = [t["price"] for t in trades]
        if len(all_prices) < 2:
            continue

        # 현재가 = 최근 3개월 거래 평균
        recent_prices = [t["price"] for t in trades if (t["year"], t["month"]) in recent_ymds]
        if not recent_prices:
            continue  # 최근 거래 없으면 스킵
        avg_price = int(sum(recent_prices) / len(recent_prices))

        hhld = get_household_count(apt)
        if not hhld or hhld < 300:
            continue

        # 전세가율 (최근 6개월 전세 기준)
        all_rent_prices = apt_rents.get((gu, apt), [])
        if not all_rent_prices:
            continue
        # 전세 데이터에는 연월 정보가 없으므로 전체 평균 사용
        avg_rent = int(sum(all_rent_prices) / len(all_rent_prices))
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
        diff_peak = round((avg_price - peak) / peak * 100, 1) if peak > 0 else 0
        diff_trough = round((avg_price - trough) / trough * 100, 1) if trough > 0 else 0

        tier = SEOUL_TIERS.get(gu, "")

        analysis.append({
            "apt": apt, "gu": gu, "tier": tier, "hhld": hhld,
            "avg_price": avg_price, "count": len(recent_prices),
            "count_total": len(all_prices),
            "avg_rent": avg_rent, "ratio": ratio, "gap": gap,
            "peak": peak, "peak_ym": peak_ym,
            "trough": trough, "trough_ym": trough_ym,
            "diff_peak": diff_peak, "diff_trough": diff_trough,
        })

    # raw 데이터 저장 (재분석용)
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "raw_trades.json"), "w") as f:
        json.dump(all_trades, f, ensure_ascii=False)
    with open(os.path.join(DATA_DIR, "raw_rents.json"), "w") as f:
        json.dump(all_rents, f, ensure_ascii=False)
    print(f"raw 데이터 저장 완료")

    # 분석 저장
    out_path = os.path.join(DATA_DIR, "analysis.json")
    with open(out_path, "w") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    print(f"분석 저장: {len(analysis)}개 아파트 → {out_path}")
    print(f"수집 시각: {now.strftime('%Y-%m-%d %H:%M')}")

    # 메타 정보 저장
    meta = {
        "collected_at": now.strftime("%Y-%m-%d %H:%M"),
        "trade_count": len(all_trades),
        "rent_count": len(all_rents),
        "apt_count": len(analysis),
        "months": months,
    }
    with open(os.path.join(DATA_DIR, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=3, help="수집 개월 수 (기본 3)")
    args = parser.parse_args()
    asyncio.run(collect_all(months=args.months))
