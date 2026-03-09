"""
🏠 내집마련 AI 비서 — 웹앱
저장된 분석 데이터 기반 조회 (collect_data.py로 하루 1회 수집)
"""
import streamlit as st
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.calculator import (
    BuyerType, LoanPolicy, UserFinance, calculate_affordability,
)

# ─────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────
st.set_page_config(page_title="내집마련 AI 비서", page_icon="🏠", layout="wide")
st.title("🏠 내집마련 AI 비서")
st.caption("내 월급으로 서울 어디 살 수 있을까?")

# ─────────────────────────────────────
# 데이터 로드 (파일 기반, 즉시 로딩)
# ─────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


@st.cache_data
def load_data():
    analysis, meta, raw_trades = [], {}, []
    path = os.path.join(DATA_DIR, "analysis.json")
    if os.path.exists(path):
        with open(path) as f:
            analysis = json.load(f)
    meta_path = os.path.join(DATA_DIR, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    raw_path = os.path.join(DATA_DIR, "raw_trades.json")
    if os.path.exists(raw_path):
        with open(raw_path) as f:
            raw_trades = json.load(f)
    return analysis, meta, raw_trades


all_data, meta, raw_trades = load_data()

# 아파트별 raw 거래 인덱스 (실거래가 테이블용)
@st.cache_data
def build_trade_index(_raw_trades):
    idx = {}
    for t in _raw_trades:
        key = (t["gu"], t["apt"])
        idx.setdefault(key, []).append(t)
    # 최신순 정렬
    for key in idx:
        idx[key].sort(key=lambda x: (x["year"], x["month"]), reverse=True)
    return idx

trade_index = build_trade_index(raw_trades)

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

    monthly_expense = st.number_input(
        "월 지출 (만원)", min_value=50, max_value=5000, value=500, step=50,
        help="월세/관리비/생활비/보험/구독 등 고정+변동 지출 합계"
    )
    bonus = st.number_input(
        "연간 인센티브/보너스 (만원)", min_value=0, max_value=50000, value=0, step=100,
        help="성과급, 상여금 등 (세후)"
    )
    annual_saving = (monthly_income - monthly_expense) * 12 + bonus
    annual_saving_억 = annual_saving / 10000
    if annual_saving > 0:
        st.success(f"연간 저축: **{annual_saving:,.0f}만원 ({annual_saving_억:.1f}억)**")
    else:
        st.error(f"지출 > 수입! ({annual_saving:,.0f}만원/년)")

    st.divider()
    st.subheader("🏦 대출 조건")

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

    # 시스템 계산
    policy = LoanPolicy(base_interest_rate=interest_rate / 100)
    user = UserFinance(
        seed_money=seed_money, monthly_income=monthly_income,
        monthly_expense=monthly_expense, buyer_type=buyer_type,
        will_reside=will_reside,
    )
    sys_result = calculate_affordability(user, policy)

    loan_input_억 = st.number_input(
        "희망 대출 금액 (억원)",
        min_value=0.0,
        max_value=sys_result.final_max_loan / 10000,
        value=sys_result.final_max_loan / 10000,
        step=0.5,
        help=f"DSR/LTV 기준 최대 {sys_result.final_max_loan/10000:.1f}억까지 가능"
    )
    loan_amount = int(loan_input_억 * 10000)

    st.info(f"DSR 최대: {sys_result.max_loan_by_dsr_stress/10000:.1f}억 / LTV 최대: {sys_result.max_loan_by_ltv/10000:.1f}억")

    st.divider()
    st.caption("10.15 부동산 대책 반영 (2025.10.15~)")
    st.caption("스트레스 DSR 3% / 토허제 서울전역")

# ─────────────────────────────────────
# 최종 예산 계산
# ─────────────────────────────────────
budget = seed_money + loan_amount
mr = (interest_rate / 100) / 12
n = 360
if loan_amount > 0 and mr > 0:
    monthly_pay = loan_amount * (mr * (1 + mr) ** n) / ((1 + mr) ** n - 1)
else:
    monthly_pay = 0

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("💰 매수 가능 집값", f"{budget / 10000:.1f}억원")
with col2:
    st.metric("🏦 대출", f"{loan_amount / 10000:.1f}억원")
with col3:
    st.metric("📅 월 상환액", f"{monthly_pay:,.0f}만원")
with col4:
    pay_ratio = monthly_pay / monthly_income * 100 if monthly_income > 0 else 0
    st.metric("📊 월급 대비", f"{pay_ratio:.1f}%")

for w in sys_result.warnings:
    st.warning(w)

st.divider()

# ─────────────────────────────────────
# 탭
# ─────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["🏆 TOP 10 추천", "📈 연도별 로드맵", "🏦 대출 상환 시뮬레이션"])

# ─────────────────────────────────────
# TAB 1: TOP 10 (저장 데이터 기반)
# ─────────────────────────────────────
with tab1:
    st.subheader("내 예산 맞춤 TOP 10 아파트")

    if not all_data:
        st.error("분석 데이터가 없습니다. 먼저 수집을 실행해주세요:")
        st.code("export $(cat .env | grep -v '^#' | xargs) && python3 collect_data.py")
    else:
        if meta:
            st.caption(f"데이터: {meta.get('collected_at', '?')} 수집 / 매매 {meta.get('trade_count', 0):,}건 / 전세 {meta.get('rent_count', 0):,}건 / {meta.get('apt_count', 0)}개 아파트")

        # 예산 중심으로 범위 (대출 포함 금액 근처)
        budget_max = int(budget * 1.10)   # 예산 + 10%
        budget_min = int(budget * 0.80)   # 예산 - 20%
        st.caption(f"예산: {budget_min/10000:.1f}억 ~ {budget_max/10000:.1f}억 (종잣돈+대출 {budget/10000:.1f}억 기준) / 25~34평 / 300세대+")

        # 스코어링 + 필터링
        candidates = []
        for r in all_data:
            if r["avg_price"] > budget_max or r["avg_price"] < budget_min:
                continue

            tier_score = {"상급지": 40, "중상급지": 25, "중하급지": 10, "하급지": 0}.get(r["tier"], 0)
            ratio_score = min(r["ratio"], 80)
            if r["ratio"] > 80:
                ratio_score -= (r["ratio"] - 80) * 2
            hhld_score = min(r.get("hhld", 0) / 100, 20)
            volume_score = min(r["count"] * 3, 15)

            score = round(tier_score + ratio_score + hhld_score + volume_score, 1)

            # 대출/월상환
            loan_needed = min(r["avg_price"] - seed_money, loan_amount)
            if loan_needed < 0:
                loan_needed = 0
            if loan_needed > 0 and mr > 0:
                mp = int(loan_needed * (mr * (1 + mr) ** n) / ((1 + mr) ** n - 1))
            else:
                mp = 0

            candidates.append({**r, "score": score, "loan_needed": loan_needed, "monthly_pay": mp})

        candidates.sort(key=lambda x: -x["score"])
        top10 = candidates[:10]

        if top10:
            for i, r in enumerate(top10, 1):
                with st.container():
                    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
                    with c1:
                        tier_emoji = {"상급지": "👑", "중상급지": "🏙️", "중하급지": "🏘️", "하급지": "🏠"}.get(r["tier"], "")
                        st.markdown(f"### {i}. {r['apt']}")
                        st.caption(f"{tier_emoji} {r['gu']} {r['tier']} · {r.get('hhld', 0):,}세대 · 거래 {r['count']}건")
                    with c2:
                        recent_high = r.get("recent_high", r["avg_price"])
                        st.metric("최근 최고가", f"{recent_high/10000:.1f}억")
                        st.metric("최근 평균가", f"{r['avg_price']/10000:.1f}억")
                        st.metric("전세가율", f"{r['ratio']}%")
                    with c3:
                        st.metric("갭", f"{r['gap']/10000:.1f}억")
                        st.metric("월 상환", f"{r['monthly_pay']:,}만원")
                    with c4:
                        if r.get("is_at_peak"):
                            st.metric("📈 현재 최고점!", f"{r.get('recent_high', r['avg_price'])/10000:.1f}억")
                            st.caption(f"이전 고점 {r['peak']/10000:.1f}억 ({r['peak_ym']}) 돌파")
                        else:
                            peak_gap = r["avg_price"] - r["peak"]
                            st.metric("전고점 대비", f"{r['diff_peak']:+.1f}%")
                            st.caption(f"고점 {r['peak']/10000:.1f}억 ({r['peak_ym']})\n\n전고점대비 **{abs(peak_gap)/10000:.1f}억 하락**")

                        # 회복률
                        rr = r.get("recovery_rate", 0)
                        if rr > 0:
                            if rr >= 100:
                                st.metric("회복률", f"{rr:.0f}%", delta="전고점 회복")
                            else:
                                st.metric("회복률", f"{rr:.0f}%")

                    # 매수 근거
                    reasons = []
                    if r["tier"] in ("상급지", "중상급지"):
                        reasons.append(f"📍 {r['tier']} 입지")
                    if r["ratio"] >= 70:
                        reasons.append(f"💰 전세가율 {r['ratio']}% (소액 갭)")
                    elif r["ratio"] >= 60:
                        reasons.append(f"💰 전세가율 {r['ratio']}% 양호")
                    if r.get("hhld", 0) >= 1000:
                        reasons.append(f"🏢 {r['hhld']:,}세대 대단지")
                    if r["count"] >= 5:
                        reasons.append(f"📊 거래 활발 ({r['count']}건)")
                    if r["monthly_pay"] < 200:
                        reasons.append(f"🏦 월상환 {r['monthly_pay']:,}만 부담 적음")
                    if r["diff_peak"] <= -20:
                        reasons.append(f"📉 전고점대비 {abs(peak_gap)/10000:.1f}억 하락 (저평가)")
                    elif r["diff_peak"] <= -10:
                        reasons.append(f"📉 전고점대비 {abs(peak_gap)/10000:.1f}억 할인")

                    st.markdown(" · ".join(reasons))

                    # 시기별 비교 테이블
                    pcp = r.get("pre_crash_peak", 0)
                    ct = r.get("crash_trough", 0)
                    if pcp > 0 and ct > 0:
                        import pandas as pd
                        crash_drop = pcp - ct
                        current_vs_precrash = r["avg_price"] - pcp
                        table_data = [
                            {
                                "시기": "상승기 고점 (20~22)",
                                "가격": f"{pcp/10000:.1f}억",
                                "시점": r.get("pre_crash_ym", ""),
                                "현재 대비": f"{current_vs_precrash/10000:+.1f}억 ({'상승' if current_vs_precrash >= 0 else '하락'})",
                            },
                            {
                                "시기": "하락기 저점 (23~24)",
                                "가격": f"{ct/10000:.1f}억",
                                "시점": r.get("crash_trough_ym", ""),
                                "현재 대비": f"{(r['avg_price']-ct)/10000:+.1f}억 (상승)",
                            },
                            {
                                "시기": "하락 폭",
                                "가격": f"-{crash_drop/10000:.1f}억",
                                "시점": "",
                                "현재 대비": f"고점 대비 {crash_drop/pcp*100:.0f}% 하락",
                            },
                            {
                                "시기": "현재 (최근 3개월)",
                                "가격": f"{r['avg_price']/10000:.1f}억",
                                "시점": "최근",
                                "현재 대비": f"회복률 {r.get('recovery_rate', 0):.0f}%",
                            },
                        ]
                        with st.expander("📋 시기별 가격 비교"):
                            st.dataframe(pd.DataFrame(table_data), use_container_width=True, hide_index=True)

                    # 매매가 추이 그래프 + 실거래가 테이블
                    history = r.get("price_history", {})
                    if history and len(history) >= 2:
                        with st.expander(f"📊 {r['apt']} 매매가 추이 + 실거래 내역"):
                            import pandas as pd
                            import plotly.graph_objects as go

                            # --- Plotly 그래프 ---
                            sorted_history = sorted(history.items())
                            yms = [ym for ym, _ in sorted_history]
                            prices = [p / 10000 for _, p in sorted_history]

                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=yms, y=prices,
                                mode="lines+markers",
                                name="월평균 매매가",
                                line=dict(color="#FF6B6B", width=2.5),
                                marker=dict(size=5),
                                hovertemplate="%{x}<br>%{y:.1f}억원<extra></extra>",
                            ))
                            # 전고점 라인
                            fig.add_hline(
                                y=r["peak"] / 10000,
                                line_dash="dash", line_color="red", opacity=0.5,
                                annotation_text=f"전고점 {r['peak']/10000:.1f}억 ({r['peak_ym']})",
                                annotation_position="top left",
                            )
                            # 전저점 라인
                            fig.add_hline(
                                y=r["trough"] / 10000,
                                line_dash="dash", line_color="blue", opacity=0.5,
                                annotation_text=f"전저점 {r['trough']/10000:.1f}억 ({r['trough_ym']})",
                                annotation_position="bottom left",
                            )
                            # 현재가 라인
                            fig.add_hline(
                                y=r["avg_price"] / 10000,
                                line_dash="dot", line_color="green", opacity=0.7,
                                annotation_text=f"현재 {r['avg_price']/10000:.1f}억",
                                annotation_position="top right",
                            )
                            fig.update_layout(
                                height=300,
                                margin=dict(l=0, r=0, t=30, b=0),
                                xaxis_title="", yaxis_title="매매가 (억원)",
                                hovermode="x unified",
                                showlegend=False,
                            )
                            st.plotly_chart(fig, use_container_width=True)

                            # --- 실거래가 테이블 ---
                            apt_trades = trade_index.get((r["gu"], r["apt"]), [])
                            # 25~34평만 필터
                            apt_trades_filtered = [t for t in apt_trades if 59 <= t["area"] <= 112]
                            if apt_trades_filtered:
                                st.markdown("**최근 실거래 내역**")
                                rows = []
                                for t in apt_trades_filtered[:15]:
                                    rows.append({
                                        "거래일": f"{t['year']}.{t['month']:02d}",
                                        "매매가": f"{t['price']/10000:.1f}억",
                                        "전용면적": f"{t['area']:.0f}㎡ ({t['area']*0.3025:.0f}평)",
                                    })
                                st.dataframe(
                                    pd.DataFrame(rows),
                                    use_container_width=True,
                                    hide_index=True,
                                )
                            st.caption(f"2020~현재 총 {r.get('count_total', 0)}건 거래")
                    st.divider()

            st.caption(f"총 {len(candidates)}개 후보 중 상위 10개")
        else:
            st.info(f"예산 {budget_min/10000:.1f}~{budget_max/10000:.1f}억 범위에 맞는 아파트가 없습니다. 조건을 조정해보세요.")

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
        total = s + loan_amount
        if total > 150000:
            loan_used = min(loan_amount, 40000)
            total_adj = s + loan_used
        else:
            loan_used = loan_amount
            total_adj = total

        tiers = []
        if total_adj >= 150000: tiers.append("상급지")
        if total_adj >= 100000: tiers.append("중상급지")
        if total_adj >= 80000: tiers.append("중하급지")
        if total_adj >= 60000: tiers.append("하급지")

        roadmap_data.append({
            "연도": f"{year}년",
            "종잣돈": f"{s/10000:.0f}억",
            "대출": f"{loan_used/10000:.0f}억",
            "매수가능": f"{total_adj/10000:.1f}억",
            "가능지역": tiers[0] if tiers else "경기",
        })

    st.table(roadmap_data)
    st.info("**주의**: 15억 초과 시 대출 한도가 6억 → 4억으로 줄어듭니다.")

# ─────────────────────────────────────
# TAB 3: 대출 상환 시뮬레이션
# ─────────────────────────────────────
with tab3:
    st.subheader("🏦 대출 상환 시뮬레이션")

    sim_loan_억 = st.slider(
        "대출 금액 (억원)",
        min_value=0.5,
        max_value=max(loan_amount / 10000, 1.0),
        value=max(loan_amount / 10000, 0.5),
        step=0.5,
    )
    sim_loan = int(sim_loan_억 * 10000)

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
                grace_pay = sim_loan * (interest_rate / 100) / 12
                after_months = 27 * 12
                after_pay = sim_loan * (r_monthly * (1 + r_monthly) ** after_months) / (
                    (1 + r_monthly) ** after_months - 1
                )
                total_interest = grace_pay * 36 + after_pay * after_months - sim_loan
                st.metric("처음 3년 월", f"{grace_pay:,.0f}만원")
                st.metric("이후 월", f"{after_pay:,.0f}만원")
            else:
                monthly = sim_loan * (r_monthly * (1 + r_monthly) ** months) / (
                    (1 + r_monthly) ** months - 1
                )
                total_interest = monthly * months - sim_loan
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
st.caption("🤖 부동산 AI 비서 | 국토교통부 실거래가 API + 건축물대장 API 기반")
st.caption("※ 투자 판단은 본인 책임입니다. 참고용으로만 활용하세요.")
