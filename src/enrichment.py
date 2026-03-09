"""
매물 데이터 보강 모듈

공식 API가 있는 소스들을 활용하여
실거래가 데이터에 입지 정보를 보강합니다.

TODO: 각 API 키 발급 필요
- 카카오 REST API: https://developers.kakao.com
- 학구도 API: https://www.data.go.kr (교육부 학구도 정보)
- SGIS 통계지리정보: https://sgis.kostat.go.kr
"""

import httpx
from dataclasses import dataclass


@dataclass
class LocationScore:
    """입지 점수"""
    apt_name: str
    address: str
    # 교통
    nearest_subway: str = ""
    subway_distance_m: int = 0      # 지하철 도보 거리 (미터)
    subway_walk_min: int = 0        # 도보 시간 (분)
    # 학군
    elementary_school: str = ""
    middle_school: str = ""
    school_distance_m: int = 0
    # 편의시설
    nearby_hospitals: int = 0
    nearby_marts: int = 0
    nearby_parks: int = 0
    # 종합 점수
    transport_score: int = 0        # 0~100
    education_score: int = 0
    convenience_score: int = 0


async def get_nearby_subway(
    lat: float, lng: float, kakao_api_key: str
) -> dict:
    """카카오 로컬 API로 가장 가까운 지하철역 조회

    카카오 REST API 키 필요: https://developers.kakao.com
    """
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    headers = {"Authorization": f"KakaoAK {kakao_api_key}"}
    params = {
        "category_group_code": "SW8",  # 지하철역
        "x": str(lng),
        "y": str(lat),
        "radius": 2000,  # 2km 내
        "sort": "distance",
        "size": 1,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data["documents"]:
        station = data["documents"][0]
        return {
            "name": station["place_name"],
            "distance_m": int(station["distance"]),
            "walk_min": int(station["distance"]) // 80,  # 분속 80m
        }
    return {"name": "", "distance_m": 0, "walk_min": 0}


async def get_nearby_facilities(
    lat: float, lng: float, kakao_api_key: str
) -> dict:
    """주변 편의시설 개수 조회"""
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    headers = {"Authorization": f"KakaoAK {kakao_api_key}"}

    categories = {
        "HP8": "hospitals",   # 병원
        "MT1": "marts",       # 대형마트
        "AT4": "parks",       # 관광명소 (공원 포함)
    }

    result = {}
    async with httpx.AsyncClient() as client:
        for code, name in categories.items():
            params = {
                "category_group_code": code,
                "x": str(lng),
                "y": str(lat),
                "radius": 1000,
                "size": 15,
            }
            resp = await client.get(url, headers=headers, params=params)
            data = resp.json()
            result[name] = len(data.get("documents", []))

    return result


async def geocode_address(
    address: str, kakao_api_key: str
) -> tuple[float, float] | None:
    """주소 → 좌표 변환 (카카오 지오코딩)"""
    url = "https://dapi.kakao.com/v2/local/search/address.json"
    headers = {"Authorization": f"KakaoAK {kakao_api_key}"}
    params = {"query": address}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        data = resp.json()

    if data["documents"]:
        doc = data["documents"][0]
        return float(doc["y"]), float(doc["x"])  # lat, lng
    return None


# ──────────────────────────────────────────────
# 네이버 부동산 / 호갱노노 / 아실 관련 참고
# ──────────────────────────────────────────────
#
# 이 플랫폼들은 공식 API를 제공하지 않습니다.
# 스크래핑은 법적 리스크가 있으므로 (컴퓨터프로그램보호법),
# 정식 서비스화 시에는 다음 대안을 고려:
#
# 1. 직접 매물 DB 구축
#    - 공인중개사 연계 → 매물 등록 시스템
#    - 부동산 114 API (유료)
#
# 2. 사용자 기여 리뷰
#    - 실거주 후기를 사용자가 직접 작성
#    - 아파트 단지별 리뷰 DB
#
# 3. 공공 데이터 활용
#    - 국토부 실거래가 (현재 연동)
#    - 건축물대장 API → 세대수, 주차대수, 면적 정보
#    - 공시지가 API → 토지/건물 공시가격
#
# 크로스체크 대안:
# - 실거래가(국토부) vs 호가(사용자 입력) 비교
# - 전세가율 계산 (전세실거래가 / 매매실거래가)
# - KB시세 참고 (KB부동산 데이터허브 API - 유료)
