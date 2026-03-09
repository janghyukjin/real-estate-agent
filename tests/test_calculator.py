"""자금 계산기 테스트"""

from src.calculator import (
    BuyerType,
    LoanPolicy,
    UserFinance,
    calculate_affordability,
    calculate_max_loan_dsr,
    calculate_max_loan_ltv,
)


def test_basic_calculation():
    """기본 계산 테스트 - 표의 예시와 비교"""
    # 표 예시: 종잣돈 15000, 월소득 400, 월지출 200
    # → 대출1(DSR) 26667, 집값 41667
    user = UserFinance(
        seed_money=15000,
        monthly_income=400,
        monthly_expense=200,
        buyer_type=BuyerType.FIRST_TIME,
    )
    result = calculate_affordability(user)

    print(f"종잣돈: {result.seed_money:,}")
    print(f"월저축: {result.monthly_saving:,}")
    print(f"DSR 최대대출: {result.max_loan_by_dsr:,}")
    print(f"LTV 최대대출: {result.max_loan_by_ltv:,}")
    print(f"최종 대출: {result.final_max_loan:,}")
    print(f"최종 집값: {result.final_max_price:,}")
    print(f"추천지역: {[r.value for r in result.recommended_regions]}")
    print(f"경고: {result.warnings}")
    print()


def test_table_samples():
    """제공된 표의 여러 케이스 테스트"""
    # (종잣돈, 월소득, 월지출, 표의_대출1_DSR, 표의_집값)
    # 표의 계산은 단순화된 공식 사용 (소득-지출)*12/0.09 형태
    test_cases = [
        (3000, 200, 100, "소액투자로 종잣돈 불리기"),
        (10000, 400, 200, "지금 경기 내집마련"),
        (20000, 400, 200, "지금 서울 하급지 혹은 경기 내집마련"),
        (30000, 700, 350, "지금 서울 중하급지 내집마련"),
        (50000, 800, 400, "지금 서울 중상급지 내집마련"),
    ]

    for seed, income, expense, expected_advice in test_cases:
        user = UserFinance(
            seed_money=seed,
            monthly_income=income,
            monthly_expense=expense,
            buyer_type=BuyerType.FIRST_TIME,
        )
        result = calculate_affordability(user)
        regions = [r.value for r in result.recommended_regions]
        print(
            f"종잣돈 {seed:>6,} | 소득 {income:>4} | "
            f"최종집값 {result.final_max_price:>7,}만 | "
            f"지역: {regions}"
        )
        print(f"  기대: {expected_advice}")
        print()


if __name__ == "__main__":
    test_basic_calculation()
    print("=" * 60)
    test_table_samples()
