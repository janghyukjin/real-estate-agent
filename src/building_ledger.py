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


def _normalize(name: str) -> str:
    """아파트명 정규화: 공백·특수문자·접미사 제거, 소문자"""
    import re
    s = re.sub(r'[\s\-·,.()（）/]', '', name).lower()
    # 접미사 제거: "아파트", "단지" 등 (정규화 매칭 정확도 향상)
    s = re.sub(r'아파트$', '', s)
    s = re.sub(r'단지$', '', s)
    return s


# 정규화된 캐시 + dong별 인덱스 (초기화 시 1회 생성)
_NORMALIZED_CACHE: dict[str, int] | None = None
_DONG_INDEX: dict[str, list[tuple[str, str, int]]] | None = None  # dong -> [(key, norm_apt_part, count)]


def _get_normalized_cache() -> dict[str, int]:
    global _NORMALIZED_CACHE
    if _NORMALIZED_CACHE is None:
        _NORMALIZED_CACHE = {}
        for key, val in APT_HOUSEHOLD_CACHE.items():
            nk = _normalize(key)
            if nk not in _NORMALIZED_CACHE:
                _NORMALIZED_CACHE[nk] = val
    return _NORMALIZED_CACHE


def _get_dong_index() -> dict[str, list[tuple[str, int]]]:
    """dong별로 캐시를 사전 인덱싱"""
    global _DONG_INDEX
    if _DONG_INDEX is None:
        _DONG_INDEX = {}
        for key, val in APT_HOUSEHOLD_CACHE.items():
            # 키에서 동 이름 추출 (동으로 끝나는 부분)
            import re
            dong_match = re.match(r'^(.+?동\d*[가]?)\s*', key)
            if dong_match:
                dong = dong_match.group(1)
                apt_part = key[len(dong):].strip()
                norm_apt = _normalize(apt_part) if apt_part else _normalize(key)
                _DONG_INDEX.setdefault(dong, []).append((norm_apt, val))
    return _DONG_INDEX


def get_household_count(apt_name: str, dong: str = "") -> int | None:
    """아파트명으로 세대수 조회 (정규화 매칭)

    매칭 우선순위:
    1. dong+apt 정확 매칭 ("역삼동경남아너스빌")
    2. dong+apt 정규화 매칭 (공백·특수문자 제거 후 비교)
    3. apt 정확 매칭
    4. apt 정규화 매칭
    5. 매칭 실패 → None
    """
    norm_cache = _get_normalized_cache()

    # 1) dong+apt 정확 매칭
    if dong:
        dong_apt = dong + apt_name
        if dong_apt in APT_HOUSEHOLD_CACHE:
            return APT_HOUSEHOLD_CACHE[dong_apt]
        # 2) dong+apt 정규화 매칭
        norm_dong_apt = _normalize(dong_apt)
        if norm_dong_apt in norm_cache:
            return norm_cache[norm_dong_apt]
        # 3) dong 범위 내 부분매칭 (dong별 인덱스 사용, 빠름)
        norm_apt = _normalize(apt_name)
        dong_idx = _get_dong_index()
        dong_entries = dong_idx.get(dong, [])
        best_match = None
        best_len = 0
        for cached_norm_apt, val in dong_entries:
            if not cached_norm_apt or not norm_apt:
                continue
            if norm_apt in cached_norm_apt or cached_norm_apt in norm_apt:
                match_len = min(len(norm_apt), len(cached_norm_apt))
                if match_len > best_len:
                    best_match = val
                    best_len = match_len
        if best_match is not None:
            return best_match

    # 4) apt 정확 매칭
    if apt_name in APT_HOUSEHOLD_CACHE:
        return APT_HOUSEHOLD_CACHE[apt_name]

    # 5) apt 정규화 매칭
    norm_apt = _normalize(apt_name)
    if norm_apt in norm_cache:
        return norm_cache[norm_apt]

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
