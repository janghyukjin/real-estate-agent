"""전세가율 & 갭투자 분석 테스트"""

from src.kb_client import analyze_gap, calculate_jeonse_ratio, grade_gap_investment


def test_jeonse_ratio():
    """전세가율 계산 테스트"""
    cases = [
        # (매매가, 전세가, 기대 전세가율, 기대 등급 키워드)
        (90000, 63000, 70.0, "적정"),     # 9억/6.3억 = 70%, 갭 2.7억 → 적정
        (50000, 40000, 80.0, "위험"),     # 5억/4억 = 80% → 역전세 위험
        (120000, 60000, 50.0, "갭 큼"),    # 12억/6억 = 50% → 갭 큼
        (70000, 45500, 65.0, "자본금"),    # 7억/4.55억 = 65%, 갭 2.45억 → 자본금 다소 필요
    ]

    for trade, jeonse, expected_ratio, expected_keyword in cases:
        ratio = calculate_jeonse_ratio(trade, jeonse)
        grade = grade_gap_investment(ratio, trade - jeonse)
        print(
            f"매매 {trade:>7,}만 | 전세 {jeonse:>7,}만 | "
            f"갭 {trade-jeonse:>6,}만 | 전세가율 {ratio}% | {grade}"
        )
        assert abs(ratio - expected_ratio) < 1.0, f"Expected ~{expected_ratio}, got {ratio}"
        assert expected_keyword in grade, f"Expected '{expected_keyword}' in '{grade}'"

    print("\n✅ 전세가율 테스트 통과")


def test_gap_analysis():
    """갭투자 종합 분석 테스트"""
    # 노원구 포레나노원 예시 (스크린샷 기반)
    result = analyze_gap(
        apt_name="포레나노원",
        region="노원구",
        trade_price=98500,   # 매매 9.85억
        jeonse_price=55000,  # 전세 5.5억 (가정)
    )
    print(f"\n📊 {result.apt_name} ({result.region})")
    print(f"   매매가: {result.trade_price:,}만")
    print(f"   전세가: {result.jeonse_price:,}만")
    print(f"   갭: {result.gap:,}만")
    print(f"   전세가율: {result.jeonse_ratio}%")
    print(f"   등급: {result.investment_grade}")
    print()

    # 서대문 연희파크푸르지오 예시
    result2 = analyze_gap(
        apt_name="연희파크푸르지오",
        region="서대문구",
        trade_price=100000,
        jeonse_price=62000,
    )
    print(f"📊 {result2.apt_name} ({result2.region})")
    print(f"   매매가: {result2.trade_price:,}만")
    print(f"   전세가: {result2.jeonse_price:,}만")
    print(f"   갭: {result2.gap:,}만")
    print(f"   전세가율: {result2.jeonse_ratio}%")
    print(f"   등급: {result2.investment_grade}")

    print("\n✅ 갭투자 분석 테스트 통과")


if __name__ == "__main__":
    test_jeonse_ratio()
    print()
    test_gap_analysis()
