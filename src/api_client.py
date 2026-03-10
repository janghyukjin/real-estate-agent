"""
국토교통부 부동산 실거래가 공공 API 클라이언트

API 출처: data.go.kr (공공데이터포털)
- 아파트매매 실거래 상세 자료
- 아파트 전월세 자료

사용하려면 data.go.kr에서 API 키를 발급받아야 합니다.
환경변수 DATA_GO_KR_API_KEY 에 설정하세요.
"""

import os
from datetime import datetime, timedelta
from dataclasses import dataclass

import httpx
import pandas as pd


# 국토교통부 API 엔드포인트 (data.go.kr 공공데이터포털)
APT_TRADE_URL = (
    "http://apis.data.go.kr/1613000/"
    "RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev"
)
APT_RENT_URL = (
    "http://apis.data.go.kr/1613000/"
    "RTMSDataSvcAptRent/getRTMSDataSvcAptRent"
)

# 주요 법정동코드 (시군구 5자리)
REGION_CODES: dict[str, str] = {
    # 서울
    "강남구": "11680",
    "서초구": "11650",
    "송파구": "11710",
    "강동구": "11740",
    "마포구": "11440",
    "용산구": "11170",
    "성동구": "11200",
    "광진구": "11215",
    "동작구": "11590",
    "영등포구": "11560",
    "양천구": "11470",
    "강서구": "11500",
    "구로구": "11530",
    "금천구": "11545",
    "관악구": "11620",
    "노원구": "11350",
    "도봉구": "11320",
    "강북구": "11305",
    "성북구": "11290",
    "종로구": "11110",
    "중구": "11140",
    "동대문구": "11230",
    "중랑구": "11260",
    "서대문구": "11410",
    "은평구": "11380",
    # 경기 주요
    "수원시장안구": "41111",
    "수원시권선구": "41113",
    "수원시팔달구": "41115",
    "수원시영통구": "41117",
    "성남시수정구": "41131",
    "성남시중원구": "41133",
    "성남시분당구": "41135",
    "고양시덕양구": "41281",
    "고양시일산동구": "41285",
    "고양시일산서구": "41287",
    "용인시수지구": "41465",
    "용인시기흥구": "41463",
    "과천시": "41290",
    "광명시": "41210",
    "하남시": "41450",
    "안양시동안구": "41173",
    "안양시만안구": "41171",
    "부천시": "41190",
    "의왕시": "41430",
    "군포시": "41410",
    "화성시": "41590",
    "평택시": "41220",
}

# 지역 등급 분류
SEOUL_TIERS: dict[str, str] = {
    # 서울 상급지
    "강남구": "상급지", "서초구": "상급지", "송파구": "상급지", "용산구": "상급지",
    # 서울 중상급지
    "마포구": "중상급지", "성동구": "중상급지", "광진구": "중상급지",
    "동작구": "중상급지", "강동구": "중상급지", "영등포구": "중상급지",
    "양천구": "중상급지",
    # 서울 중하급지
    "노원구": "중하급지", "도봉구": "중하급지", "강북구": "중하급지",
    "성북구": "중하급지", "중랑구": "중하급지", "동대문구": "중하급지",
    "서대문구": "중하급지", "은평구": "중하급지",
    # 서울 하급지
    "강서구": "하급지", "구로구": "하급지", "금천구": "하급지",
    "관악구": "하급지", "종로구": "하급지", "중구": "하급지",
    # 경기 상급지
    "과천시": "상급지(경기·과천)", "성남시분당구": "상급지(경기)",
}


@dataclass
class AptTrade:
    """아파트 매매 실거래 데이터"""
    apt_name: str         # 아파트명
    deal_amount: int      # 거래금액 (만원)
    area: float           # 전용면적 (㎡)
    floor: int            # 층
    year: int             # 거래년도
    month: int            # 거래월
    day: int              # 거래일
    dong: str             # 법정동
    build_year: int       # 건축년도
    gu: str               # 시군구
    jibun: str = ""       # 지번
    deal_type: str = ""   # 거래유형 (중개거래/직거래)


def get_api_key() -> str:
    key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not key:
        raise ValueError(
            "환경변수 DATA_GO_KR_API_KEY를 설정해주세요.\n"
            "data.go.kr에서 '국토교통부 아파트매매 실거래 상세 자료' API 키를 발급받으세요."
        )
    return key


async def fetch_apt_trades(
    region_code: str,
    deal_ymd: str,  # YYYYMM 형식
    api_key: str | None = None,
) -> list[AptTrade]:
    """아파트 매매 실거래 데이터 조회

    Args:
        region_code: 시군구코드 5자리
        deal_ymd: 계약년월 (YYYYMM)
        api_key: data.go.kr API 키
    """
    if api_key is None:
        api_key = get_api_key()

    params = {
        "serviceKey": api_key,
        "LAWD_CD": region_code,
        "DEAL_YMD": deal_ymd,
        "pageNo": "1",
        "numOfRows": "9999",
    }

    async with httpx.AsyncClient(timeout=30, http2=False) as client:
        resp = await client.get(APT_TRADE_URL, params=params)
        resp.raise_for_status()

    return _parse_trade_xml(resp.text, region_code)


def _parse_trade_xml(xml_text: str, gu_code: str) -> list[AptTrade]:
    """XML 응답을 파싱하여 AptTrade 리스트 반환"""
    import xml.etree.ElementTree as ET

    trades: list[AptTrade] = []
    root = ET.fromstring(xml_text)

    # 시군구코드 → 구이름 역매핑
    code_to_name = {v: k for k, v in REGION_CODES.items()}
    gu_name = code_to_name.get(gu_code, gu_code)

    items = root.findall(".//item")
    for item in items:
        try:
            # 필드명: 한글(구버전) 또는 영문(신버전) 둘 다 지원
            amount_str = (
                item.findtext("dealAmount") or item.findtext("거래금액") or "0"
            ).strip().replace(",", "")
            trades.append(AptTrade(
                apt_name=(item.findtext("aptNm") or item.findtext("아파트") or "").strip(),
                deal_amount=int(amount_str),
                area=float(item.findtext("excluUseAr") or item.findtext("전용면적") or "0"),
                floor=int(item.findtext("floor") or item.findtext("층") or "0"),
                year=int(item.findtext("dealYear") or item.findtext("년") or "0"),
                month=int(item.findtext("dealMonth") or item.findtext("월") or "0"),
                day=int(item.findtext("dealDay") or item.findtext("일") or "0"),
                dong=(item.findtext("umdNm") or item.findtext("법정동") or "").strip(),
                build_year=int(item.findtext("buildYear") or item.findtext("건축년도") or "0"),
                gu=gu_name,
                jibun=(item.findtext("jibun") or item.findtext("지번") or "").strip(),
                deal_type=(item.findtext("dealingGbn") or item.findtext("거래유형") or "").strip(),
            ))
        except (ValueError, TypeError):
            continue

    return trades


async def fetch_recent_trades(
    region_code: str,
    months: int = 6,
    api_key: str | None = None,
) -> list[AptTrade]:
    """최근 N개월 실거래 데이터 조회"""
    if api_key is None:
        api_key = get_api_key()

    all_trades: list[AptTrade] = []
    now = datetime.now()

    for i in range(months):
        dt = now - timedelta(days=30 * i)
        ymd = dt.strftime("%Y%m")
        trades = await fetch_apt_trades(region_code, ymd, api_key)
        all_trades.extend(trades)

    return all_trades


def trades_to_dataframe(trades: list[AptTrade]) -> pd.DataFrame:
    """실거래 데이터를 DataFrame으로 변환"""
    if not trades:
        return pd.DataFrame()

    records = [
        {
            "아파트": t.apt_name,
            "거래금액(만원)": t.deal_amount,
            "전용면적(㎡)": t.area,
            "층": t.floor,
            "거래년월": f"{t.year}-{t.month:02d}",
            "거래일": t.day,
            "법정동": t.dong,
            "건축년도": t.build_year,
            "시군구": t.gu,
        }
        for t in trades
    ]
    df = pd.DataFrame(records)
    df = df.sort_values("거래금액(만원)", ascending=False)
    return df


@dataclass
class AptRent:
    """아파트 전월세 실거래 데이터"""
    apt_name: str         # 아파트명
    deposit: int          # 보증금 (만원)
    monthly_rent: int     # 월세 (만원, 전세면 0)
    area: float           # 전용면적 (㎡)
    floor: int            # 층
    year: int
    month: int
    day: int
    dong: str
    build_year: int
    gu: str
    rent_type: str = ""   # 전세/월세


async def fetch_apt_rents(
    region_code: str,
    deal_ymd: str,
    api_key: str | None = None,
) -> list[AptRent]:
    """아파트 전월세 실거래 데이터 조회"""
    if api_key is None:
        api_key = get_api_key()

    params = {
        "serviceKey": api_key,
        "LAWD_CD": region_code,
        "DEAL_YMD": deal_ymd,
        "pageNo": "1",
        "numOfRows": "9999",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(APT_RENT_URL, params=params)
        resp.raise_for_status()

    return _parse_rent_xml(resp.text, region_code)


def _parse_rent_xml(xml_text: str, gu_code: str) -> list[AptRent]:
    """전월세 XML 응답 파싱"""
    import xml.etree.ElementTree as ET

    rents: list[AptRent] = []
    root = ET.fromstring(xml_text)

    code_to_name = {v: k for k, v in REGION_CODES.items()}
    gu_name = code_to_name.get(gu_code, gu_code)

    items = root.findall(".//item")
    for item in items:
        try:
            deposit_str = (
                item.findtext("deposit") or item.findtext("보증금액") or "0"
            ).strip().replace(",", "")
            monthly_str = (
                item.findtext("monthlyRent") or item.findtext("월세금액") or "0"
            ).strip().replace(",", "")
            monthly_rent = int(monthly_str)

            rents.append(AptRent(
                apt_name=(item.findtext("aptNm") or item.findtext("아파트") or "").strip(),
                deposit=int(deposit_str),
                monthly_rent=monthly_rent,
                area=float(item.findtext("excluUseAr") or item.findtext("전용면적") or "0"),
                floor=int(item.findtext("floor") or item.findtext("층") or "0"),
                year=int(item.findtext("dealYear") or item.findtext("년") or "0"),
                month=int(item.findtext("dealMonth") or item.findtext("월") or "0"),
                day=int(item.findtext("dealDay") or item.findtext("일") or "0"),
                dong=(item.findtext("umdNm") or item.findtext("법정동") or "").strip(),
                build_year=int(item.findtext("buildYear") or item.findtext("건축년도") or "0"),
                gu=gu_name,
                rent_type="전세" if monthly_rent == 0 else "월세",
            ))
        except (ValueError, TypeError):
            continue

    return rents


async def fetch_recent_rents(
    region_code: str,
    months: int = 6,
    jeonse_only: bool = True,
    api_key: str | None = None,
) -> list[AptRent]:
    """최근 N개월 전월세 데이터 조회"""
    if api_key is None:
        api_key = get_api_key()

    all_rents: list[AptRent] = []
    now = datetime.now()

    for i in range(months):
        dt = now - timedelta(days=30 * i)
        ymd = dt.strftime("%Y%m")
        rents = await fetch_apt_rents(region_code, ymd, api_key)
        all_rents.extend(rents)

    if jeonse_only:
        all_rents = [r for r in all_rents if r.rent_type == "전세"]

    return all_rents


def filter_by_budget(
    trades: list[AptTrade],
    min_price: int,
    max_price: int,
    min_area: float = 59.0,
    max_area: float = 85.0,
) -> list[AptTrade]:
    """예산과 면적 범위로 필터링"""
    return [
        t for t in trades
        if min_price <= t.deal_amount <= max_price
        and min_area <= t.area <= max_area
    ]


def analyze_price_trend(trades: list[AptTrade], apt_name: str) -> pd.DataFrame:
    """특정 아파트의 가격 추이 분석"""
    apt_trades = [t for t in trades if t.apt_name == apt_name]
    if not apt_trades:
        return pd.DataFrame()

    df = trades_to_dataframe(apt_trades)
    trend = (
        df.groupby("거래년월")["거래금액(만원)"]
        .agg(["mean", "min", "max", "count"])
        .round(0)
        .rename(columns={
            "mean": "평균가",
            "min": "최저가",
            "max": "최고가",
            "count": "거래건수",
        })
    )
    return trend
