"""
내집마련 자금 계산기

10.15 부동산 대책 (2025.10.15) 반영:
- 스트레스 DSR 가산금리: 1.5% → 3.0% 상향
- LTV: 무주택자 40%, 생애최초 70% (규제지역)
- 시가 15억 초과 주담대 한도: 4억
- 시가 25억 초과 주담대 한도: 2억
- 토지거래허가구역: 서울 전역 + 경기 12곳 (2026.12.31까지)
- 실거주 의무: 2년 (토허제), 전입 6개월 이내 (생애최초)
- 유주택자 LTV 0% (사실상 추가 대출 불가)
"""

from dataclasses import dataclass, field
from enum import Enum


class BuyerType(Enum):
    FIRST_TIME = "생애최초"       # 무주택 + 생애최초
    NO_HOUSE = "무주택"           # 무주택 일반
    ONE_HOUSE = "1주택"
    MULTI_HOME = "다주택자"


class RegionTier(Enum):
    """서울/수도권 부동산 등급 분류"""
    GYEONGGI = "경기"
    SEOUL_LOW = "서울 하급지"
    SEOUL_MID_LOW = "서울 중하급지"
    SEOUL_MID_HIGH = "서울 중상급지"
    SEOUL_HIGH = "서울 상급지"


# 지역별 대략적 가격대 (만원, 전용 59~84㎡ 기준)
REGION_PRICE_RANGE: dict[RegionTier, tuple[int, int]] = {
    RegionTier.GYEONGGI: (10_000, 40_000),
    RegionTier.SEOUL_LOW: (40_000, 70_000),
    RegionTier.SEOUL_MID_LOW: (70_000, 100_000),
    RegionTier.SEOUL_MID_HIGH: (100_000, 150_000),
    RegionTier.SEOUL_HIGH: (150_000, 300_000),
}


@dataclass
class LoanPolicy:
    """대출 규제 정책 (10.15 대책 반영)"""
    # DSR
    dsr_ratio: float = 0.40                # DSR 40%
    stress_rate: float = 0.03              # 스트레스 가산금리 3.0% (10.15 변경)
    base_interest_rate: float = 0.04       # 기본 금리 4%

    # LTV (규제지역 = 서울 전역 기준)
    ltv_first_time: float = 0.70           # 생애최초 LTV 70% (10.15 변경, 기존 80%)
    ltv_no_house: float = 0.40             # 무주택 일반 LTV 40% (10.15 변경, 기존 70%)
    ltv_one_house: float = 0.0             # 1주택자 LTV 0% (사실상 불가)
    ltv_multi_home: float = 0.0            # 다주택자 LTV 0%

    # 대출 한도 (10.15 변경)
    max_loan_under_15: int = 60_000        # 시가 15억 이하: 기존 6억 한도
    max_loan_15_to_25: int = 40_000        # 시가 15억 초과~25억: 4억 한도
    max_loan_over_25: int = 20_000         # 시가 25억 초과: 2억 한도

    # 대출 기간
    loan_term_years: int = 30

    # 토지거래허가구역 (서울 전역 2026.12.31까지)
    land_permit_zone: bool = True          # 서울은 기본 True
    require_move_in_months: int = 6        # 생애최초 전입 의무 기간

    @property
    def effective_rate(self) -> float:
        """스트레스 DSR 적용 실효금리"""
        return self.base_interest_rate + self.stress_rate


@dataclass
class UserFinance:
    """사용자 재무 상태 (단위: 만원)"""
    seed_money: int                # 종잣돈
    monthly_income: int            # 월소득
    monthly_expense: int           # 월지출
    buyer_type: BuyerType = BuyerType.FIRST_TIME
    existing_debt_payment: int = 0 # 기존 대출 월상환액
    will_reside: bool = True       # 실거주 여부

    @property
    def monthly_saving(self) -> int:
        return self.monthly_income - self.monthly_expense


@dataclass
class AffordabilityResult:
    """자금 계산 결과 (단위: 만원)"""
    seed_money: int
    monthly_saving: int
    # DSR 기반
    max_loan_by_dsr: int
    max_loan_by_dsr_stress: int    # 스트레스 DSR 적용
    max_price_by_dsr: int
    # LTV 기반
    max_loan_by_ltv: int
    # 최종
    final_max_loan: int
    final_max_price: int
    # 시가별 한도 적용 결과
    loan_cap_applied: str = ""     # 어떤 한도가 적용됐는지
    recommended_regions: list[RegionTier] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def calculate_max_loan_dsr(
    monthly_income: int,
    existing_debt_payment: int,
    interest_rate: float,
    loan_term_years: int,
    dsr_ratio: float,
) -> int:
    """DSR 기반 최대 대출 가능액 계산

    원리금균등상환 기준:
    월상환액 = 대출금 × r(1+r)^n / ((1+r)^n - 1)
    """
    annual_income = monthly_income * 12
    max_annual_repayment = annual_income * dsr_ratio
    existing_annual_debt = existing_debt_payment * 12
    available_annual_repayment = max_annual_repayment - existing_annual_debt

    if available_annual_repayment <= 0:
        return 0

    monthly_repayment = available_annual_repayment / 12
    r = interest_rate / 12
    n = loan_term_years * 12

    if r <= 0:
        return int(monthly_repayment * n)

    factor = ((1 + r) ** n - 1) / (r * (1 + r) ** n)
    return int(monthly_repayment * factor)


def get_ltv_for_buyer(buyer_type: BuyerType, policy: LoanPolicy) -> float:
    """매수자 유형별 LTV 반환"""
    return {
        BuyerType.FIRST_TIME: policy.ltv_first_time,
        BuyerType.NO_HOUSE: policy.ltv_no_house,
        BuyerType.ONE_HOUSE: policy.ltv_one_house,
        BuyerType.MULTI_HOME: policy.ltv_multi_home,
    }.get(buyer_type, 0.0)


def get_loan_cap(price: int, policy: LoanPolicy) -> int:
    """시가별 주담대 한도 반환 (10.15 대책)"""
    if price > 250_000:
        return policy.max_loan_over_25
    elif price > 150_000:
        return policy.max_loan_15_to_25
    else:
        return policy.max_loan_under_15


def calculate_max_loan_ltv(
    seed_money: int,
    policy: LoanPolicy,
    buyer_type: BuyerType,
) -> int:
    """LTV 기반 최대 대출 가능액 계산

    시가별 한도를 고려해서 최대 대출을 구함.
    종잣돈 + 대출 = 집값, 대출 ≤ 집값 × LTV, 대출 ≤ 시가별 한도
    """
    ltv = get_ltv_for_buyer(buyer_type, policy)

    if ltv <= 0:
        return 0

    # 시가별 한도 구간별로 최대 대출을 계산
    # 종잣돈 + 대출 = 집값, 대출 = min(집값 × LTV, 한도)
    best_loan = 0
    for cap, price_limit in [
        (policy.max_loan_under_15, 150_000),
        (policy.max_loan_15_to_25, 250_000),
        (policy.max_loan_over_25, 999_999_999),
    ]:
        # 이 구간에서 가능한 최대 집값
        max_price_by_seed = seed_money + cap
        max_price_by_ltv = int(seed_money / (1 - ltv)) if ltv < 1 else 999_999_999
        max_price = min(max_price_by_seed, max_price_by_ltv, price_limit)
        loan = min(int(max_price * ltv), cap, max_price - seed_money)
        if loan > best_loan and loan >= 0:
            best_loan = loan

    return best_loan


def classify_region(max_price: int) -> list[RegionTier]:
    """최대 매수가 기반 추천 지역 분류"""
    regions = []
    for tier, (low, high) in REGION_PRICE_RANGE.items():
        if max_price >= low:
            regions.append(tier)
    return regions


def calculate_affordability(
    user: UserFinance,
    policy: LoanPolicy | None = None,
) -> AffordabilityResult:
    """종합 자금 계산 (10.15 대책 반영)"""
    if policy is None:
        policy = LoanPolicy()

    warnings: list[str] = []

    # 1) DSR 기반 대출 (기본 금리)
    max_loan_dsr = calculate_max_loan_dsr(
        user.monthly_income,
        user.existing_debt_payment,
        policy.base_interest_rate,
        policy.loan_term_years,
        policy.dsr_ratio,
    )

    # 2) 스트레스 DSR 적용 (10.15: 가산 3%)
    max_loan_dsr_stress = calculate_max_loan_dsr(
        user.monthly_income,
        user.existing_debt_payment,
        policy.effective_rate,  # 기본금리 + 스트레스 3%
        policy.loan_term_years,
        policy.dsr_ratio,
    )
    max_price_dsr = user.seed_money + max_loan_dsr_stress

    # 3) LTV 기반 대출
    max_loan_ltv = calculate_max_loan_ltv(
        user.seed_money, policy, user.buyer_type
    )

    # 4) 최종 대출 = min(스트레스DSR, LTV)
    final_loan = min(max_loan_dsr_stress, max_loan_ltv)
    final_price = user.seed_money + final_loan

    # 5) 시가별 한도 체크
    loan_cap = get_loan_cap(final_price, policy)
    loan_cap_msg = ""
    if final_loan > loan_cap:
        final_loan = loan_cap
        final_price = user.seed_money + final_loan
        loan_cap_msg = f"시가 {final_price:,}만 → 주담대 한도 {loan_cap:,}만 적용"

    # 6) 경고 생성
    if policy.land_permit_zone:
        warnings.append(
            "토지거래허가구역 (서울 전역, ~2026.12.31): "
            "2년 실거주 의무. 미거주 시 대출 거의 불가."
        )

    if user.buyer_type == BuyerType.FIRST_TIME:
        warnings.append(
            f"생애최초: 전입 {policy.require_move_in_months}개월 이내 의무. "
            f"LTV {policy.ltv_first_time*100:.0f}%."
        )

    stress_diff = max_loan_dsr - max_loan_dsr_stress
    if stress_diff > 0:
        warnings.append(
            f"스트레스 DSR 3% 적용으로 대출 {stress_diff:,}만원 감소 "
            f"(기본 {max_loan_dsr:,}만 → 스트레스 {max_loan_dsr_stress:,}만)"
        )

    if max_loan_dsr_stress > max_loan_ltv:
        warnings.append(
            f"LTV에 의해 대출 제한됨 "
            f"(DSR {max_loan_dsr_stress:,}만 vs LTV {max_loan_ltv:,}만)"
        )

    if not user.will_reside and policy.land_permit_zone:
        warnings.append(
            "실거주 안 하면 토허제 구역 대출 사실상 불가!"
        )

    regions = classify_region(final_price)

    return AffordabilityResult(
        seed_money=user.seed_money,
        monthly_saving=user.monthly_saving,
        max_loan_by_dsr=max_loan_dsr,
        max_loan_by_dsr_stress=max_loan_dsr_stress,
        max_price_by_dsr=max_price_dsr,
        max_loan_by_ltv=max_loan_ltv,
        final_max_loan=final_loan,
        final_max_price=final_price,
        loan_cap_applied=loan_cap_msg,
        recommended_regions=regions,
        warnings=warnings,
    )
