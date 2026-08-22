"""
최근 N개월 증분 갱신 — raw_trades/raw_rents에서 해당 월 슬라이스만 교체
(실거래 신고 30일 지연분 반영을 위해 기본 4개월 재수집 —
 3개월로 돌리면 지연신고분이 누락된다)

사용: .venv/bin/python refresh_recent.py [--months 4]
이후 reanalyze.py 실행으로 analysis.json 재생성.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta

from src.api_client import REGION_CODES, fetch_apt_trades, fetch_apt_rents

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
HWASEONG_CODES = ["41591", "41593", "41595", "41597"]


async def refresh(months: int = 3):
    api_key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not api_key:
        print("DATA_GO_KR_API_KEY 환경변수를 설정해주세요.")
        return False

    with open(os.path.join(DATA_DIR, "raw_trades.json")) as f:
        existing_trades = json.load(f)
    with open(os.path.join(DATA_DIR, "raw_rents.json")) as f:
        existing_rents = json.load(f)

    # 기존 raw에 있는 지역만 그대로 갱신 (화성시는 4개 코드)
    gus = sorted({t["gu"] for t in existing_trades})
    codes = []
    for gu in gus:
        if gu == "화성시":
            codes.extend(("화성시", c) for c in HWASEONG_CODES)
        elif gu in REGION_CODES:
            codes.append((gu, REGION_CODES[gu]))
        else:
            print(f"  ⚠️ REGION_CODES에 없는 지역 스킵: {gu}")

    now = datetime.now()
    ymds = [(now - timedelta(days=30 * i)).strftime("%Y%m") for i in range(months)]
    refresh_ym = {(int(y[:4]), int(y[4:])) for y in ymds}

    sem = asyncio.Semaphore(10)
    failures = []

    async def fetch_one(gu_name, code, ymd):
        async with sem:
            t_list, r_list = [], []
            try:
                for t in await fetch_apt_trades(code, ymd, api_key):
                    t_list.append({
                        "apt": t.apt_name, "price": t.deal_amount,
                        "area": t.area, "gu": gu_name, "dong": t.dong,
                        "year": t.year, "month": t.month, "day": t.day,
                        "floor": t.floor, "deal_type": t.deal_type,
                        "build_year": t.build_year,
                    })
            except Exception as e:
                print(f"  매매 실패: {gu_name} {ymd} - {e}")
                failures.append(("매매", gu_name, ymd, str(e)))
            try:
                for r in await fetch_apt_rents(code, ymd, api_key):
                    if r.monthly_rent == 0 and r.deposit > 0:
                        r_list.append({
                            "apt": r.apt_name, "deposit": r.deposit,
                            "area": r.area, "gu": gu_name,
                            "year": r.year, "month": r.month,
                        })
            except Exception as e:
                print(f"  전세 실패: {gu_name} {ymd} - {e}")
                failures.append(("전세", gu_name, ymd, str(e)))
            return t_list, r_list

    tasks = [fetch_one(gu, code, ymd) for gu, code in codes for ymd in ymds]
    print(f"갱신 수집: {len(codes)}개 코드 × {len(ymds)}개월({ymds[-1]}~{ymds[0]}) = {len(tasks)}건")
    results = await asyncio.gather(*tasks)

    new_trades, new_rents = [], []
    for t_list, r_list in results:
        new_trades.extend(t_list)
        new_rents.extend(r_list)
    print(f"수집 완료: 매매 {len(new_trades):,}건 / 전세 {len(new_rents):,}건")

    # 갱신 대상 월 슬라이스 제거 후 새 데이터로 교체
    kept_t = [t for t in existing_trades if (t["year"], t["month"]) not in refresh_ym]
    kept_r = [r for r in existing_rents if (r["year"], r["month"]) not in refresh_ym]
    dropped_t = len(existing_trades) - len(kept_t)
    dropped_r = len(existing_rents) - len(kept_r)

    # 안전 가드 — API 일시 장애 시 최근 N개월이 통째로 날아가는 것을 막는다.
    # fetch_one이 예외를 삼키고 빈 리스트를 반환하므로, 여기서 잡지 않으면
    # "수집 0건"이 그대로 슬라이스 삭제로 이어진다 (2026-06-16 CI 사고와 동일 구조).
    total_tasks = len(tasks) * 2  # 매매 + 전세
    fail_ratio = len(failures) / total_tasks if total_tasks else 0.0
    problems = []
    if fail_ratio > 0.10:
        problems.append(
            f"수집 실패율 {fail_ratio:.1%} ({len(failures)}/{total_tasks}건) — 임계치 10% 초과"
        )
    if dropped_t > 0 and len(new_trades) < dropped_t * 0.5:
        problems.append(
            f"매매 수집량 급감: 기존 {dropped_t:,}건 → 신규 {len(new_trades):,}건 (50% 미달)"
        )
    if dropped_r > 0 and len(new_rents) < dropped_r * 0.5:
        problems.append(
            f"전세 수집량 급감: 기존 {dropped_r:,}건 → 신규 {len(new_rents):,}건 (50% 미달)"
        )
    if problems:
        print("\n❌ 갱신 중단 — raw 데이터를 그대로 보존합니다:")
        for msg in problems:
            print(f"  - {msg}")
        return False

    all_trades = kept_t + new_trades
    all_rents = kept_r + new_rents

    with open(os.path.join(DATA_DIR, "raw_trades.json"), "w") as f:
        json.dump(all_trades, f, ensure_ascii=False)
    with open(os.path.join(DATA_DIR, "raw_rents.json"), "w") as f:
        json.dump(all_rents, f, ensure_ascii=False)

    print(f"교체: 매매 {dropped_t:,}→{len(new_trades):,}건 / 전세 {dropped_r:,}→{len(new_rents):,}건")
    print(f"합산 저장: 매매 {len(all_trades):,}건 / 전세 {len(all_rents):,}건")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=4)
    args = parser.parse_args()
    ok = asyncio.run(refresh(months=args.months))
    sys.exit(0 if ok else 1)
