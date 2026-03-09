"""
API 키 발급 후 실제 연동 테스트

사용법:
  export DATA_GO_KR_API_KEY="발급받은키"
  python3 -m tests.test_api_live
"""

import asyncio
import os
import sys


async def test_apt_trade():
    """아파트 매매 실거래가 API 테스트 (노원구 최근 1개월)"""
    from src.api_client import fetch_apt_trades, REGION_CODES, trades_to_dataframe

    print("=" * 60)
    print("1️⃣  아파트 매매 실거래가 테스트 (노원구)")
    print("=" * 60)

    code = REGION_CODES["노원구"]
    from datetime import datetime
    ymd = datetime.now().strftime("%Y%m")

    trades = await fetch_apt_trades(code, ymd)
    print(f"   조회 기간: {ymd}")
    print(f"   거래 건수: {len(trades)}건")

    if trades:
        df = trades_to_dataframe(trades)
        print(f"\n   최근 거래 TOP 5:")
        for _, row in df.head(5).iterrows():
            print(
                f"   - {row['아파트']} | {row['거래금액(만원)']:,}만원 | "
                f"{row['전용면적(㎡)']}㎡ | {row['층']}층"
            )
    else:
        print("   ⚠️ 이번 달 데이터가 아직 없을 수 있음 (전월로 재시도)")
        from datetime import timedelta
        prev = datetime.now() - timedelta(days=35)
        ymd2 = prev.strftime("%Y%m")
        trades2 = await fetch_apt_trades(code, ymd2)
        print(f"   {ymd2} 조회: {len(trades2)}건")
        if trades2:
            df2 = trades_to_dataframe(trades2)
            for _, row in df2.head(5).iterrows():
                print(
                    f"   - {row['아파트']} | {row['거래금액(만원)']:,}만원 | "
                    f"{row['전용면적(㎡)']}㎡ | {row['층']}층"
                )

    return len(trades) > 0


async def test_apt_rent():
    """아파트 전월세 실거래가 API 테스트"""
    from src.api_client import fetch_apt_rents, REGION_CODES

    print("\n" + "=" * 60)
    print("2️⃣  아파트 전월세 실거래가 테스트 (노원구)")
    print("=" * 60)

    code = REGION_CODES["노원구"]
    from datetime import datetime, timedelta
    prev = datetime.now() - timedelta(days=35)
    ymd = prev.strftime("%Y%m")

    rents = await fetch_apt_rents(code, ymd)
    jeonse = [r for r in rents if r.rent_type == "전세"]
    wolse = [r for r in rents if r.rent_type == "월세"]

    print(f"   조회 기간: {ymd}")
    print(f"   전세: {len(jeonse)}건 / 월세: {len(wolse)}건")

    if jeonse:
        print(f"\n   전세 TOP 5:")
        jeonse.sort(key=lambda x: x.deposit, reverse=True)
        for r in jeonse[:5]:
            print(
                f"   - {r.apt_name} | 보증금 {r.deposit:,}만원 | "
                f"{r.area}㎡ | {r.floor}층"
            )

    return len(rents) > 0


async def test_gap_analysis():
    """실거래가 기반 갭투자 분석 테스트"""
    from src.api_client import fetch_recent_trades, fetch_recent_rents, REGION_CODES
    from src.kb_client import analyze_area_gap

    print("\n" + "=" * 60)
    print("3️⃣  갭투자 분석 테스트 (노원구, 최근 3개월)")
    print("=" * 60)

    code = REGION_CODES["노원구"]
    trades = await fetch_recent_trades(code, months=3)
    rents = await fetch_recent_rents(code, months=3, jeonse_only=True)

    print(f"   매매 거래: {len(trades)}건")
    print(f"   전세 거래: {len(rents)}건")

    df = await analyze_area_gap(trades, rents)
    if not df.empty:
        print(f"\n   갭투자 분석 (전세가율 높은 순 TOP 5):")
        for _, row in df.head(5).iterrows():
            print(
                f"   - {row['아파트']} | 매매 {row['평균매매가(만원)']:,}만 | "
                f"전세 {row['평균전세가(만원)']:,}만 | "
                f"갭 {row['갭(만원)']:,}만 | "
                f"전세가율 {row['전세가율(%)']}% | {row['투자등급']}"
            )
    return not df.empty


async def test_user_scenario():
    """유저 시나리오 통합 테스트"""
    from src.calculator import BuyerType, UserFinance, calculate_affordability
    from src.api_client import fetch_recent_trades, REGION_CODES, filter_by_budget, trades_to_dataframe
    from src.building_ledger import is_large_complex

    print("\n" + "=" * 60)
    print("4️⃣  통합 시나리오: 자금 6억 / 월급 600 / 생애최초 / 300세대+")
    print("=" * 60)

    # 1) 예산 계산
    user = UserFinance(
        seed_money=60000, monthly_income=600, monthly_expense=150,
        buyer_type=BuyerType.FIRST_TIME, will_reside=True,
    )
    result = calculate_affordability(user)
    budget_max = result.final_max_price
    budget_min = max(budget_max - 30000, 0)

    print(f"\n   매수 가능 집값: {result.final_max_price:,}만원 ({result.final_max_price/10000:.1f}억)")
    print(f"   검색 범위: {budget_min:,}만 ~ {budget_max:,}만")

    # 2) 노원구 실거래가 조회
    code = REGION_CODES["노원구"]
    trades = await fetch_recent_trades(code, months=3)
    filtered = filter_by_budget(trades, budget_min, budget_max)

    print(f"\n   노원구 예산 범위 내 거래: {len(filtered)}건")

    if filtered:
        df = trades_to_dataframe(filtered)
        # 아파트별 그룹핑
        apt_summary = (
            df.groupby("아파트")
            .agg({
                "거래금액(만원)": ["mean", "min", "max", "count"],
            })
            .round(0)
        )
        apt_summary.columns = ["평균가", "최저가", "최고가", "거래건수"]
        apt_summary = apt_summary.sort_values("거래건수", ascending=False)

        print(f"\n   아파트별 요약 (300세대+ 필터):")
        for apt_name, row in apt_summary.head(10).iterrows():
            large = is_large_complex(apt_name, 300)
            marker = "✅" if large else ("❌" if large is False else "❓")
            print(
                f"   {marker} {apt_name} | {row['평균가']:,.0f}만 "
                f"({row['최저가']:,.0f}~{row['최고가']:,.0f}) | "
                f"{row['거래건수']:.0f}건"
            )


async def main():
    api_key = os.environ.get("DATA_GO_KR_API_KEY", "")
    if not api_key:
        print("❌ DATA_GO_KR_API_KEY 환경변수를 설정해주세요!")
        print()
        print("   export DATA_GO_KR_API_KEY='발급받은키'")
        print("   python3 -m tests.test_api_live")
        sys.exit(1)

    print(f"🔑 API 키: {api_key[:10]}...{api_key[-5:]}")
    print()

    ok1 = await test_apt_trade()
    ok2 = await test_apt_rent()

    if ok1 and ok2:
        await test_gap_analysis()
        await test_user_scenario()

    print("\n" + "=" * 60)
    print("✅ 테스트 완료!" if ok1 else "⚠️ API 응답 확인 필요")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
