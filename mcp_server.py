"""
🏠 내집마련 AI 비서 — MCP 서버
Claude가 직접 호출할 수 있는 부동산 분석 도구들을 제공합니다.

실행: python3 mcp_server.py
연결: Claude Desktop / Claude Code에서 MCP 서버로 등록
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from mcp.server.fastmcp import FastMCP

from src.calculator import (
    BuyerType, LoanPolicy, UserFinance, calculate_affordability,
)
from src.api_client import REGION_CODES, SEOUL_TIERS
from src.building_ledger import get_household_count

# ─────────────────────────────────────
# MCP 서버 초기화
# ─────────────────────────────────────
mcp = FastMCP("내집마련 AI 비서")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def _load_analysis() -> list[dict]:
    path = os.path.join(DATA_DIR, "analysis.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []


# ─────────────────────────────────────
# Tool 1: 예산 계산
# ─────────────────────────────────────
@mcp.tool()
def calculate_budget(
    seed_money: int,
    annual_income: int,
    monthly_expense: int = 500,
    buyer_type: str = "생애최초",
    interest_rate: float = 4.0,
    will_reside: bool = True,
) -> str:
    """사용자의 재무 조건으로 매수 가능 금액을 계산합니다.

    Args:
        seed_money: 종잣돈 (만원)
        annual_income: 연봉/원천징수 (만원)
        monthly_expense: 월 지출 (만원)
        buyer_type: 매수자 유형 (생애최초/무주택/1주택)
        interest_rate: 예상 대출 금리 (%, 기본 4.0)
        will_reside: 실거주 여부
    """
    buyer_map = {
        "생애최초": BuyerType.FIRST_TIME,
        "무주택": BuyerType.NO_HOUSE,
        "1주택": BuyerType.ONE_HOUSE,
    }
    monthly_income = annual_income // 12
    policy = LoanPolicy(base_interest_rate=interest_rate / 100)
    user = UserFinance(
        seed_money=seed_money,
        monthly_income=monthly_income,
        monthly_expense=monthly_expense,
        buyer_type=buyer_map.get(buyer_type, BuyerType.FIRST_TIME),
        will_reside=will_reside,
    )
    r = calculate_affordability(user, policy)

    # 월 상환액 계산
    mr = (interest_rate / 100) / 12
    n = 360
    if r.final_max_loan > 0 and mr > 0:
        monthly_pay = r.final_max_loan * (mr * (1 + mr) ** n) / ((1 + mr) ** n - 1)
    else:
        monthly_pay = 0

    return json.dumps({
        "종잣돈": f"{seed_money:,}만원 ({seed_money/10000:.1f}억)",
        "연봉": f"{annual_income:,}만원",
        "월소득": f"{monthly_income:,}만원",
        "월지출": f"{monthly_expense:,}만원",
        "DSR_최대대출": f"{r.max_loan_by_dsr_stress:,}만원 ({r.max_loan_by_dsr_stress/10000:.1f}억)",
        "LTV_최대대출": f"{r.max_loan_by_ltv:,}만원 ({r.max_loan_by_ltv/10000:.1f}억)",
        "최종_대출": f"{r.final_max_loan:,}만원 ({r.final_max_loan/10000:.1f}억)",
        "매수가능_집값": f"{r.final_max_price:,}만원 ({r.final_max_price/10000:.1f}억)",
        "월_상환액": f"{monthly_pay:,.0f}만원",
        "월급대비": f"{monthly_pay/monthly_income*100:.1f}%",
        "시가별_한도": r.loan_cap_applied or "해당없음",
        "추천지역": [t.value for t in r.recommended_regions],
        "주의사항": r.warnings,
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────
# Tool 2: TOP 아파트 추천
# ─────────────────────────────────────
@mcp.tool()
def recommend_apartments(
    budget_max: int,
    budget_min: int = 0,
    seed_money: int = 0,
    loan_amount: int = 0,
    interest_rate: float = 4.0,
    min_households: int = 300,
    gu_filter: str = "",
    tier_filter: str = "",
    top_n: int = 10,
) -> str:
    """예산에 맞는 TOP N 아파트를 추천합니다.

    Args:
        budget_max: 최대 예산 (만원)
        budget_min: 최소 예산 (만원, 기본 0이면 최대의 50%)
        seed_money: 종잣돈 (만원, 월상환 계산용)
        loan_amount: 대출 금액 (만원, 월상환 계산용)
        interest_rate: 대출 금리 (%)
        min_households: 최소 세대수 (기본 300)
        gu_filter: 특정 구만 필터 (예: "노원구", 비우면 전체)
        tier_filter: 등급 필터 (상급지/중상급지/중하급지/하급지, 비우면 전체)
        top_n: 상위 N개 (기본 10)
    """
    data = _load_analysis()
    if not data:
        return json.dumps({"error": "분석 데이터가 없습니다. collect_data.py를 먼저 실행하세요."})

    if budget_min == 0:
        budget_min = max(int(budget_max * 0.5), 30000)

    mr = (interest_rate / 100) / 12
    n = 360
    candidates = []

    for r in data:
        if r["avg_price"] > budget_max or r["avg_price"] < budget_min:
            continue
        if r.get("hhld", 0) < min_households:
            continue
        if gu_filter and r["gu"] != gu_filter:
            continue
        if tier_filter and r["tier"] != tier_filter:
            continue

        # 스코어링
        tier_score = {"상급지": 40, "중상급지": 25, "중하급지": 10, "하급지": 0}.get(r["tier"], 0)
        ratio_score = min(r["ratio"], 80)
        if r["ratio"] > 80:
            ratio_score -= (r["ratio"] - 80) * 2
        hhld_score = min(r.get("hhld", 0) / 100, 20)
        volume_score = min(r["count"] * 3, 15)
        score = round(tier_score + ratio_score + hhld_score + volume_score, 1)

        # 월상환
        loan_needed = min(r["avg_price"] - seed_money, loan_amount) if seed_money > 0 else 0
        if loan_needed < 0:
            loan_needed = 0
        if loan_needed > 0 and mr > 0:
            mp = int(loan_needed * (mr * (1 + mr) ** n) / ((1 + mr) ** n - 1))
        else:
            mp = 0

        peak_gap = r["avg_price"] - r["peak"]

        candidates.append({
            "순위": 0,
            "아파트": r["apt"],
            "구": r["gu"],
            "등급": r["tier"],
            "매매가": f"{r['avg_price']/10000:.1f}억",
            "전세가율": f"{r['ratio']}%",
            "갭": f"{r['gap']/10000:.1f}억",
            "세대수": r.get("hhld", 0),
            "거래건수": r["count"],
            "월상환": f"{mp:,}만원",
            "전고점대비": f"{r['diff_peak']:+.1f}% ({abs(peak_gap)/10000:.1f}억 {'하락' if peak_gap < 0 else '상승'})",
            "전고점": f"{r['peak']/10000:.1f}억 ({r['peak_ym']})",
            "전저점대비": f"{r['diff_trough']:+.1f}%",
            "점수": score,
        })

    candidates.sort(key=lambda x: -x["점수"])
    for i, c in enumerate(candidates[:top_n], 1):
        c["순위"] = i

    return json.dumps({
        "예산범위": f"{budget_min/10000:.1f}~{budget_max/10000:.1f}억",
        "총_후보": len(candidates),
        "추천": candidates[:top_n],
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────
# Tool 3: 특정 아파트 상세 분석
# ─────────────────────────────────────
@mcp.tool()
def analyze_apartment(apt_name: str) -> str:
    """특정 아파트의 상세 분석 정보를 제공합니다.

    Args:
        apt_name: 아파트 이름 (부분 매칭 지원)
    """
    data = _load_analysis()
    matches = [r for r in data if apt_name in r["apt"] or r["apt"] in apt_name]

    if not matches:
        return json.dumps({"error": f"'{apt_name}' 아파트를 찾을 수 없습니다."})

    results = []
    for r in matches:
        peak_gap = r["avg_price"] - r["peak"]
        trough_gap = r["avg_price"] - r["trough"]
        results.append({
            "아파트": r["apt"],
            "구": r["gu"],
            "등급": r["tier"],
            "세대수": r.get("hhld", 0),
            "평균매매가": f"{r['avg_price']/10000:.1f}억 ({r['avg_price']:,}만원)",
            "평균전세가": f"{r['avg_rent']/10000:.1f}억",
            "전세가율": f"{r['ratio']}%",
            "갭": f"{r['gap']/10000:.1f}억",
            "거래건수": f"{r['count']}건",
            "전고점": f"{r['peak']/10000:.1f}억 ({r['peak_ym']})",
            "전고점대비": f"{r['diff_peak']:+.1f}% → 전고점대비 {abs(peak_gap)/10000:.1f}억 {'하락' if peak_gap < 0 else '상승'}",
            "전저점": f"{r['trough']/10000:.1f}억 ({r['trough_ym']})",
            "전저점대비": f"{r['diff_trough']:+.1f}% → 전저점대비 {abs(trough_gap)/10000:.1f}억 {'상승' if trough_gap > 0 else '하락'}",
        })

    return json.dumps(results, ensure_ascii=False, indent=2)


# ─────────────────────────────────────
# Tool 4: 지역 정보
# ─────────────────────────────────────
@mcp.tool()
def get_region_info(gu_name: str = "") -> str:
    """서울 각 구의 등급(상급지~하급지) 정보를 제공합니다.

    Args:
        gu_name: 특정 구 이름 (비우면 전체 목록)
    """
    if gu_name:
        tier = SEOUL_TIERS.get(gu_name, "정보없음")
        data = _load_analysis()
        gu_apts = [r for r in data if r["gu"] == gu_name]
        return json.dumps({
            "구": gu_name,
            "등급": tier,
            "분석된_아파트수": len(gu_apts),
            "평균매매가": f"{sum(r['avg_price'] for r in gu_apts)/len(gu_apts)/10000:.1f}억" if gu_apts else "데이터없음",
        }, ensure_ascii=False, indent=2)

    # 전체 등급 목록
    tiers = {"상급지": [], "중상급지": [], "중하급지": [], "하급지": []}
    for gu, tier in SEOUL_TIERS.items():
        tiers[tier].append(gu)
    return json.dumps(tiers, ensure_ascii=False, indent=2)


# ─────────────────────────────────────
# Tool 5: 대출 시뮬레이션
# ─────────────────────────────────────
@mcp.tool()
def simulate_loan(
    loan_amount: int,
    interest_rate: float = 4.0,
    monthly_income: int = 0,
) -> str:
    """대출 상환 시뮬레이션 (30년/15년/거치3년+27년 비교)

    Args:
        loan_amount: 대출 금액 (만원)
        interest_rate: 금리 (%)
        monthly_income: 월소득 (만원, 월급대비 계산용)
    """
    r = (interest_rate / 100) / 12
    scenarios = {}

    # 30년 원리금균등
    n = 360
    m30 = loan_amount * (r * (1 + r) ** n) / ((1 + r) ** n - 1)
    scenarios["30년_원리금균등"] = {
        "월상환": f"{m30:,.0f}만원",
        "총이자": f"{(m30 * n - loan_amount)/10000:.1f}억",
        "월급대비": f"{m30/monthly_income*100:.1f}%" if monthly_income > 0 else "-",
    }

    # 15년 조기상환
    n15 = 180
    m15 = loan_amount * (r * (1 + r) ** n15) / ((1 + r) ** n15 - 1)
    scenarios["15년_조기상환"] = {
        "월상환": f"{m15:,.0f}만원",
        "총이자": f"{(m15 * n15 - loan_amount)/10000:.1f}억",
        "월급대비": f"{m15/monthly_income*100:.1f}%" if monthly_income > 0 else "-",
    }

    # 거치 3년 + 27년
    grace = loan_amount * (interest_rate / 100) / 12
    n27 = 324
    m27 = loan_amount * (r * (1 + r) ** n27) / ((1 + r) ** n27 - 1)
    scenarios["거치3년_27년"] = {
        "처음3년_월": f"{grace:,.0f}만원 (이자만)",
        "이후_월": f"{m27:,.0f}만원",
        "총이자": f"{(grace * 36 + m27 * n27 - loan_amount)/10000:.1f}억",
    }

    return json.dumps({
        "대출금액": f"{loan_amount/10000:.1f}억",
        "금리": f"{interest_rate}%",
        "시나리오": scenarios,
    }, ensure_ascii=False, indent=2)


# ─────────────────────────────────────
# 실행
# ─────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
