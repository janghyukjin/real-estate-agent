"""
🏠 집피티 — 내집마련 AI 비서 — 웹앱
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
st.set_page_config(page_title="집피티 — 내집마련 AI 비서", page_icon="🏠", layout="wide", initial_sidebar_state="expanded")

st.title("🏠 집피티")
st.caption("내 월급으로 서울 어디 살 수 있을까?")
st.info("👈 **왼쪽 사이드바**에서 종잣돈·연봉을 입력하면 맞춤 추천이 시작됩니다! (모바일: 좌측 상단 **>** 버튼)")

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

# 아파트별+평형별 raw 거래 인덱스 (실거래가 테이블용)
def _get_area_type(area):
    return f"{int(area)}㎡"

@st.cache_data
def build_trade_index(_raw_trades):
    idx = {}
    for t in _raw_trades:
        area_type = _get_area_type(t["area"])
        key = (t["gu"], t["apt"], t.get("dong", ""), area_type)
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
        "종잣돈 (억원)", min_value=0.0, max_value=50.0, value=0.0, step=0.5,
        help="현재 보유 현금 + 예금 + 주식 등 동원 가능한 총 금액"
    )
    seed_money = int(seed_money_억 * 10000)

    contract_salary = st.number_input(
        "계약연봉 (만원)", min_value=0, max_value=100000, value=0, step=100,
        help="인센/상여 제외한 계약연봉 (세전)"
    )
    bonus = st.number_input(
        "연간 인센티브/상여 (만원)", min_value=0, max_value=50000, value=0, step=100,
        help="성과급, 상여금 등 연간 합계 (세전)"
    )
    annual_income = contract_salary + bonus  # 원천징수 총급여
    monthly_income = contract_salary // 12 if contract_salary > 0 else 0
    if annual_income > 0:
        st.caption(f"원천징수 총급여: {annual_income:,}만원 (월 {monthly_income:,}만원 + 인센 {bonus:,}만원)")

    monthly_expense = st.number_input(
        "월 지출 (만원)", min_value=0, max_value=5000, value=150, step=50,
        help="월세/관리비/생활비/보험/구독 등 고정+변동 지출 합계"
    )

    if seed_money == 0 or annual_income == 0:
        st.warning("⬆️ 종잣돈과 연봉을 입력해주세요")
    annual_saving = (monthly_income - monthly_expense) * 12 + bonus
    annual_saving_억 = annual_saving / 10000
    if annual_saving > 0:
        st.success(f"연간 저축: **{annual_saving:,.0f}만원 ({annual_saving_억:.1f}억)**")
        st.caption(f"월급 저축 {(monthly_income - monthly_expense) * 12:,}만 + 인센 {bonus:,}만")
    elif annual_income > 0:
        st.error(f"지출 > 수입! ({annual_saving:,.0f}만원/년)")

    st.divider()
    st.subheader("🏦 대출 조건")

    buyer_type = st.selectbox(
        "매수자 유형",
        options=[BuyerType.FIRST_TIME, BuyerType.NO_HOUSE, BuyerType.ONE_HOUSE],
        format_func=lambda x: x.value,
        help="생애최초: LTV 70% / 무주택: LTV 40% / 1주택: LTV 0%"
    )
    will_reside = st.checkbox("실거주 예정", value=True, key="will_reside")
    gap_invest_mode = st.checkbox("갭투자 (전세끼고 매수)", value=False,
        help="ON: 전세끼고 매수 / 자동으로 비실거주 적용")
    if gap_invest_mode:
        will_reside = False
        st.caption("⚠️ 갭투자 → 비실거주 자동 적용")
    interest_rate = st.slider(
        "예상 대출 금리 (%)", min_value=2.5, max_value=6.0, value=4.2, step=0.1,
    )

    # 시스템 계산 (DSR은 원천징수 총급여 기준 = 계약연봉 + 인센)
    dsr_monthly_income = annual_income // 12 if annual_income > 0 else 0
    policy = LoanPolicy(base_interest_rate=interest_rate / 100)
    user = UserFinance(
        seed_money=seed_money, monthly_income=dsr_monthly_income,
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
    st.subheader("🔍 필터")

    tier_options = ["전체", "상급지", "상급지(경기·과천)", "상급지(경기)", "중상급지", "중하급지", "하급지"]
    selected_tiers = st.multiselect(
        "지역 등급",
        options=tier_options,
        default=["전체"],
        help="상급지: 강남/서초/송파/용산 | 중상급지: 마포/성동/광진/동작/강동/영등포/양천 | 중하급지: 노원/도봉/강북/성북/중랑/동대문/서대문/은평 | 하급지: 강서/구로/금천/관악/종로/중구"
    )

    # 구/동 필터
    all_gus = sorted(set(r["gu"] for r in all_data))
    selected_gus = st.multiselect("구 선택", options=["전체"] + all_gus, default=["전체"])
    filter_all_gus = "전체" in selected_gus

    all_dongs = sorted(set(r.get("dong", "") for r in all_data
                           if r.get("dong") and (filter_all_gus or r["gu"] in selected_gus)))
    if all_dongs:
        selected_dongs = st.multiselect("동 선택", options=["전체"] + all_dongs, default=["전체"])
        filter_all_dongs = "전체" in selected_dongs
    else:
        selected_dongs = ["전체"]
        filter_all_dongs = True

    min_recovery = st.slider(
        "최소 회복률 — 22년 고점 대비 (%)", min_value=0, max_value=150, value=0, step=5,
        help="현재 거래가 / 22년 고점 × 100%. 100% = 고점 회복"
    )
    max_recovery = st.slider(
        "최대 회복률 — 22년 고점 대비 (%)", min_value=0, max_value=200, value=200, step=5,
        help="현재 거래가 / 22년 고점 × 100%. 100% 미만 = 아직 미회복"
    )

    max_policy_change = st.slider(
        "토허제 후 최대 변동률 (%)", min_value=-100, max_value=100, value=100, step=5,
        help="10.15 토허제 전(24년7~9월) 대비 변동률. 낮을수록 토허제 후 많이 빠진 곳"
    )

    min_hhld = st.number_input(
        "최소 세대수", min_value=300, max_value=5000, value=300, step=100,
        help="이 세대수 이상인 아파트만 표시"
    )

    top_n = st.number_input(
        "상위 표시 개수", min_value=5, max_value=50, value=10, step=5,
        help="TOP N개 아파트 표시"
    )

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

pay_ratio = monthly_pay / monthly_income * 100 if monthly_income > 0 else 0
budget_label = "💰 갭투자 내돈" if gap_invest_mode else "💰 매수 가능 집값"
budget_val = f"{(seed_money + loan_amount) / 10000:.1f}억원" if gap_invest_mode else f"{budget / 10000:.1f}억원"
fin_cells = [
    (budget_label, budget_val),
    ("🏦 대출", f"{loan_amount / 10000:.1f}억원"),
    ("📅 월 상환액", f"{monthly_pay:,.0f}만원"),
    ("📊 월급 대비", f"{pay_ratio:.1f}%"),
]
fin_html = '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:4px 12px;margin:0.5rem 0 1rem;">'
for fl, fv in fin_cells:
    fin_html += f'<div style="padding:8px 0;border-bottom:1px solid rgba(128,128,128,0.15)"><span style="font-size:0.75rem;color:#888;display:block">{fl}</span><span style="font-size:1.2rem;font-weight:700">{fv}</span></div>'
fin_html += '</div>'
st.markdown(fin_html, unsafe_allow_html=True)

for w in sys_result.warnings:
    st.warning(w)

st.divider()

# ─────────────────────────────────────
# 탭
# ─────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs([f"🏆 TOP {top_n} 추천", "📈 연도별 로드맵", "🏦 대출 상환 시뮬레이션", "ℹ️ 서비스 소개"])

# ─────────────────────────────────────
# TAB 1: TOP 10 (저장 데이터 기반)
# ─────────────────────────────────────
with tab1:
    st.subheader(f"내 예산 맞춤 TOP {top_n} 아파트")

    if not all_data:
        st.error("분석 데이터가 없습니다. 먼저 수집을 실행해주세요:")
        st.code("export $(cat .env | grep -v '^#' | xargs) && python3 collect_data.py")
    else:
        if meta:
            st.caption(f"데이터: {meta.get('collected_at', '?')} 수집 / 매매 {meta.get('trade_count', 0):,}건 / 전세 {meta.get('rent_count', 0):,}건 / {meta.get('apt_count', 0)}개 아파트")

        # 모드별 필터 기준
        gap_budget = seed_money + loan_amount  # 갭투자 시 내 돈 = 종잣돈 + 대출
        if gap_invest_mode:
            gap_max = int(gap_budget * 1.10)
            gap_min = int(gap_budget * 0.90)
            st.caption(f"🔄 갭투자 모드: 갭 {gap_min/10000:.1f}~{gap_max/10000:.1f}억 (내돈 = 종잣돈+대출 {gap_budget/10000:.1f}억 기준) / 매매가 = 전세가+내돈 / {min_hhld}세대+")
        else:
            budget_max = int(budget * 1.10)   # 예산 + 10%
            budget_min = int(budget * 0.80)   # 예산 - 20%
            st.caption(f"예산: {budget_min/10000:.1f}억 ~ {budget_max/10000:.1f}억 (종잣돈+대출 {budget/10000:.1f}억 기준) / 25~34평 / {min_hhld}세대+")

        # 스코어링 + 필터링
        filter_all_tiers = "전체" in selected_tiers
        candidates = []
        for r in all_data:
            # 공통 필터
            if r.get("hhld", 0) < min_hhld:
                continue
            if not filter_all_tiers and r.get("tier", "") not in selected_tiers:
                continue
            if not filter_all_gus and r["gu"] not in selected_gus:
                continue
            if not filter_all_dongs and r.get("dong", "") not in selected_dongs:
                continue
            rr = r.get("recovery_rate", 0)
            if rr < min_recovery or rr > max_recovery:
                continue
            # 토허제 변동률 필터
            pa = r.get("policy_avg", 0)
            if pa > 0:
                latest_p = r.get("latest_price", r["avg_price"])
                policy_pct = round((latest_p - pa) / pa * 100, 1)
                if policy_pct > max_policy_change:
                    continue

            # 모드별 필터
            if gap_invest_mode:
                # 갭투자: 갭(매매가-전세가) ≤ 종잣돈+대출 범위 90~110%
                apt_gap = r["gap"]
                if apt_gap > gap_max or apt_gap < gap_min:
                    continue
            else:
                if r["avg_price"] > budget_max or r["avg_price"] < budget_min:
                    continue

            # 1) 지역등급 (최대 40점)
            tier_score = {"상급지": 40, "상급지(경기·과천)": 30, "상급지(경기)": 25, "중상급지": 25, "중하급지": 10, "하급지": 0}.get(r["tier"], 0)
            # 2) 전세가율 (최대 30점) — 50~70% 최고, 벗어나면 감점
            ratio_val = r["ratio"]
            if 50 <= ratio_val <= 70:
                ratio_score = 30
            elif ratio_val < 50:
                ratio_score = max(0, 30 - (50 - ratio_val) * 1.0)
            else:  # > 70
                ratio_score = max(0, 30 - (ratio_val - 70) * 1.5)
            # 3) 세대수 (최대 20점)
            hhld_score = min(r.get("hhld", 0) / 100, 20)
            # 4) 거래량 (최대 15점)
            volume_score = min(r["count"] * 3, 15)
            # 5) 회복률 (±30점) — 100% 미만 가점, 초과 감점
            if rr > 0:
                recovery_score = (100 - rr) * 0.3  # 80%→+6, 100%→0, 120%→-6
                recovery_score = max(-30, min(30, recovery_score))
            else:
                recovery_score = 0
            # 6) 토허제 변동 (±15점) — 적게 오를수록 가점
            pa = r.get("policy_avg", 0)
            if pa > 0:
                latest_p = r.get("latest_price", r["avg_price"])
                policy_pct = (latest_p - pa) / pa * 100  # 변동률 %
                policy_score = -policy_pct * 0.5  # 10% 상승→-5점, -10% 하락→+5점
                policy_score = max(-15, min(15, policy_score))
            else:
                policy_score = 0

            score = round(tier_score + ratio_score + hhld_score + volume_score + recovery_score + policy_score, 1)

            # 대출/월상환
            if gap_invest_mode:
                loan_needed = min(r["gap"] - seed_money, loan_amount)
            else:
                loan_needed = min(r["avg_price"] - seed_money, loan_amount)
            if loan_needed < 0:
                loan_needed = 0
            if loan_needed > 0 and mr > 0:
                mp = int(loan_needed * (mr * (1 + mr) ** n) / ((1 + mr) ** n - 1))
            else:
                mp = 0

            candidates.append({**r, "score": score, "loan_needed": loan_needed, "monthly_pay": mp})

        candidates.sort(key=lambda x: -x["score"])
        top10 = candidates[:top_n]

        if top10:
            for i, r in enumerate(top10, 1):
                with st.container():
                    # 아파트명 (전체 너비)
                    tier_emoji = {"상급지": "👑", "중상급지": "🏙️", "중하급지": "🏘️", "하급지": "🏠"}.get(r["tier"], "")
                    area_type = r.get("area_type", "")
                    area_num = int(area_type.replace("㎡", "")) if "㎡" in area_type else 0
                    pyeong = round(area_num * 0.3025) if area_num else ""
                    st.markdown(f"### {i}. {r['apt']}")
                    dong = r.get("dong", "")
                    loc = f"{r['gu']} {dong}" if dong else r['gu']
                    st.caption(f"{tier_emoji} {loc} {r['tier']} · **전용 {area_type} ({pyeong}평)** · {r.get('hhld', 0):,}세대 · 거래 {r['count']}건")

                    # 핵심 지표 — HTML 그리드 (모바일 반응형)
                    latest = r.get("latest_price", r["avg_price"])
                    latest_ym = r.get("latest_ym", "")
                    gap = r["gap"]

                    # 행1: 가격 정보
                    cells = []
                    ym_sub = f'<span style="font-size:0.7rem;color:#888">({latest_ym})</span>' if latest_ym else ""
                    cells.append(("최근 거래가", f"{latest/10000:.1f}억 {ym_sub}"))
                    cells.append(("평균 매매가", f"{r['avg_price']/10000:.1f}억"))
                    cells.append(("전세가율", f"{r['ratio']}%"))
                    cells.append(("갭(매매-전세)", f"{gap/10000:.1f}억"))

                    # 월 상환 / 갭투자
                    if gap_invest_mode:
                        remain = gap_budget - gap
                        extra = f"✅ 잔여 {remain/10000:.1f}억" if remain >= 0 else ""
                        cells.append(("갭투자", f"내돈 {gap/10000:.1f}억 {extra}"))
                    else:
                        if r['monthly_pay'] > 0:
                            cells.append(("월 상환", f"{r['monthly_pay']:,}만원"))
                        if seed_money > 0 and gap <= seed_money:
                            cells.append(("갭투자", "✅ 종잣돈으로 가능"))

                    # 10.15 토허제
                    pa = r.get("policy_avg", 0)
                    if pa > 0:
                        diff_policy = latest - pa
                        pct = round(diff_policy / pa * 100, 1)
                        cells.append(("10.15 변동", f"{pct:+.1f}% <span style='font-size:0.7rem;color:#888'>{pa/10000:.1f}→{latest/10000:.1f}억</span>"))

                    # 고점 대비
                    if r.get("is_at_peak"):
                        cells.append(("📈 최고점!", f"{r.get('recent_high', r['avg_price'])/10000:.1f}억"))
                    else:
                        peak_gap = r["avg_price"] - r["peak"]
                        cells.append(("전고점 대비", f"{r['diff_peak']:+.1f}% <span style='font-size:0.7rem;color:#888'>({r['peak']/10000:.1f}억 {r['peak_ym']})</span>"))

                    # 회복률
                    rr = r.get("recovery_rate", 0)
                    if rr > 0:
                        if rr >= 100:
                            cells.append(("22년 고점", f"<span style='color:#2ecc71'>{rr:.0f}% 돌파</span>"))
                        else:
                            cells.append(("22년 고점", f"<span style='color:#e74c3c'>{rr:.0f}% ({100-rr:.0f}% 미회복)</span>"))

                    # HTML 그리드 렌더링
                    grid_html = '<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:4px 12px;margin:0.5rem 0 1rem;">'
                    for label, val in cells:
                        grid_html += f'<div style="padding:6px 0;border-bottom:1px solid rgba(128,128,128,0.15)"><span style="font-size:0.75rem;color:#888;display:block">{label}</span><span style="font-size:1rem;font-weight:600">{val}</span></div>'
                    grid_html += '</div>'
                    st.markdown(grid_html, unsafe_allow_html=True)

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
                            st.dataframe(pd.DataFrame(table_data), width="stretch", hide_index=True)

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
                            # 마지막 실거래가 포인트 (월평균과 다를 수 있음)
                            latest_p = r.get("latest_price", 0)
                            latest_ym = r.get("latest_ym", "")
                            if latest_p and latest_ym:
                                fig.add_trace(go.Scatter(
                                    x=[latest_ym], y=[latest_p / 10000],
                                    mode="markers+text",
                                    name="최근 실거래가",
                                    marker=dict(size=12, color="#FF6B6B", symbol="star", line=dict(width=2, color="white")),
                                    text=[f"{latest_p/10000:.1f}억"],
                                    textposition="top center",
                                    textfont=dict(size=11, color="#FF6B6B"),
                                    hovertemplate=f"최근 실거래가<br>{latest_ym}<br>{latest_p/10000:.1f}억원<extra></extra>",
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
                            st.plotly_chart(fig, width="stretch")

                            # --- 실거래가 테이블 (같은 평형만) ---
                            apt_trades_filtered = trade_index.get((r["gu"], r["apt"], r.get("dong", ""), r.get("area_type", "")), [])
                            if apt_trades_filtered:
                                st.markdown("**최근 실거래 내역**")
                                rows = []
                                for t in apt_trades_filtered[:15]:
                                    floor = t.get("floor", "")
                                    floor_str = f"{floor}층" if floor else ""
                                    if floor == 1:
                                        floor_str = "⚠️ 1층"
                                    deal_type = t.get("deal_type", "")
                                    note = ""
                                    if deal_type == "직거래":
                                        note = "직거래"
                                    rows.append({
                                        "거래일": f"{t['year']}.{t['month']:02d}",
                                        "매매가": f"{t['price']/10000:.1f}억",
                                        "층": floor_str,
                                        "면적": f"{t['area']:.0f}㎡",
                                        "비고": note,
                                    })
                                st.dataframe(
                                    pd.DataFrame(rows),
                                    width="stretch",
                                    hide_index=True,
                                )
                            st.caption(f"2020~현재 총 {r.get('count_total', 0)}건 거래")
                    st.divider()

            st.caption(f"총 {len(candidates)}개 후보 중 상위 10개")
        else:
            if gap_invest_mode:
                st.info(f"갭 {gap_min/10000:.1f}~{gap_max/10000:.1f}억 범위에 맞는 아파트가 없습니다. 조건을 조정해보세요.")
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
                if monthly_income > 0:
                    st.metric("월급 대비", f"{monthly / monthly_income * 100:.1f}%")

            st.metric("총 이자", f"{total_interest / 10000:.1f}억원")

    st.divider()
    st.caption("※ 중도상환 수수료: 대부분 3년 이내 1.2~1.5%, 이후 무료")
    st.caption("※ 실제 금리는 은행/신용등급/상품에 따라 다름")

# ─────────────────────────────────────
# TAB 4: 서비스 소개
# ─────────────────────────────────────
with tab4:
    st.subheader("ℹ️ 서비스 소개")

    st.markdown("""
### 이 서비스는 무엇인가요?

**집피티(ZipTI)**는 무주택 실수요자를 위한 **아파트 맞춤 추천 도구**입니다.
내 연봉, 종잣돈, 지출을 입력하면 DSR/LTV를 자동 계산하고,
예산에 맞는 아파트를 **6가지 항목으로 스코어링**하여 순위를 매깁니다.

단순히 시세를 보여주는 데이터 뷰어가 아니라, **"지금 이 돈으로 어디가 최선인가"에 답하는 의사결정 도구**입니다.

---

### 사용 데이터

| 데이터 | 출처 | 설명 |
|--------|------|------|
| 아파트 매매 실거래가 | 국토교통부 API (data.go.kr) | 2020년~현재, 서울+과천/분당 |
| 아파트 전월세 실거래 | 국토교통부 API (data.go.kr) | 전세가율 계산용 |
| 건축물대장 총괄표제부 | 국토교통부 API (data.go.kr) | 세대수, 건물 정보 |
| 법정동코드 | 행정표준코드관리시스템 (code.go.kr) | 871개 동 매핑 |

> **크롤링 제로.** 모든 데이터는 정부 공공 API에서 합법적으로 수집합니다.

---

### 데이터 전처리

- **직거래 제외** — 가족 간 거래 등 시세 왜곡 요소 제거
- **1층 제외** — 평균가 끌어내림 방지, 로열층 기준 시세 산출
- **25~34평 (59~112㎡)** — 실거주 수요 최다 국민평형대만 필터
- **300세대 이상** — 소규모 단지 제외, 유동성 확보된 대단지만
- **동(洞) 단위 분리** — 같은 이름이라도 다른 동이면 별도 분석
- **최근 3개월 거래** 기준으로 현재 시세 산출

---

### 스코어링 (점수 산출 방식)
""")

    score_data = [
        {"항목": "📍 지역등급", "기준": "상급지 40 > 경기과천 30 > 중상급지 25 > 중하급지 10 > 하급지 0", "배점": "최대 40점"},
        {"항목": "💰 전세가율", "기준": "50~70% 최적. 벗어나면 감점 (역전세 리스크 / 갭 과다)", "배점": "최대 30점"},
        {"항목": "🏢 세대수", "기준": "100세대당 1점. 대단지 = 유동성/인프라 우수", "배점": "최대 20점"},
        {"항목": "📊 거래량", "기준": "최근 3개월 거래 건수. 활발한 거래 = 높은 유동성", "배점": "최대 15점"},
        {"항목": "📉 회복률", "기준": "22년 고점 대비 현재가. 100% 미만 가점(저평가), 초과 감점", "배점": "±30점"},
        {"항목": "🏛️ 토허제 변동", "기준": "10.15 토허제 전(24.7~9월) 대비. 덜 오를수록 가점", "배점": "±15점"},
    ]
    import pandas as pd
    st.dataframe(pd.DataFrame(score_data), width="stretch", hide_index=True)

    st.markdown("""
> **설계 철학**: "싸고 저평가된 곳"에 높은 점수를 줍니다.
> 회복률이 낮을수록, 토허제 후 덜 올랐을수록 가점이 붙어
> 무주택 실수요자에게 유리한 매물이 상위에 올라옵니다.

---

### 필터링 옵션

**재무 조건**: 종잣돈 / 계약연봉 / 인센티브 / 월 지출 / 매수자 유형 / 실거주 여부 / 갭투자 모드 / 대출 금리

**아파트 조건**: 지역등급 / 구·동 선택 / 회복률 범위 / 토허제 변동률 / 최소 세대수 / 상위 N개

---

### 제공 기능

| 기능 | 설명 |
|------|------|
| 🏆 TOP N 맞춤 추천 | 예산 범위 내 아파트를 스코어 순으로 랭킹 |
| 📈 매매가 추이 그래프 | 2020~현재 월별 평균 + 전고점/전저점 기준선 + 최근 실거래가(★) |
| 📋 시기별 가격 비교 | 상승기 고점 → 하락기 저점 → 현재 회복률 |
| 🏛️ 토허제 전후 비교 | 24.7~9월 vs 현재 변동률 |
| 🔄 갭투자 모드 | 전세 끼고 매수 시 필요한 내 돈 기준 필터링 |
| 📅 연도별 로드맵 | 매년 저축 시 7년간 매수 가능 금액 & 가능 지역 |
| 🏦 대출 상환 시뮬레이션 | 30년/15년/거치3년+27년 시나리오 비교 |
| 📊 실거래 내역 | 같은 평형 최근 15건 (거래일, 가격, 층, 직거래 여부) |

---

### 대출 한도 계산 로직

- **DSR 한도**: 원천징수 총급여 기준 DSR 40%. 스트레스 금리(+3%) 가산, 30년 원리금균등 기준
- **LTV 한도**: 생애최초 70% / 무주택 50% / 1주택 이하. 9억 이하·9~15억 구간별 차등
- **최종 한도**: DSR과 LTV 중 작은 값 = 실제 대출 가능 금액

---

### 기존 플랫폼과의 차이

| | 집피티 | 기존 부동산 플랫폼 |
|---|---|---|
| 접근 방식 | 내 조건 → 맞춤 추천 | 검색 → 매물 목록 → 직접 비교 |
| 대출 한도 | DSR+LTV+스트레스금리 자동 계산 | 별도 계산기 필요 |
| 랭킹 | 6개 항목 스코어링 | 없음 |
| 정책 반영 | 토허제 전후 비교 | 없음 |
| 저평가 발굴 | 회복률 기반 가점 | 시세만 표시 |
| 갭투자 | 전세가율 기반 자동 필터 | 직접 계산 |
| 장기 플랜 | 연도별 로드맵 | 없음 |
| 데이터 수집 | 100% 공공 API (합법) | 크롤링 기반 (법적 리스크) |

---

### 데이터 현황
""")

    if meta:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("분석 아파트", f"{meta.get('apt_count', 0):,}개")
        with col2:
            st.metric("매매 거래", f"{meta.get('trade_count', 0):,}건")
        with col3:
            st.metric("전월세 거래", f"{meta.get('rent_count', 0):,}건")
        with col4:
            st.metric("수집일", meta.get("collected_at", "?"))

    st.markdown("""
---

> ⚠️ **면책**: 본 서비스는 참고용 정보 제공 도구입니다. 투자 판단은 본인 책임이며,
> 실거래가는 시점·층·조건에 따라 다를 수 있습니다. 대출 한도는 은행/신용등급/상품에 따라 달라지므로
> 반드시 은행 상담을 병행하세요.
""")

# ─────────────────────────────────────
# 푸터
# ─────────────────────────────────────
st.divider()
st.caption("🏠 집피티 | 국토교통부 실거래가 API + 건축물대장 API 기반")
st.caption("※ 투자 판단은 본인 책임입니다. 참고용으로만 활용하세요.")
