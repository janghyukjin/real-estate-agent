"""10.15 부동산 대책 반영 테스트 + 유저 시나리오 시뮬레이션"""

from src.calculator import (
    BuyerType,
    LoanPolicy,
    UserFinance,
    calculate_affordability,
)
from src.building_ledger import (
    get_household_count,
    is_large_complex,
    APT_HOUSEHOLD_CACHE,
)


def test_user_scenario():
    """
    유저 조건:
    - 자금 6억, 월급 600, 월지출 150 (월 450 저축 + 인센)
    - 생애최초, 실거주
    - 300세대 이상 아파트만
    """
    print("=" * 70)
    print("📋 유저 시나리오: 자금 6억 / 월급 600 / 월저축 450 / 생애최초")
    print("=" * 70)

    user = UserFinance(
        seed_money=60000,        # 6억
        monthly_income=600,      # 월 600만
        monthly_expense=150,     # 월 150만 (450 저축)
        buyer_type=BuyerType.FIRST_TIME,
        will_reside=True,
    )
    policy = LoanPolicy()  # 10.15 대책 기본값

    result = calculate_affordability(user, policy)

    print(f"\n💰 자금 분석 (10.15 대책 반영)")
    print(f"   종잣돈: {result.seed_money:,}만원")
    print(f"   월저축: {result.monthly_saving:,}만원")
    print()
    print(f"📊 대출 분석")
    print(f"   DSR 기본금리(4%): {result.max_loan_by_dsr:,}만원")
    print(f"   DSR 스트레스(7%): {result.max_loan_by_dsr_stress:,}만원")
    print(f"   → 스트레스 가산으로 {result.max_loan_by_dsr - result.max_loan_by_dsr_stress:,}만원 감소!")
    print(f"   LTV 70%(생애최초): {result.max_loan_by_ltv:,}만원")
    print()
    print(f"🏠 최종 결과")
    print(f"   최종 대출: {result.final_max_loan:,}만원")
    print(f"   매수 가능 집값: {result.final_max_price:,}만원 ({result.final_max_price/10000:.1f}억)")
    if result.loan_cap_applied:
        print(f"   시가별 한도: {result.loan_cap_applied}")
    print(f"   추천 지역: {[r.value for r in result.recommended_regions]}")
    print()
    print(f"⚠️  주의사항:")
    for w in result.warnings:
        print(f"   - {w}")

    # 300세대 이상 필터링
    print(f"\n🏢 300세대 이상 아파트 필터링:")
    budget_max = result.final_max_price
    budget_min = max(budget_max - 30000, 0)  # 최종집값 -3억 범위

    large_apts = {
        name: count for name, count in APT_HOUSEHOLD_CACHE.items()
        if count >= 300
    }
    print(f"   캐시된 300세대+ 아파트: {len(large_apts)}개")
    for name, count in sorted(large_apts.items(), key=lambda x: x[1], reverse=True)[:10]:
        print(f"   - {name}: {count:,}세대")


def test_10_15_impact():
    """10.15 대책 전후 비교"""
    print("\n" + "=" * 70)
    print("📊 10.15 대책 전후 비교 (같은 유저 조건)")
    print("=" * 70)

    user = UserFinance(
        seed_money=60000,
        monthly_income=600,
        monthly_expense=150,
        buyer_type=BuyerType.FIRST_TIME,
        will_reside=True,
    )

    # 10.15 이전 (구 규제)
    old_policy = LoanPolicy(
        stress_rate=0.015,        # 스트레스 1.5%
        ltv_first_time=0.80,      # 생애최초 80%
        ltv_no_house=0.70,        # 무주택 70%
        max_loan_under_15=60000,  # 일괄 6억
        max_loan_15_to_25=60000,
        max_loan_over_25=60000,
        land_permit_zone=False,
    )

    # 10.15 이후 (신 규제)
    new_policy = LoanPolicy()  # 기본값 = 10.15 대책

    old_result = calculate_affordability(user, old_policy)
    new_result = calculate_affordability(user, new_policy)

    print(f"\n{'항목':<25} {'10.15 이전':>15} {'10.15 이후':>15} {'차이':>12}")
    print("-" * 70)
    print(f"{'스트레스 가산금리':<25} {'1.5%':>15} {'3.0%':>15} {'':>12}")
    print(f"{'생애최초 LTV':<25} {'80%':>15} {'70%':>15} {'':>12}")
    print(f"{'DSR 최대대출(기본)':<25} {old_result.max_loan_by_dsr:>13,}만 {new_result.max_loan_by_dsr:>13,}만 {'동일':>12}")
    print(f"{'DSR 최대대출(스트레스)':<25} {old_result.max_loan_by_dsr_stress:>13,}만 {new_result.max_loan_by_dsr_stress:>13,}만 {new_result.max_loan_by_dsr_stress - old_result.max_loan_by_dsr_stress:>+10,}만")
    print(f"{'LTV 최대대출':<25} {old_result.max_loan_by_ltv:>13,}만 {new_result.max_loan_by_ltv:>13,}만 {new_result.max_loan_by_ltv - old_result.max_loan_by_ltv:>+10,}만")
    print(f"{'최종 대출':<25} {old_result.final_max_loan:>13,}만 {new_result.final_max_loan:>13,}만 {new_result.final_max_loan - old_result.final_max_loan:>+10,}만")
    print(f"{'매수가능 집값':<25} {old_result.final_max_price:>13,}만 {new_result.final_max_price:>13,}만 {new_result.final_max_price - old_result.final_max_price:>+10,}만")
    print(f"{'':>25} {'':>15} {'':>15} {(new_result.final_max_price - old_result.final_max_price)/10000:>+10.1f}억")


def test_buyer_types():
    """매수자 유형별 비교"""
    print("\n" + "=" * 70)
    print("📊 매수자 유형별 비교 (종잣돈 6억, 월소득 600)")
    print("=" * 70)

    for bt in BuyerType:
        user = UserFinance(
            seed_money=60000,
            monthly_income=600,
            monthly_expense=150,
            buyer_type=bt,
            will_reside=True,
        )
        result = calculate_affordability(user)
        print(
            f"  {bt.value:<8} | 대출 {result.final_max_loan:>7,}만 | "
            f"집값 {result.final_max_price:>8,}만 ({result.final_max_price/10000:.1f}억) | "
            f"지역: {[r.value for r in result.recommended_regions]}"
        )


if __name__ == "__main__":
    test_user_scenario()
    test_10_15_impact()
    test_buyer_types()
