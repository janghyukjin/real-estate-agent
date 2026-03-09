"""
건축물대장 API 클라이언트

공공데이터포털 - 국토교통부 건축물대장정보 서비스
→ 세대수, 총 동수, 주차대수, 건축면적, 사용승인일 등 조회

API 키: data.go.kr에서 '건축물대장정보 서비스' 활용신청 (즉시 승인)
환경변수 DATA_GO_KR_API_KEY 공유 사용.
"""

import os
from dataclasses import dataclass

import httpx

# 건축물대장 API 엔드포인트
BUILDING_TITLE_URL = (
    "http://apis.data.go.kr/1613000/"
    "BldRgstHubService/getBrTitleInfo"
)
BUILDING_RECAP_URL = (
    "http://apis.data.go.kr/1613000/"
    "BldRgstHubService/getBrRecapTitleInfo"
)


@dataclass
class BuildingInfo:
    """건축물대장 총괄표제부 데이터"""
    bld_name: str           # 건물명
    dong_count: int         # 총 동수
    household_count: int    # 세대수 (총 가구수)
    ground_floor: int       # 지상 층수
    underground_floor: int  # 지하 층수
    use_apr_day: str        # 사용승인일
    main_purps: str         # 주용도
    tot_area: float         # 연면적 (㎡)
    parking_count: int      # 주차대수 (옥외+옥내)
    sigungu_cd: str         # 시군구코드
    bjdong_cd: str          # 법정동코드


def _get_api_key() -> str:
    key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not key:
        raise ValueError("환경변수 DATA_GO_KR_API_KEY를 설정해주세요.")
    return key


async def fetch_building_info(
    sigungu_cd: str,
    bjdong_cd: str,
    bun: str = "",
    ji: str = "",
    api_key: str | None = None,
) -> list[BuildingInfo]:
    """건축물대장 총괄표제부 조회

    Args:
        sigungu_cd: 시군구코드 5자리
        bjdong_cd: 법정동코드 5자리
        bun: 본번 (4자리, 선택)
        ji: 부번 (4자리, 선택)
    """
    if api_key is None:
        api_key = _get_api_key()

    params = {
        "serviceKey": api_key,
        "sigunguCd": sigungu_cd,
        "bjdongCd": bjdong_cd,
        "numOfRows": "500",
        "pageNo": "1",
    }
    if bun:
        params["bun"] = bun.zfill(4)
    if ji:
        params["ji"] = ji.zfill(4)

    # 총괄표제부 우선 (단지 전체 세대수), 실패시 표제부
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(BUILDING_RECAP_URL, params=params)
        resp.raise_for_status()

    return _parse_building_xml(resp.text)


def _parse_building_xml(xml_text: str) -> list[BuildingInfo]:
    """건축물대장 XML 파싱"""
    import xml.etree.ElementTree as ET

    buildings: list[BuildingInfo] = []
    root = ET.fromstring(xml_text)

    items = root.findall(".//item")
    for item in items:
        try:
            buildings.append(BuildingInfo(
                bld_name=(item.findtext("bldNm") or "").strip(),
                dong_count=int(item.findtext("dongCnt") or "0"),
                household_count=int(item.findtext("hhldCnt") or item.findtext("hoCnt") or "0"),
                ground_floor=int(item.findtext("grndFlrCnt") or "0"),
                underground_floor=int(item.findtext("ugrndFlrCnt") or "0"),
                use_apr_day=(item.findtext("useAprDay") or "").strip(),
                main_purps=(item.findtext("mainPurpsCdNm") or "").strip(),
                tot_area=float(item.findtext("totArea") or "0"),
                parking_count=(
                    int(item.findtext("oudrMechUtcnt") or "0")
                    + int(item.findtext("oudrAutoUtcnt") or "0")
                    + int(item.findtext("indrMechUtcnt") or "0")
                    + int(item.findtext("indrAutoUtcnt") or "0")
                ),
                sigungu_cd=(item.findtext("sigunguCd") or "").strip(),
                bjdong_cd=(item.findtext("bjdongCd") or "").strip(),
            ))
        except (ValueError, TypeError):
            continue

    return buildings


def filter_by_households(
    buildings: list[BuildingInfo],
    min_households: int = 300,
) -> list[BuildingInfo]:
    """세대수 기준 필터링"""
    return [b for b in buildings if b.household_count >= min_households]


# ──────────────────────────────────────────────
# 아파트 단지 정보 캐시 (실거래가 매칭용)
# ──────────────────────────────────────────────
# 실거래가 데이터에는 세대수가 없으므로,
# 건축물대장에서 세대수를 미리 조회하여 캐시해두고
# 실거래가 결과에 세대수를 매칭하는 방식으로 사용.

# 서울 전역 아파트 세대수 캐시 (건축물대장 API 기반, 300세대+)
# 2026-03-09 건축물대장 총괄표제부 기준 자동 수집
# 런타임에 update_cache_from_api()로 추가 업데이트 가능
import json as _json
import os as _os

def _load_cache() -> dict[str, int]:
    """캐시 파일 있으면 로드, 없으면 기본값"""
    cache_path = _os.path.join(_os.path.dirname(__file__), "..", "data", "apt_cache.json")
    if _os.path.exists(cache_path):
        with open(cache_path) as f:
            return _json.load(f)
    return {}

APT_HOUSEHOLD_CACHE: dict[str, int] = _load_cache()


def get_household_count(apt_name: str) -> int | None:
    """아파트명으로 세대수 조회 (캐시 우선)"""
    # 정확한 이름 매칭
    if apt_name in APT_HOUSEHOLD_CACHE:
        return APT_HOUSEHOLD_CACHE[apt_name]
    # 부분 매칭 (실거래 데이터 아파트명이 약간 다를 수 있음)
    for cached_name, count in APT_HOUSEHOLD_CACHE.items():
        if cached_name in apt_name or apt_name in cached_name:
            return count
    return None


def is_large_complex(apt_name: str, min_households: int = 300) -> bool | None:
    """대단지 여부 확인 (캐시 기반)

    Returns:
        True: 대단지, False: 소단지, None: 데이터 없음
    """
    count = get_household_count(apt_name)
    if count is None:
        return None
    return count >= min_households


# ──────────────────────────────────────────────
# 노원구 법정동코드 매핑 (건축물대장 조회용)
# ──────────────────────────────────────────────
# sigunguCd(5자리) + bjdongCd(5자리) 조합 필요
BJDONG_CODES: dict[str, dict[str, str]] = {
    "11350": {  # 노원구
        "월계동": "10200",
        "공릉동": "10300",
        "중계동": "10400",
        "상계동": "10500",
        "하계동": "10600",
    },
    "11290": {  # 성북구
        "정릉동": "10600",
        "길음동": "10700",
        "장위동": "10900",
    },
    "11410": {  # 서대문구
        "연희동": "10400",
        "남가좌동": "10800",
        "북가좌동": "10900",
    },
}


async def fetch_apt_households(
    sigungu_cd: str,
    dong_name: str,
    min_households: int = 100,
    api_key: str | None = None,
) -> dict[str, int]:
    """특정 동의 아파트 세대수 일괄 조회 (건축물대장 API)

    Returns:
        {아파트명: 세대수} 딕셔너리
    """
    bjdong_map = BJDONG_CODES.get(sigungu_cd, {})
    bjdong_cd = bjdong_map.get(dong_name)
    if not bjdong_cd:
        return {}

    buildings = await fetch_building_info(sigungu_cd, bjdong_cd, api_key=api_key)
    result = {}
    for b in buildings:
        if b.household_count >= min_households and b.bld_name:
            result[b.bld_name] = b.household_count
    return result


async def update_cache_from_api(
    sigungu_cd: str,
    dong_names: list[str] | None = None,
    min_households: int = 100,
) -> int:
    """건축물대장 API로 캐시 업데이트

    Returns:
        새로 추가된 아파트 수
    """
    bjdong_map = BJDONG_CODES.get(sigungu_cd, {})
    if dong_names is None:
        dong_names = list(bjdong_map.keys())

    added = 0
    for dong in dong_names:
        households = await fetch_apt_households(sigungu_cd, dong, min_households)
        for name, count in households.items():
            if name not in APT_HOUSEHOLD_CACHE:
                APT_HOUSEHOLD_CACHE[name] = count
                added += 1
    return added
