"""
🏠 내집마련 AI 비서 — 웹앱
Streamlit 기반 프로토타입
"""
import streamlit as st
import json
import os
import sys

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(__file__))

from src.calculator import (
    BuyerType, LoanPolicy, UserFinance, calculate_affordability,
)

# ─────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────
st.set_page_config(
    page_title="내집마련 AI 비서",
    page_icon="🏠",
    layout="wide",
)

st.title("🏠 내집마련 AI 비서")
st.caption("내 월급으로 서울 어디 살 수 있을까?")

# ─────────────────────────────────────
# 사이드바: 유저 입력
# ─────────────────────────────────────
with st.sidebar:
    st.header("📋 내 조건 입력")

    seed_money_억 = st.number_input(
        "종잣돈 (억원)", min_value=0.0, max_value=50.0, value=6.0, step=0.5,
        help="현재 보유 현금 + 예금 + 주식 등 동원 가능한 총 금액"
    )
    seed_money = int(seed_money_억 * 10000)

    annual_income = st.number_input(
        "연봉 / 원천징수 (만원)", min_value=2000, max_value=100000, value=12300, step=100,
        help="작년 원천징수영수증 기준 총급여"
    )
    monthly_income = annual_income // 12

    annual_saving_억 = st.number_input(
        "연간 저축액 (억원)", min_value=0.0, max_value=10.0, value=1.0, step=0.1,
        help="인센티브 포함 실제 연간 저축 가능 금액"
    )

    buyer_type = st.selectbox(
        "매수자 유형",
        options=[BuyerType.FIRST_TIME, BuyerType.NO_HOUSE, BuyerType.ONE_HOUSE],
        format_func=lambda x: x.value,
        help="생애최초: LTV 70% / 무주택: LTV 40% / 1주택: LTV 0%"
    )

    will_reside = st.checkbox("실거주 예정", value=True)

    interest_rate = st.slider(
        "예상 대출 금리 (%)", min_value=2.5, max_value=6.0, value=4.0, step=0.1,
    )

    st.divider()
    st.caption("10.15 부동산 대책 반영 (2025.10.15~)")
    st.caption("스트레스 DSR 3% / 토허제 서울전역")

# ─────────────────────────────────────
# 자금 계산
# ─────────────────────────────────────
policy = LoanPolicy(base_interest_rate=interest_rate / 100)
user = UserFinance(
    seed_money=seed_money,
    monthly_income=monthly_income,
    monthly_expense=150,  # 기본값
    buyer_type=buyer_type,
    will_reside=will_reside,
)
result = calculate_affordability(user, policy)

# ─────────────────────────────────────
# 메인: 결과 표시
# ─────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("💰 매수 가능 집값", f"{result.final_max_price / 10000:.1f}억원")
with col2:
    st.metric("🏦 최대 대출", f"{result.final_max_loan / 10000:.1f}억원")
with col3:
    # 월 상환 계산
    loan = result.final_max_loan
    mr = (interest_rate / 100) / 12
    n = 360
    if loan > 0 and mr > 0:
        monthly_pay = loan * (mr * (1 + mr) ** n) / ((1 + mr) ** n - 1)
    else:
        monthly_pay = 0
    st.metric("📅 월 상환액", f"{monthly_pay:,.0f}만원")
with col4:
    ratio = monthly_pay / monthly_income * 100 if monthly_income > 0 else 0
    st.metric("📊 월급 대비", f"{ratio:.1f}%")

# 경고
for w in result.warnings:
    st.warning(w)

st.divider()

# ─────────────────────────────────────
# 탭 구성
# ─────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🏆 TOP 10 추천", "📈 연도별 로드맵", "🏦 대출 상환 시뮬레이션"])

# ─────────────────────────────────────
# TAB 1: TOP 10
# ─────────────────────────────────────
with tab1:
    st.subheader("내 예산 맞춤 TOP 10 아파트")
    st.caption(f"예산 범위: {result.final_max_price/10000:.1f}억 이하 / 25~34평 / 300세대+")

    # 캐시된 분석 결과 로드
    analysis_path = os.path.join(os.path.dirname(__file__), "data", "analysis.json")
    cache_path = os.path.join(os.path.dirname(__file__), "data", "apt_cache.json")

    if os.path.exists(analysis_path) and os.path.exists(cache_path):
        with open(analysis_path) as f:
            all_results = json.load(f)
        with open(cache_path) as f:
            apt_cache = json.load(f)

        def get_hhld(name):
            if name in apt_cache:
                return apt_cache[name]
            for k, v in apt_cache.items():
                if k in name or name in k:
                    return v
            return None

        budget_max = result.final_max_price
        budget_min = max(budget_max - 40000, 60000)

        candidates = []
        for r in all_results:
            if r['avg_price'] > budget_max or r['avg_price'] < budget_min:
                continue
            hhld = get_hhld(r['apt'])
            if not hhld or hhld < 300:
                continue
            if r['count'] < 2 or r['ratio'] <= 0:
                continue

            tier_score = {"상급지": 40, "중상급지": 25, "중하급지": 10, "하급지": 0}.get(r['tier'], 0)
            ratio_score = min(r['ratio'], 80)
            if r['ratio'] > 80:
                ratio_score -= (r['ratio'] - 80) * 2
            hhld_score = min(hhld / 100, 20)
            volume_score = min(r['count'] * 3, 15)

            r['hhld'] = hhld
            r['score'] = round(tier_score + ratio_score + hhld_score + volume_score, 1)

            # 대출/월상환 계산
            loan_needed = min(r['avg_price'] - seed_money, result.final_max_loan)
            if loan_needed < 0:
                loan_needed = 0
            if loan_needed > 0 and mr > 0:
                r['monthly_pay'] = int(loan_needed * (mr * (1 + mr) ** n) / ((1 + mr) ** n - 1))
            else:
                r['monthly_pay'] = 0
            r['loan'] = loan_needed

            candidates.append(r)

        candidates.sort(key=lambda x: -x['score'])
        top10 = candidates[:10]

        if top10:
            for i, r in enumerate(top10, 1):
                with st.container():
                    c1, c2, c3 = st.columns([3, 2, 2])
                    with c1:
                        tier_emoji = {"상급지": "👑", "중상급지": "🏙️", "중하급지": "🏘️", "하급지": "🏠"}.get(r['tier'], "")
                        st.markdown(f"### {i}. {r['apt']}")
                        st.caption(f"{tier_emoji} {r['gu']} {r['tier']} · {r['hhld']:,}세대 · 거래 {r['count']}건")
                    with c2:
                        st.metric("매매가", f"{r['avg_price']/10000:.1f}억")
                        st.metric("전세가율", f"{r['ratio']}%")
                    with c3:
                        st.metric("갭", f"{r['gap']/10000:.1f}억")
                        st.metric("월 상환", f"{r['monthly_pay']:,}만원")

                    # 매수 근거
                    reasons = []
                    if r['tier'] in ('상급지', '중상급지'):
                        reasons.append(f"📍 {r['tier']} 입지 프리미엄")
                    if r['ratio'] >= 70:
                        reasons.append(f"💰 전세가율 {r['ratio']}% (소액 갭)")
                    elif r['ratio'] >= 60:
                        reasons.append(f"💰 전세가율 {r['ratio']}% 양호")
                    if r['hhld'] >= 1000:
                        reasons.append(f"🏢 {r['hhld']:,}세대 대단지")
                    if r['count'] >= 5:
                        reasons.append(f"📊 거래 활발 ({r['count']}건)")
                    if r['monthly_pay'] < 200:
                        reasons.append(f"🏦 월 상환 {r['monthly_pay']:,}만 부담 적음")

                    st.markdown(" · ".join(reasons))
                    st.divider()
        else:
            st.info("예산 범위에 맞는 300세대+ 아파트가 없습니다. 조건을 조정해보세요.")
    else:
        st.info("실거래가 분석 데이터가 없습니다. 먼저 분석을 실행해주세요.")
        st.code("export $(cat .env | xargs) && python3 -m tests.test_api_live")

# ─────────────────────────────────────
# TAB 2: 연도별 로드맵
# ─────────────────────────────────────
with tab2:
    st.subheader("📈 연도별 매수 가능 금액 로드맵")

    annual_save = int(annual_saving_억 * 10000)

    roadmap_data = []
    for year_offset in range(7):
        year = 2026 + year_offset
        s = seed_money + annual_save * year_offset
        # 15억 넘으면 한도 4억
        total = s + result.final_max_loan
        if total > 150000:
            loan_used = 40000
            total_adj = s + 40000
        else:
            loan_used = result.final_max_loan
            total_adj = total

        tiers = []
        if total_adj >= 150000:
            tiers.append("상급지")
        if total_adj >= 100000:
            tiers.append("중상급지")
        if total_adj >= 80000:
            tiers.append("중하급지")
        if total_adj >= 60000:
            tiers.append("하급지")

        roadmap_data.append({
            "연도": f"{year}년",
            "종잣돈": f"{s/10000:.0f}억",
            "대출": f"{loan_used/10000:.0f}억",
            "매수가능": f"{total_adj/10000:.1f}억",
            "가능지역": tiers[0] if tiers else "경기",
        })

    st.table(roadmap_data)

    st.info("""
    **주의**: 15억 초과 시 대출 한도가 6억 → 4억으로 줄어듭니다.
    종잣돈이 늘어도 매수력이 역전될 수 있어요!
    """)

# ─────────────────────────────────────
# TAB 3: 대출 상환 시뮬레이션
# ─────────────────────────────────────
with tab3:
    st.subheader("🏦 대출 상환 시뮬레이션")

    loan_amount_억 = st.slider(
        "대출 금액 (억원)",
        min_value=1.0,
        max_value=min(result.final_max_loan / 10000, 6.0),
        value=min(result.final_max_loan / 10000, 6.0),
        step=0.5,
    )
    loan_amt = int(loan_amount_억 * 10000)

    col1, col2, col3 = st.columns(3)

    scenarios = [
        ("A. 30년 원리금균등", 30, False),
        ("B. 15년 조기상환", 15, False),
        ("C. 거치 3년 + 27년", 30, True),
    ]

    for col, (name, years, is_grace) in zip([col1, col2, col3], scenarios):
        with col:
            st.markdown(f"**{name}**")
            r_monthly = (interest_rate / 100) / 12
            months = years * 12

            if is_grace:
                grace_pay = loan_amt * (interest_rate / 100) / 12
                after_months = 27 * 12
                after_pay = loan_amt * (r_monthly * (1 + r_monthly) ** after_months) / (
                    (1 + r_monthly) ** after_months - 1
                )
                total_interest = grace_pay * 36 + after_pay * after_months - loan_amt
                st.metric("처음 3년 월", f"{grace_pay:,.0f}만원")
                st.metric("이후 월", f"{after_pay:,.0f}만원")
            else:
                monthly = loan_amt * (r_monthly * (1 + r_monthly) ** months) / (
                    (1 + r_monthly) ** months - 1
                )
                total_interest = monthly * months - loan_amt
                st.metric("월 상환액", f"{monthly:,.0f}만원")
                st.metric("월급 대비", f"{monthly / monthly_income * 100:.1f}%")

            st.metric("총 이자", f"{total_interest / 10000:.1f}억원")

    st.divider()
    st.caption("※ 중도상환 수수료: 대부분 3년 이내 1.2~1.5%, 이후 무료")
    st.caption("※ 실제 금리는 은행/신용등급/상품에 따라 다름")

# ─────────────────────────────────────
# 푸터
# ─────────────────────────────────────
st.divider()
st.caption("🤖 부동산 AI 비서 | 공공데이터포털 실거래가 API + 건축물대장 API 기반")
st.caption("※ 투자 판단은 본인 책임입니다. 참고용으로만 활용하세요.")
