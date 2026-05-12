"""
내집마련 자금 계산기 — 2025~2026 부동산·대출 규제 누적 반영

▸ 6.27 가계부채 대책 (2025-06-27, 수도권)
  - 처분조건부 1주택자: 기존주택 6개월 내 처분 약정 필요
  - 처분조건부/무주택 LTV 40%

▸ 7월 스트레스 DSR 3단계 (2025-07)
  - 주담대 + 신용 + 기타 + 1주택자 전세대출 → 모두 DSR 반영
  - 스트레스 금리 하한 1.5% → 3% (수도권/규제지역 주담대)

▸ 10.15 부동산 대책 (2025-10-15)
  - LTV: 생애최초 70%, 무주택/처분조건부 40%, 1주택 0%
  - 시가별 한도: 15억 이하 6억, 15-25억 4억, 25억+ 2억
  - 토지거래허가구역: 서울 전역 + 경기 12곳 (~2026-12-31)
  - 실거주 의무: 2년 (토허제), 전입 6개월 (생애최초)

▸ 2026-05-12 토허구역 실거주 유예 확대 (LATEST)
  - 세 낀 매물 매수 시 입주 유예: 임대계약 종료까지, 최대 2028-05-11
  - 매수자 발표일 이후 무주택 유지 필수 (소급 X)
  - 토허 신청 마감 2026-12-31
  - 매도자(비거주 1주택) 퇴거자금대출 한도 1억
  - 갭투자 차단: 전세가율 40% 룰 (정부 명시)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class BuyerType(Enum):
    FIRST_TIME = "생애최초"       # 무주택 + 생애최초
    NO_HOUSE = "무주택"           # 무주택 일반
    HOUSE_DISPOSING = "처분조건부"  # 1주택자 6개월 내 처분 약정 (6.27)
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
    """대출 규제 정책 (2025-2026 누적 반영)"""
    # ── DSR (10.15 + 7월 3단계) ──
    dsr_ratio: float = 0.40                # 1금융권 DSR 40%
    dsr_ratio_2nd_tier: float = 0.50       # 2금융권 DSR 50%
    stress_rate: float = 0.03              # 스트레스 가산금리 3.0% (10.15: 1.5→3.0)
    base_interest_rate: float = 0.04       # 기본 금리 4%

    # ── LTV (규제지역 = 서울 전역 기준, 10.15) ──
    ltv_first_time: float = 0.70           # 생애최초 LTV 70%
    ltv_no_house: float = 0.40             # 무주택 일반 LTV 40%
    ltv_house_disposing: float = 0.40      # 처분조건부 1주택 (6.27): 무주택과 동일
    ltv_one_house: float = 0.0             # 1주택자 LTV 0% (사실상 불가)
    ltv_multi_home: float = 0.0            # 다주택자 LTV 0%

    # ── 시가별 한도 (10.15, 만원) ──
    max_loan_under_15: int = 60_000        # 15억 이하: 6억
    max_loan_15_to_25: int = 40_000        # 15-25억: 4억
    max_loan_over_25: int = 20_000         # 25억 초과: 2억

    # ── 대출 기간 ──
    loan_term_years: int = 30

    # ── 토지거래허가구역 (~2026-12-31) ──
    land_permit_zone: bool = True          # 서울 전역 기본 True
    require_move_in_months: int = 6        # 생애최초 전입 의무
    mandatory_residency_years: int = 2     # 토허제 실거주 의무

    # ── 처분조건부 (6.27) ──
    house_dispose_grace_months: int = 6    # 기존주택 처분 기한

    # ── 2026-05-12 토허 실거주 유예 ──
    deferred_residency_available: bool = True
    move_in_deadline: str = "2028-05-11"          # 입주 최후 마감
    application_deadline: str = "2026-12-31"      # 토허 신청 마감
    must_be_no_house_since: str = "2026-05-12"    # 무주택 유지 기준일
    eviction_loan_cap: int = 10_000               # 매도자 퇴거자금 한도 1억
    max_jeonse_ratio: float = 0.40                # 전세가율 상한 (갭투자 차단)

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

    # ── 7월 3단계: 1주택자 전세대출도 DSR 반영 ──
    existing_jeonse_loan_payment: int = 0  # 기존 전세대출 월상환

    # ── 2026.5.12 갭매수(세 낀 매물) 시나리오 ──
    is_gap_purchase: bool = False           # 세 낀 매물 인수 시나리오
    inherited_tenant_deposit: int = 0       # 인수 보증금 (만원)
    lease_end_date: str | None = None       # 세입자 임대계약 종료일 (YYYY-MM-DD)
    target_move_in_date: str | None = None  # 본인 입주 예정일

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
    # 최종 (실거주 시나리오)
    final_max_loan: int
    final_max_price: int
    # 시가별 한도 적용 결과
    loan_cap_applied: str = ""     # 어떤 한도가 적용됐는지
    recommended_regions: list[RegionTier] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    # ── 2026.5.12 갭매수 시나리오 결과 ──
    gap_max_price: int | None = None        # 세 낀 매물 매수 시 최대 매수가
    gap_tenant_deposit: int | None = None   # 인수해야 할 세입자 보증금
    gap_loan: int | None = None             # 본인 주담대 금액
    gap_eligible: bool = False              # 자격 통과 여부
    gap_note: str = ""                      # 상세 설명


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
        BuyerType.HOUSE_DISPOSING: policy.ltv_house_disposing,
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


# ─────────────────────────────────────
# 2026-05-12 갭매수(세 낀 매물) 시나리오
# ─────────────────────────────────────

def check_gap_purchase_eligibility(
    user: UserFinance, policy: LoanPolicy
) -> tuple[bool, list[str]]:
    """2026-05-12 토허구역 실거주 유예 정책 자격 체크

    Returns: (eligible, errors)
    """
    errors: list[str] = []

    if not policy.land_permit_zone:
        errors.append("토허구역 아닌 곳은 실거주 유예 대상 아님")

    if user.buyer_type not in (BuyerType.FIRST_TIME, BuyerType.NO_HOUSE):
        errors.append(
            f"매수자는 {policy.must_be_no_house_since}부터 계속 무주택 유지 필수 "
            f"(현재: {user.buyer_type.value})"
        )

    if user.lease_end_date and user.lease_end_date > policy.move_in_deadline:
        errors.append(
            f"임대계약 종료일({user.lease_end_date}) > "
            f"입주 데드라인({policy.move_in_deadline}) — 위반 위험"
        )

    if user.target_move_in_date and user.target_move_in_date > policy.move_in_deadline:
        errors.append(
            f"목표 입주일({user.target_move_in_date}) > "
            f"입주 데드라인({policy.move_in_deadline})"
        )

    return (len(errors) == 0, errors)


def calculate_max_price_with_gap(
    user: UserFinance, policy: LoanPolicy
) -> tuple[int, int, int, str]:
    """갭매수 시나리오 최대 매수가

    제약:
      - 매매가 = 종잣돈 + 주담대 + 세입자보증금
      - 세입자보증금 ≤ 매매가 × max_jeonse_ratio (전세가율 룰)
      - 주담대 ≤ min(매매가 × LTV, 시가별 한도)
      - 시가 구간 일관성 유지

    Returns: (max_price, tenant_deposit, my_loan, note)
    """
    ltv = get_ltv_for_buyer(user.buyer_type, policy)
    if ltv <= 0:
        return (0, 0, 0, "LTV 0% — 대출 불가")

    brackets = [
        (0, 150_000, policy.max_loan_under_15),
        (150_000, 250_000, policy.max_loan_15_to_25),
        (250_000, 10**9, policy.max_loan_over_25),
    ]

    best_price = 0
    best_deposit = 0
    best_loan = 0

    for low, high, cap in brackets:
        # 1) loan = cap 가정 → self_funded = seed + cap
        loan = cap
        self_funded = user.seed_money + loan
        # 2) 전세가율 룰: price ≤ self_funded / (1 - jeonse_ratio)
        price_by_jeonse = int(self_funded / (1 - policy.max_jeonse_ratio))
        price = min(price_by_jeonse, high)
        # 3) 구간 일관성: price가 이 bracket에 속해야 함
        if price < low:
            continue
        # 4) LTV 재검증: loan ≤ price × LTV
        loan = min(loan, int(price * ltv))
        # 5) loan 줄어들면 price도 재계산 가능
        self_funded = user.seed_money + loan
        price_by_jeonse = int(self_funded / (1 - policy.max_jeonse_ratio))
        price = min(price_by_jeonse, high)
        if price < low:
            continue
        deposit = price - user.seed_money - loan
        if deposit < 0:
            continue
        if price > best_price:
            best_price = price
            best_deposit = deposit
            best_loan = loan

    if best_price == 0:
        return (0, 0, 0, "갭매수 시나리오 산출 실패 — 종잣돈/LTV 점검 필요")

    ratio = best_deposit / best_price * 100 if best_price else 0
    note = (
        f"종잣돈 {user.seed_money:,}만 + 주담대 {best_loan:,}만 "
        f"+ 세입자보증금 {best_deposit:,}만 = 매매가 {best_price:,}만 "
        f"(전세가율 {ratio:.1f}%)"
    )
    return (best_price, best_deposit, best_loan, note)


# ─────────────────────────────────────
# 지역 분류
# ─────────────────────────────────────

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
    """종합 자금 계산 (2025-2026 대책 누적 반영)"""
    if policy is None:
        policy = LoanPolicy()

    warnings: list[str] = []

    # ── 7월 3단계: 1주택 전세대출도 DSR 합산 ──
    total_existing_debt = (
        user.existing_debt_payment + user.existing_jeonse_loan_payment
    )

    # 1) DSR 기반 대출 (기본 금리)
    max_loan_dsr = calculate_max_loan_dsr(
        user.monthly_income,
        total_existing_debt,
        policy.base_interest_rate,
        policy.loan_term_years,
        policy.dsr_ratio,
    )

    # 2) 스트레스 DSR (10.15: 가산 3%)
    max_loan_dsr_stress = calculate_max_loan_dsr(
        user.monthly_income,
        total_existing_debt,
        policy.effective_rate,
        policy.loan_term_years,
        policy.dsr_ratio,
    )
    max_price_dsr = user.seed_money + max_loan_dsr_stress

    # 3) LTV 기반 대출
    max_loan_ltv = calculate_max_loan_ltv(
        user.seed_money, policy, user.buyer_type
    )

    # 4) 실거주 시나리오 최종 = min(DSR, LTV)
    final_loan = min(max_loan_dsr_stress, max_loan_ltv)
    final_price = user.seed_money + final_loan

    # 5) 시가별 한도
    loan_cap = get_loan_cap(final_price, policy)
    loan_cap_msg = ""
    if final_loan > loan_cap:
        final_loan = loan_cap
        final_price = user.seed_money + final_loan
        loan_cap_msg = f"시가 {final_price:,}만 → 주담대 한도 {loan_cap:,}만 적용"

    # 6) 경고
    if policy.land_permit_zone:
        warnings.append(
            f"토허구역 (서울 전역+경기12곳, ~{policy.application_deadline}): "
            f"{policy.mandatory_residency_years}년 실거주 의무"
        )

    if user.buyer_type == BuyerType.FIRST_TIME:
        warnings.append(
            f"생애최초: 전입 {policy.require_move_in_months}개월 이내, "
            f"LTV {policy.ltv_first_time*100:.0f}%"
        )
    elif user.buyer_type == BuyerType.HOUSE_DISPOSING:
        warnings.append(
            f"처분조건부 1주택 (6.27): 기존주택 "
            f"{policy.house_dispose_grace_months}개월 내 처분 약정 필수"
        )

    stress_diff = max_loan_dsr - max_loan_dsr_stress
    if stress_diff > 0:
        warnings.append(
            f"스트레스 DSR {policy.stress_rate*100:.0f}% 적용으로 "
            f"대출 {stress_diff:,}만 감소 "
            f"(기본 {max_loan_dsr:,} → 스트레스 {max_loan_dsr_stress:,})"
        )

    if user.existing_jeonse_loan_payment > 0:
        warnings.append(
            f"1주택 전세대출 월상환 {user.existing_jeonse_loan_payment:,}만 "
            f"DSR 합산 (7월 3단계)"
        )

    if max_loan_dsr_stress > max_loan_ltv:
        warnings.append(
            f"LTV 제한 (DSR {max_loan_dsr_stress:,} vs LTV {max_loan_ltv:,})"
        )

    if not user.will_reside and policy.land_permit_zone and not user.is_gap_purchase:
        warnings.append("토허구역 실거주 안 하면 대출 거의 불가 (갭매수 시나리오 필요)")

    # 7) 2026-05-12 갭매수 시나리오 계산
    gap_max_price: int | None = None
    gap_tenant_deposit: int | None = None
    gap_loan: int | None = None
    gap_eligible = False
    gap_note = ""

    if user.is_gap_purchase:
        eligible, gap_errors = check_gap_purchase_eligibility(user, policy)
        gap_eligible = eligible
        if not eligible:
            warnings.extend([f"❌ 갭매수 자격 미달: {e}" for e in gap_errors])
        else:
            gap_max_price, gap_tenant_deposit, gap_loan, gap_note = (
                calculate_max_price_with_gap(user, policy)
            )
            warnings.append(f"📌 갭매수 시나리오: {gap_note}")
            warnings.append(
                f"입주 데드라인 {policy.move_in_deadline} → "
                f"이후 {policy.mandatory_residency_years}년 실거주 의무"
            )
            warnings.append(
                f"토허 신청 마감 {policy.application_deadline}, "
                f"{policy.must_be_no_house_since} 이후 무주택 유지 필수"
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
        gap_max_price=gap_max_price,
        gap_tenant_deposit=gap_tenant_deposit,
        gap_loan=gap_loan,
        gap_eligible=gap_eligible,
        gap_note=gap_note,
    )
