"""
캐시 재구축 스크립트 — 누락 아파트 세대수를 건축물대장 API로 추가

1. raw_trades.json에서 최근3개월 거래 5건+ 인데 캐시 미매칭 아파트 추출
2. 해당 동의 건축물대장을 API 조회하여 캐시에 추가
3. 읍/면+리 → 읍/면 매핑, 통합시군구코드 매핑 처리
"""
import asyncio
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta

import httpx

sys.path.insert(0, os.path.dirname(__file__))

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
CACHE_PATH = os.path.join(DATA_DIR, "apt_cache.json")

BUILDING_RECAP_URL = (
    "http://apis.data.go.kr/1613000/"
    "BldRgstHubService/getBrRecapTitleInfo"
)

# 구 시군구코드 → 통합코드 매핑 (행정구역 통합된 지역)
MERGED_SIGUNGU = {
    "41192": "41190",  # 부천시원미구 → 부천시
    "41194": "41190",  # 부천시소사구 → 부천시
    "41196": "41190",  # 부천시오정구 → 부천시
}


def load_env():
    """Load .env file"""
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip())


def normalize_dong_for_bjdong(dong_name: str) -> str:
    """실거래 동명 → bjdong_codes 키로 변환

    "고덕면 궁리" → "고덕면"
    "진접읍 부평리" → "진접읍"
    "퇴계원읍 퇴계원리" → "퇴계원면" (or "퇴계원읍" — 둘 다 시도)
    일반 동 → 그대로
    """
    # 읍/면 + 리 패턴
    m = re.match(r'^(.+?(?:읍|면))\s+\S+리$', dong_name)
    if m:
        return m.group(1)
    return dong_name


def find_bjdong_code(sigungu_cd: str, dong_name: str, bjdong_map: dict) -> tuple[str, str] | None:
    """(sigungu_cd, dong_name) → (actual_sigungu_cd, bjdong_cd) 찾기

    통합코드, 읍/면+리 매핑 등을 시도.
    """
    # 1) 직접 매칭
    codes = bjdong_map.get(sigungu_cd, {})
    if dong_name in codes:
        return (sigungu_cd, codes[dong_name])

    # 2) 읍/면+리 → 읍/면
    norm_dong = normalize_dong_for_bjdong(dong_name)
    if norm_dong != dong_name and norm_dong in codes:
        return (sigungu_cd, codes[norm_dong])

    # 3) 통합 시군구코드로 시도
    merged = MERGED_SIGUNGU.get(sigungu_cd)
    if merged:
        merged_codes = bjdong_map.get(merged, {})
        if dong_name in merged_codes:
            return (merged, merged_codes[dong_name])
        if norm_dong != dong_name and norm_dong in merged_codes:
            return (merged, merged_codes[norm_dong])

    # 4) 퇴계원읍 ↔ 퇴계원면 변환
    if dong_name.endswith("읍"):
        alt = dong_name[:-1] + "면"
        if alt in codes:
            return (sigungu_cd, codes[alt])
    elif dong_name.endswith("면"):
        alt = dong_name[:-1] + "읍"
        if alt in codes:
            return (sigungu_cd, codes[alt])

    return None


async def fetch_building_recap(
    sigungu_cd: str, bjdong_cd: str, api_key: str
) -> list[dict]:
    """건축물대장 총괄표제부 조회"""
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
            if name and hhld > 0:
                results.append({"bld_name": name, "household_count": hhld})
        except (ValueError, TypeError):
            continue
    return results


async def rebuild_cache():
    load_env()
    api_key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not api_key:
        print("ERROR: DATA_GO_KR_API_KEY 환경변수를 설정해주세요.")
        return

    from src.api_client import REGION_CODES

    # 캐시 로드
    with open(CACHE_PATH) as f:
        cache = json.load(f)
    original_size = len(cache)
    print(f"기존 캐시: {original_size:,}개")

    # bjdong_codes 로드
    with open(os.path.join(DATA_DIR, "bjdong_codes.json")) as f:
        bjdong_map = json.load(f)

    # raw_trades 로드
    with open(os.path.join(DATA_DIR, "raw_trades.json")) as f:
        trades = json.load(f)
    print(f"거래 데이터: {len(trades):,}건")

    # 매칭 로직 reimport (개선된 버전)
    if 'src.building_ledger' in sys.modules:
        del sys.modules['src.building_ledger']
    from src.building_ledger import get_household_count

    # 최근 3개월 거래 그룹핑
    now = datetime(2026, 3, 11)
    recent_yms = set()
    for i in range(3):
        dt = now - timedelta(days=30 * i)
        recent_yms.add((dt.year, dt.month))

    apt_recent = defaultdict(int)
    for t in trades:
        if 59 <= t["area"] <= 112 and t.get("dong"):
            key = (t["gu"], t["dong"], t["apt"])
            if (t["year"], t["month"]) in recent_yms:
                apt_recent[key] += 1

    # 미매칭 아파트 → 조회 필요한 (sigungu_cd, bjdong_cd, dong_name) 추출
    missing_apts = []
    query_dongs = set()  # (actual_sigungu_cd, bjdong_cd, dong_name)
    no_bjdong = set()

    for (gu, dong, apt), cnt in apt_recent.items():
        if cnt < 5:
            continue
        hhld = get_household_count(apt, dong)
        if hhld is not None:
            continue

        sigungu_cd = REGION_CODES.get(gu)
        if not sigungu_cd:
            continue

        result = find_bjdong_code(sigungu_cd, dong, bjdong_map)
        if result:
            actual_cd, bjdong_cd = result
            query_dongs.add((actual_cd, bjdong_cd, dong))
            missing_apts.append((gu, dong, apt, cnt))
        else:
            no_bjdong.add((gu, dong))

    print(f"\n미매칭 아파트: {len(missing_apts)}개 (5+ 최근 거래)")
    print(f"조회 대상 동: {len(query_dongs)}개")
    if no_bjdong:
        print(f"법정동코드 없음 ({len(no_bjdong)}개):")
        for gu, dong in sorted(no_bjdong):
            print(f"  {gu} {dong}")

    # API 조회
    sem = asyncio.Semaphore(3)  # rate limit
    added = 0
    errors = 0
    processed = 0

    async def fetch_one(actual_cd: str, bjdong_cd: str, dong_name: str):
        nonlocal added, errors, processed
        async with sem:
            try:
                await asyncio.sleep(0.3)  # rate limit
                results = await fetch_building_recap(actual_cd, bjdong_cd, api_key)
                for r in results:
                    bld = r["bld_name"]
                    hhld = r["household_count"]
                    # "동+아파트명" 키
                    dong_apt_key = dong_name + bld
                    if dong_apt_key not in cache:
                        cache[dong_apt_key] = hhld
                        added += 1
                    # 아파트명만 (동일명 충돌 없을 때)
                    if bld not in cache:
                        cache[bld] = hhld
                processed += 1
                if processed % 10 == 0:
                    print(f"  진행: {processed}/{len(query_dongs)} ({added}개 추가)")
            except Exception as e:
                errors += 1
                if errors <= 10:
                    print(f"  에러: {actual_cd}/{bjdong_cd} ({dong_name}) - {e}")

    tasks = [fetch_one(a, b, d) for a, b, d in sorted(query_dongs)]
    print(f"\nAPI 조회 시작... ({len(tasks)}건)")
    await asyncio.gather(*tasks)

    # 저장
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, ensure_ascii=False)

    print(f"\n완료!")
    print(f"  기존: {original_size:,}개")
    print(f"  추가: {added}개 (에러 {errors}건)")
    print(f"  최종: {len(cache):,}개")

    # 재검증: 개선된 매칭 + 새 캐시로 얼마나 매칭되는지
    if 'src.building_ledger' in sys.modules:
        del sys.modules['src.building_ledger']
    # 캐시를 다시 로드하기 위해 모듈 reimport
    from importlib import reload
    import src.building_ledger as bl
    bl.APT_HOUSEHOLD_CACHE = cache
    bl._NORMALIZED_CACHE = None
    bl._DONG_INDEX = None
    bl._APT_ONLY_CACHE = None

    still_missing = 0
    now_matched = 0
    for (gu, dong, apt), cnt in apt_recent.items():
        if cnt < 5:
            continue
        hhld = bl.get_household_count(apt, dong)
        if hhld is None:
            still_missing += 1
        else:
            now_matched += 1

    print(f"\n재검증:")
    print(f"  매칭 성공: {now_matched}개")
    print(f"  여전히 미매칭: {still_missing}개")


if __name__ == "__main__":
    asyncio.run(rebuild_cache())
