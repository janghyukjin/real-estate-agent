"""부천시(3구) + 화성시 재수집 (코드 수정 후)"""
import asyncio
import json
import os
from datetime import datetime, timedelta

from src.api_client import fetch_apt_trades, fetch_apt_rents

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# 화성시: API가 4개 코드로 분리, gu명은 "화성시"로 통일
FIX_CODES = {
    "화성시": ["41591", "41593", "41595", "41597"],
}


async def collect_fix(months: int = 75):
    api_key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not api_key:
        print("DATA_GO_KR_API_KEY 환경변수를 설정해주세요.")
        return

    now = datetime.now()
    ymds = [(now - timedelta(days=30 * i)).strftime("%Y%m") for i in range(months)]
    new_trades = []
    new_rents = []

    sem = asyncio.Semaphore(5)  # 429 방지를 위해 5로 줄임

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

    tasks = []
    for gu_name, codes in FIX_CODES.items():
        if isinstance(codes, str):
            codes = [codes]
        for code in codes:
            for ymd in ymds:
                tasks.append(fetch_one(gu_name, code, ymd))

    print(f"재수집: {sum(len(c) if isinstance(c, list) else 1 for c in FIX_CODES.values())}개 코드 × {months}개월 = {len(tasks)}건")
    results = await asyncio.gather(*tasks)

    for t_list, r_list in results:
        new_trades.extend(t_list)
        new_rents.extend(r_list)

    print(f"재수집 완료: 매매 {len(new_trades):,}건 / 전세 {len(new_rents):,}건")

    # 기존 데이터 로드 + 합치기
    with open(os.path.join(DATA_DIR, "raw_trades.json")) as f:
        existing_trades = json.load(f)
    with open(os.path.join(DATA_DIR, "raw_rents.json")) as f:
        existing_rents = json.load(f)

    # 기존 부천시/화성시 제거 (잘못된 코드로 0건이었을 것)
    fix_gus = set(FIX_CODES.keys())
    existing_trades = [t for t in existing_trades if t["gu"] not in fix_gus]
    existing_rents = [r for r in existing_rents if r["gu"] not in fix_gus]

    all_trades = existing_trades + new_trades
    all_rents = existing_rents + new_rents

    with open(os.path.join(DATA_DIR, "raw_trades.json"), "w") as f:
        json.dump(all_trades, f, ensure_ascii=False)
    with open(os.path.join(DATA_DIR, "raw_rents.json"), "w") as f:
        json.dump(all_rents, f, ensure_ascii=False)

    print(f"합산 저장: 매매 {len(all_trades):,}건 / 전세 {len(all_rents):,}건")


if __name__ == "__main__":
    asyncio.run(collect_fix())
