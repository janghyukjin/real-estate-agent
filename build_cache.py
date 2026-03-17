"""
건축물대장 API로 세대수 캐시 일괄 구축

실거래 데이터의 모든 (구, 동) 조합에 대해 건축물대장 총괄표제부를 조회하고,
"동+아파트명": 세대수 형태로 캐시에 저장.
"""
import asyncio
import json
import os
from datetime import datetime

import httpx

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_PATH = os.path.join(DATA_DIR, "apt_cache.json")

BUILDING_RECAP_URL = (
    "http://apis.data.go.kr/1613000/"
    "BldRgstHubService/getBrRecapTitleInfo"
)


def load_bjdong_codes() -> dict[str, dict[str, str]]:
    with open(os.path.join(DATA_DIR, "bjdong_codes.json")) as f:
        return json.load(f)


def load_trade_gu_dongs() -> set[tuple[str, str, str]]:
    """실거래 데이터에서 (sigungu_cd, dong_name, apt_name) 유니크 목록"""
    from src.api_client import REGION_CODES
    with open(os.path.join(DATA_DIR, "raw_trades.json")) as f:
        trades = json.load(f)

    bjdong_map = load_bjdong_codes()
    gu_dongs = set()  # (sigungu_cd, dong_name)
    for t in trades:
        if 59 <= t["area"] <= 112 and t.get("dong"):
            sigungu_cd = REGION_CODES.get(t["gu"])
            if sigungu_cd:
                dong_codes = bjdong_map.get(sigungu_cd, {})
                if t["dong"] in dong_codes:
                    gu_dongs.add((sigungu_cd, t["dong"]))
    return gu_dongs


async def fetch_building_recap(
    sigungu_cd: str, bjdong_cd: str, api_key: str
) -> list[dict]:
    """건축물대장 총괄표제부 조회 → [{bld_name, household_count}, ...]"""
    params = {
        "serviceKey": api_key,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "numOfRows": "500",
        "pageNo": "1",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(BUILDING_RECAP_URL, params=params)
        resp.raise_for_status()

    import xml.etree.ElementTree as ET
    root = ET.fromstring(resp.text)
    results = []
    for item in root.findall(".//item"):
        try:
            name = (item.findtext("bldNm") or "").strip()
            hhld = int(item.findtext("hhldCnt") or item.findtext("hoCnt") or "0")
            if not name or hhld <= 0:
                continue
            # 사용승인일 "20050315" → 준공연도 2005
            use_apr = (item.findtext("useAprDay") or "").strip()
            build_year = int(use_apr[:4]) if len(use_apr) >= 4 and use_apr[:4].isdigit() else 0
            results.append({"bld_name": name, "household_count": hhld, "build_year": build_year})
        except (ValueError, TypeError):
            continue
    return results


async def build_full_cache(max_concurrent: int = 5):
    api_key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not api_key:
        print("DATA_GO_KR_API_KEY 환경변수를 설정해주세요.")
        return

    bjdong_map = load_bjdong_codes()
    gu_dongs = load_trade_gu_dongs()

    # 기존 캐시 로드 (구형 int → 신형 dict 마이그레이션)
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH) as f:
            raw = json.load(f)
        cache = {}
        for k, v in raw.items():
            if isinstance(v, int):
                cache[k] = {"hhld": v, "build_year": 0}
            elif isinstance(v, dict):
                cache[k] = v
    else:
        cache = {}

    print(f"기존 캐시: {len(cache)}개")
    print(f"조회 대상: {len(gu_dongs)}개 (구, 동) 조합")

    sem = asyncio.Semaphore(max_concurrent)
    added = 0
    errors = 0
    processed = 0

    async def fetch_one(sigungu_cd: str, dong_name: str):
        nonlocal added, errors, processed
        bjdong_cd = bjdong_map.get(sigungu_cd, {}).get(dong_name)
        if not bjdong_cd:
            return

        async with sem:
            try:
                results = await fetch_building_recap(sigungu_cd, bjdong_cd, api_key)
                for r in results:
                    info = {"hhld": r["household_count"], "build_year": r["build_year"]}
                    # "동+아파트명" 키로 저장
                    dong_apt_key = dong_name + r["bld_name"]
                    if dong_apt_key not in cache:
                        cache[dong_apt_key] = info
                        added += 1
                    else:
                        # build_year 없으면 업데이트
                        if r["build_year"] and not cache[dong_apt_key].get("build_year"):
                            cache[dong_apt_key]["build_year"] = r["build_year"]
                    # 아파트명만으로도 저장
                    if r["bld_name"] not in cache:
                        cache[r["bld_name"]] = info
                    else:
                        if r["build_year"] and not cache[r["bld_name"]].get("build_year"):
                            cache[r["bld_name"]]["build_year"] = r["build_year"]
                processed += 1
                if processed % 20 == 0:
                    print(f"  진행: {processed}/{len(gu_dongs)} ({added}개 추가)")
            except Exception as e:
                errors += 1
                if errors <= 5:
                    print(f"  에러: {sigungu_cd} {dong_name} - {e}")

    tasks = [fetch_one(s, d) for s, d in sorted(gu_dongs)]
    await asyncio.gather(*tasks)

    # 저장
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, ensure_ascii=False)

    print(f"\n완료: {added}개 추가 (에러 {errors}건)")
    print(f"캐시 총: {len(cache)}개")
    print(f"저장: {CACHE_PATH}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--concurrent", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(build_full_cache(max_concurrent=args.concurrent))
