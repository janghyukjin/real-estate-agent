"""2026-05-12 토허구역 실거주 유예 정책 테스트

신규 정책:
- 세 낀 매물 매수 시 입주 유예 (최대 2028-05-11)
- 매수자 무주택 유지 필수
- 갭투자 차단: 전세가율 40% 룰
"""

from src.calculator import (
    BuyerType,
    LoanPolicy,
    UserFinance,
    calculate_affordability,
    calculate_max_price_with_gap,
    check_gap_purchase_eligibility,
)


def test_eligibility_first_time_ok():
    """생애최초 + 조건 모두 충족 → 자격 통과"""
    user = UserFinance(
        seed_money=60_000,
        monthly_income=1_025,
        monthly_expense=200,
        buyer_type=BuyerType.FIRST_TIME,
        is_gap_purchase=True,
        lease_end_date="2028-04-30",
        target_move_in_date="2028-05-01",
    )
    policy = LoanPolicy()
    eligible, errs = check_gap_purchase_eligibility(user, policy)
    assert eligible, f"기대: 통과, 실제 오류: {errs}"
    print("✅ 생애최초 + 임대만료 2028-04-30 → 자격 통과")


def test_eligibility_one_house_rejected():
    """1주택자 (HOUSE_DISPOSING이 아닌 일반 1주택) → 자격 X"""
    user = UserFinance(
        seed_money=60_000,
        monthly_income=1_025,
        monthly_expense=200,
        buyer_type=BuyerType.ONE_HOUSE,
        is_gap_purchase=True,
        lease_end_date="2028-04-30",
    )
    policy = LoanPolicy()
    eligible, errs = check_gap_purchase_eligibility(user, policy)
    assert not eligible
    assert any("무주택" in e for e in errs)
    print(f"✅ 1주택자 → 자격 거절 ({errs[0][:40]}...)")


def test_eligibility_late_lease_rejected():
    """임대계약 종료가 2028-05-11 이후 → 자격 X"""
    user = UserFinance(
        seed_money=60_000,
        monthly_income=1_025,
        monthly_expense=200,
        buyer_type=BuyerType.FIRST_TIME,
        is_gap_purchase=True,
        lease_end_date="2028-08-01",
    )
    policy = LoanPolicy()
    eligible, errs = check_gap_purchase_eligibility(user, policy)
    assert not eligible
    assert any("임대계약" in e for e in errs)
    print(f"✅ 임대 만료 2028-08-01 → 자격 거절")


def test_eligibility_non_toho_rejected():
    """토허구역 아님 → 자격 X"""
    user = UserFinance(
        seed_money=60_000,
        monthly_income=1_025,
        monthly_expense=200,
        buyer_type=BuyerType.FIRST_TIME,
        is_gap_purchase=True,
        lease_end_date="2028-04-30",
    )
    policy = LoanPolicy(land_permit_zone=False)
    eligible, errs = check_gap_purchase_eligibility(user, policy)
    assert not eligible
    assert any("토허" in e for e in errs)
    print(f"✅ 토허구역 외 → 자격 거절")


def test_max_price_user_scenario():
    """유저 케이스: 종잣돈 6억, 생애최초, 갭매수

    예상:
    - 15-25억 bracket cap 4억 활용
    - self_funded = 6 + 4 = 10억
    - max price by jeonse = 10/0.6 = 16.67억
    - tenant deposit = 6.67억 (40%)
    """
    user = UserFinance(
        seed_money=60_000,
        monthly_income=1_025,
        monthly_expense=200,
        buyer_type=BuyerType.FIRST_TIME,
        is_gap_purchase=True,
        lease_end_date="2028-04-30",
    )
    policy = LoanPolicy()
    price, deposit, loan, note = calculate_max_price_with_gap(user, policy)

    print(f"\n📌 갭매수 시나리오 (종잣돈 6억, 생애최초):")
    print(f"   {note}")
    print(f"   매매가 {price/10000:.2f}억 | 갭 {deposit/10000:.2f}억 | 주담대 {loan/10000:.2f}억")

    # 결과 검증
    assert price > 0
    assert 150_000 <= price <= 250_000, f"15-25억 bracket 예상, 실제: {price}"
    assert loan == 40_000, f"주담대 4억 예상, 실제: {loan}"
    assert abs(deposit / price - 0.40) < 0.01, f"전세가율 ~40% 예상, 실제 {deposit/price*100:.1f}%"


def test_max_price_no_seed():
    """종잣돈 0 케이스 — 갭매수 불가능에 가까움"""
    user = UserFinance(
        seed_money=0,
        monthly_income=1_025,
        monthly_expense=200,
        buyer_type=BuyerType.FIRST_TIME,
        is_gap_purchase=True,
        lease_end_date="2028-04-30",
    )
    policy = LoanPolicy()
    price, deposit, loan, note = calculate_max_price_with_gap(user, policy)
    # 종잣돈 0 → self_funded = loan, max price = loan / 0.6
    # bracket-15: cap 6억, self_funded 6, price 10억 (<15) ✓
    # bracket-15-25: cap 4억, self_funded 4, price 6.67 (<15) → 부합 X
    # bracket-25+: cap 2억, self_funded 2, price 3.33 (<25) → 부합 X
    # → 10억대 가능
    print(f"\n📌 종잣돈 0 케이스: {note}")
    assert price > 0


def test_full_affordability_with_gap():
    """calculate_affordability 통합 — 유저 시나리오 (갭매수 포함)"""
    user = UserFinance(
        seed_money=60_000,
        monthly_income=1_025,       # 작년 원징 1.23억 / 12
        monthly_expense=200,         # 가정
        buyer_type=BuyerType.FIRST_TIME,
        is_gap_purchase=True,
        lease_end_date="2028-04-30",
        target_move_in_date="2028-05-01",
    )
    result = calculate_affordability(user)

    print("\n" + "=" * 70)
    print("📋 유저 시나리오 (2026-05-12 갭매수 정책)")
    print("=" * 70)
    print(f"종잣돈: {result.seed_money:,}만 ({result.seed_money/10000:.1f}억)")
    print(f"월저축: {result.monthly_saving:,}만")
    print()
    print(f"[실거주 시나리오]")
    print(f"  DSR 스트레스 대출: {result.max_loan_by_dsr_stress:,}만")
    print(f"  LTV 대출: {result.max_loan_by_ltv:,}만")
    print(f"  최종 대출: {result.final_max_loan:,}만 ({result.final_max_loan/10000:.1f}억)")
    print(f"  매수가능 집값: {result.final_max_price:,}만 ({result.final_max_price/10000:.2f}억)")
    if result.loan_cap_applied:
        print(f"  적용: {result.loan_cap_applied}")
    print()
    print(f"[갭매수 시나리오 - 2026.5.12 정책]")
    print(f"  자격: {'✅ 통과' if result.gap_eligible else '❌ 미달'}")
    if result.gap_eligible:
        print(f"  매수가능 매매가: {result.gap_max_price:,}만 ({result.gap_max_price/10000:.2f}억)")
        print(f"  본인 주담대: {result.gap_loan:,}만 ({result.gap_loan/10000:.1f}억)")
        print(f"  인수 보증금: {result.gap_tenant_deposit:,}만 ({result.gap_tenant_deposit/10000:.2f}억)")
        print(f"  전세가율: {result.gap_tenant_deposit/result.gap_max_price*100:.1f}%")
    print()
    print(f"[경고/안내]")
    for w in result.warnings:
        print(f"  - {w}")

    assert result.gap_eligible
    assert result.gap_max_price > result.final_max_price, "갭매수가 실거주보다 매수가 커야 함"


def test_jeonse_loan_dsr_impact():
    """1주택자 전세대출 → DSR에 합산되어 대출 감소 (7월 3단계)"""
    base_user = UserFinance(
        seed_money=60_000,
        monthly_income=1_025,
        monthly_expense=200,
        buyer_type=BuyerType.FIRST_TIME,
    )
    with_jeonse_loan = UserFinance(
        seed_money=60_000,
        monthly_income=1_025,
        monthly_expense=200,
        buyer_type=BuyerType.FIRST_TIME,
        existing_jeonse_loan_payment=100,   # 월 100만 전세대출 상환
    )

    base = calculate_affordability(base_user)
    with_loan = calculate_affordability(with_jeonse_loan)

    print(f"\n📊 전세대출 DSR 영향:")
    print(f"  전세대출 없음: DSR 대출 {base.max_loan_by_dsr_stress:,}만")
    print(f"  전세대출 100만/월: DSR 대출 {with_loan.max_loan_by_dsr_stress:,}만")
    print(f"  → 감소 {base.max_loan_by_dsr_stress - with_loan.max_loan_by_dsr_stress:,}만")

    assert with_loan.max_loan_by_dsr_stress < base.max_loan_by_dsr_stress, "전세대출 합산으로 대출 감소해야 함"


def test_house_disposing_buyer():
    """처분조건부 1주택 (6.27): LTV 40% 적용"""
    user = UserFinance(
        seed_money=60_000,
        monthly_income=1_025,
        monthly_expense=200,
        buyer_type=BuyerType.HOUSE_DISPOSING,
    )
    result = calculate_affordability(user)

    print(f"\n📊 처분조건부 1주택자 (6.27):")
    print(f"  최종 대출: {result.final_max_loan:,}만 ({result.final_max_loan/10000:.1f}억)")
    print(f"  매수가능: {result.final_max_price:,}만 ({result.final_max_price/10000:.1f}억)")
    has_dispose_warning = any("처분조건부" in w for w in result.warnings)
    assert has_dispose_warning
    print(f"  ✅ 6.27 처분 약정 경고 포함")


if __name__ == "__main__":
    test_eligibility_first_time_ok()
    test_eligibility_one_house_rejected()
    test_eligibility_late_lease_rejected()
    test_eligibility_non_toho_rejected()
    test_max_price_user_scenario()
    test_max_price_no_seed()
    test_full_affordability_with_gap()
    test_jeonse_loan_dsr_impact()
    test_house_disposing_buyer()
    print("\n✅ 모든 테스트 통과")
