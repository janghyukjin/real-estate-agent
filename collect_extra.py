"""
추가 지역 수집 — 기존 raw 데이터에 합치기
"""
import asyncio
import json
import os
from datetime import datetime, timedelta

from src.api_client import REGION_CODES, SEOUL_TIERS, fetch_apt_trades, fetch_apt_rents

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")

# 추가할 지역 (SEOUL_TIERS에 등록된 경기 지역)
GYEONGGI_NAMES = [
    "과천시", "성남시분당구", "수원시영통구", "용인시수지구",         # 상급지
    "고양시일산동구", "광명시", "하남시", "안양시동안구",             # 중상급지
    "용인시기흥구", "구리시",
    "고양시일산서구", "고양시덕양구", "수원시장안구", "수원시권선구",  # 중하급지
    "수원시팔달구", "성남시수정구", "성남시중원구",
    "부천시원미구", "부천시소사구", "부천시오정구",
    "안양시만안구", "군포시", "의왕시", "남양주시", "의정부시",
    "평택시", "오산시", "광주시", "용인시처인구",                    # 하급지
    "시흥시", "김포시",
]
EXTRA_CODES = {name: REGION_CODES[name] for name in GYEONGGI_NAMES}
# 화성시: API가 4개 코드로 분리 → gu명 "화성시"로 통일
HWASEONG_CODES = ["41591", "41593", "41595", "41597"]


async def collect_extra(months: int = 75):
    api_key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not api_key:
        print("DATA_GO_KR_API_KEY 환경변수를 설정해주세요.")
        return

    now = datetime.now()
    ymds = [(now - timedelta(days=30 * i)).strftime("%Y%m") for i in range(months)]
    new_trades = []
    new_rents = []

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

    tasks = []
    for gu_name, code in EXTRA_CODES.items():
        for ymd in ymds:
            tasks.append(fetch_one(gu_name, code, ymd))
    # 화성시: 4개 API 코드, gu명 "화성시"로 통일
    for hcode in HWASEONG_CODES:
        for ymd in ymds:
            tasks.append(fetch_one("화성시", hcode, ymd))

    print(f"추가 수집: {len(EXTRA_CODES)}개 지역 + 화성시(4코드) × {months}개월 = {len(tasks)}건")
    results = await asyncio.gather(*tasks)

    for t_list, r_list in results:
        new_trades.extend(t_list)
        new_rents.extend(r_list)

    print(f"추가 수집 완료: 매매 {len(new_trades):,}건 / 전세 {len(new_rents):,}건")

    # 기존 데이터 로드 + 합치기
    with open(os.path.join(DATA_DIR, "raw_trades.json")) as f:
        existing_trades = json.load(f)
    with open(os.path.join(DATA_DIR, "raw_rents.json")) as f:
        existing_rents = json.load(f)

    # 기존 데이터에서 추가 지역 제거 (중복 방지)
    extra_gus = set(EXTRA_CODES.keys()) | {"화성시"}
    existing_trades = [t for t in existing_trades if t["gu"] not in extra_gus]
    existing_rents = [r for r in existing_rents if r["gu"] not in extra_gus]

    all_trades = existing_trades + new_trades
    all_rents = existing_rents + new_rents

    with open(os.path.join(DATA_DIR, "raw_trades.json"), "w") as f:
        json.dump(all_trades, f, ensure_ascii=False)
    with open(os.path.join(DATA_DIR, "raw_rents.json"), "w") as f:
        json.dump(all_rents, f, ensure_ascii=False)

    print(f"합산 저장: 매매 {len(all_trades):,}건 / 전세 {len(all_rents):,}건")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--months", type=int, default=75)
    args = parser.parse_args()
    asyncio.run(collect_extra(months=args.months))
