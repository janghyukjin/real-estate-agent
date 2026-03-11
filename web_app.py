"""
🏠 집피티 — 내집마련 AI 비서 — 웹앱 (토스 스타일 + 스킬 기반)
"""
import streamlit as st
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.calculator import (
    BuyerType, LoanPolicy, UserFinance, calculate_affordability,
)
from src.constants import (
    TIER_DISPLAY, TIER_EMOJI, TIER_REVERSE, TIER_KEYS_ORDERED,
    PRESETS, ADVANCED_DEFAULTS,
)
from src.scoring import apply_skill_overrides, filter_and_score
from src.card_renderer import (
    render_summary_card, render_empty_summary_card, render_apt_card,
    render_community_skill_card, render_my_skill_card,
    build_skill_tags_html, build_my_skill_summary,
)

# ─────────────────────────────────────
# 데이터 로드 (@st.cache_data는 src/data_loader.py에 분리 — Python 3.14 tokenizer 호환)
# ─────────────────────────────────────
from src.data_loader import load_data, load_trade_index, load_community_skills

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@st.cache_data
def load_css():
    css_path = os.path.join(STATIC_DIR, "style.css")
    if os.path.exists(css_path):
        with open(css_path) as f:
            return f.read()
    return ""


all_data, meta = load_data()
_seoul_gus = sorted(set(r["gu"] for r in all_data if "경기" not in r.get("tier", "")))
_gyeonggi_gus = sorted(set(r["gu"] for r in all_data if "경기" in r.get("tier", "")))
COMMUNITY_SKILLS = load_community_skills()

# ─────────────────────────────────────
# 페이지 설정
# ─────────────────────────────────────
st.set_page_config(
    page_title="집피티 — 내집마련 AI 비서",
    page_icon="🏠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# CSS 로드
css_text = load_css()
if css_text:
    st.markdown(f"<style>{css_text}</style>", unsafe_allow_html=True)

# ─────────────────────────────────────
# 히어로
# ─────────────────────────────────────
st.markdown("# 🏠 집피티")
st.caption("내 월급으로 살 수 있는 저평가 아파트를 찾아드려요")

# ─────────────────────────────────────
# 핵심 입력 (3개만)
# ─────────────────────────────────────
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)
with col1:
    seed_money_억 = st.number_input(
        "💰 종잣돈 (억원)", min_value=0.0, max_value=50.0, value=0.0, step=0.5,
        help="현금 + 예금 + 주식 등 총 동원 가능 금액"
    )
with col2:
    contract_salary = st.number_input(
        "💵 계약연봉 (만원)", min_value=0, max_value=100000, value=0, step=100,
        help="인센/상여 제외, 세전 기준"
    )

seed_money = int(seed_money_억 * 10000)

region_choice = st.radio("📍 어디에서 찾을까요?", ["전체", "서울", "경기"], horizontal=True)

if "selected_preset" not in st.session_state:
    st.session_state.selected_preset = None

# ─────────────────────────────────────
# 상세 설정 (접기)
# ─────────────────────────────────────
with st.expander("⚙️ 상세 설정", expanded=False):
    st.caption("기본값으로도 충분해요. 세밀한 조정이 필요할 때 열어보세요.")

    adv_col1, adv_col2 = st.columns(2)
    with adv_col1:
        bonus = st.number_input(
            "인센티브/상여 (만원)", min_value=0, max_value=50000, value=0, step=100,
        )
        monthly_expense = st.number_input(
            "월 지출 (만원)", min_value=0, max_value=5000, value=150, step=50,
        )
    with adv_col2:
        buyer_type = st.selectbox(
            "매수자 유형",
            options=[BuyerType.FIRST_TIME, BuyerType.NO_HOUSE, BuyerType.ONE_HOUSE],
            format_func=lambda x: x.value,
        )
        interest_rate = st.slider(
            "대출 금리 (%)", min_value=2.5, max_value=6.0, value=4.2, step=0.1,
        )
    desired_loan_억 = st.number_input(
        "💰 희망 대출 (억원)",
        min_value=0.0, max_value=10.0, value=0.0, step=0.5,
        help="0이면 대출 없이 종잣돈으로만 매수. 한도 초과 시 자동으로 줄어듭니다.",
    )

    will_reside = st.checkbox("실거주 예정", value=True)
    gap_invest_mode = st.checkbox("갭투자 모드 (전세끼고 매수)", value=False)
    if gap_invest_mode:
        will_reside = False

    st.markdown("---")
    st.markdown("**필터**")

    tier_display_options = ["전체"] + [TIER_DISPLAY[t] for t in TIER_KEYS_ORDERED]
    selected_tier_displays = st.multiselect("지역 등급", options=tier_display_options, default=["전체"])
    # UI 표시명 → 내부명 변환
    if "전체" in selected_tier_displays:
        selected_tiers = ["전체"]
    else:
        selected_tiers = [TIER_REVERSE.get(d, d) for d in selected_tier_displays]

    if region_choice == "서울":
        available_gus = _seoul_gus
    elif region_choice == "경기":
        available_gus = _gyeonggi_gus
    else:
        available_gus = sorted(_seoul_gus + _gyeonggi_gus)
    selected_gus = st.multiselect("구 선택", options=["전체"] + available_gus, default=["전체"])
    if "전체" in selected_gus:
        effective_gus = set(available_gus)
        filter_all_gus = (region_choice == "전체")
    else:
        effective_gus = set(selected_gus)
        filter_all_gus = False

    all_dongs = sorted(set(r.get("dong", "") for r in all_data
                           if r.get("dong") and (filter_all_gus or r["gu"] in effective_gus)))
    if all_dongs:
        selected_dongs = st.multiselect("동 선택", options=["전체"] + all_dongs, default=["전체"])
        filter_all_dongs = "전체" in selected_dongs
    else:
        selected_dongs = ["전체"]
        filter_all_dongs = True

    max_recovery = st.slider(
        "최대 회복률 — 22년 고점 대비 (%)", 0, 200, 200, 5,
        help="100% 미만 = 아직 고점 못 돌파 (저평가). 낮출수록 더 저평가된 곳만 표시"
    )
    min_recovery = 0
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        max_policy_change = st.slider("토허제 후 최대 변동률 (%)", -100, 100, 100, 5)
    with f_col2:
        min_hhld = st.number_input("최소 세대수", min_value=300, max_value=5000, value=300, step=100)

    top_n = st.number_input("상위 표시 개수", min_value=5, max_value=50, value=10, step=5)

    # 전략 프리셋 (상세 설정 하단)
    st.markdown("---")
    st.markdown("**🎯 전략 프리셋** (원클릭 필터)")
    preset_keys = list(PRESETS.keys())
    row1 = preset_keys[:3]
    p_cols = st.columns(3)
    for idx, key in enumerate(row1):
        with p_cols[idx]:
            if st.button(key, key=f"preset_{idx}", width="stretch"):
                if st.session_state.selected_preset == key:
                    st.session_state.selected_preset = None
                else:
                    st.session_state.selected_preset = key
    row2 = preset_keys[3:]
    if row2:
        p_cols2 = st.columns(3)
        for idx, key in enumerate(row2):
            with p_cols2[idx]:
                if st.button(key, key=f"preset_{idx+3}", width="stretch"):
                    if st.session_state.selected_preset == key:
                        st.session_state.selected_preset = None
                    else:
                        st.session_state.selected_preset = key

    active_preset = st.session_state.get("selected_preset")
    if active_preset and active_preset in PRESETS:
        p_info = PRESETS[active_preset]
        st.success(f"🎯 **{active_preset}** — {p_info['desc']}")
    elif st.session_state.get("active_community_skill"):
        cs_desc = st.session_state.active_community_skill.get("desc", "커뮤니티 스킬")
        st.info(f"🎯 커스텀 스킬 적용 중 — {cs_desc}")
        if st.button("해제", key="clear_community_skill"):
            st.session_state.active_community_skill = None
            st.rerun()

# 상세 설정 기본값 — Streamlit expander는 항상 실행되므로 여기는 안전장치
_d = ADVANCED_DEFAULTS
bonus = locals().get("bonus", _d["bonus"])
monthly_expense = locals().get("monthly_expense", _d["monthly_expense"])
buyer_type = locals().get("buyer_type", BuyerType.FIRST_TIME)
interest_rate = locals().get("interest_rate", _d["interest_rate"])
will_reside = locals().get("will_reside", _d["will_reside"])
gap_invest_mode = locals().get("gap_invest_mode", _d["gap_invest_mode"])
selected_tiers = locals().get("selected_tiers", _d["selected_tiers"])
filter_all_gus = locals().get("filter_all_gus", _d["filter_all_gus"])
effective_gus = locals().get("effective_gus", set(_seoul_gus + _gyeonggi_gus))
filter_all_dongs = locals().get("filter_all_dongs", _d["filter_all_dongs"])
selected_dongs = locals().get("selected_dongs", _d["selected_dongs"])
max_recovery = locals().get("max_recovery", _d["max_recovery"])
max_policy_change = locals().get("max_policy_change", _d["max_policy_change"])
min_hhld = locals().get("min_hhld", _d["min_hhld"])
top_n = locals().get("top_n", _d["top_n"])
desired_loan_억 = locals().get("desired_loan_억", 0.0)

# ─────────────────────────────────────
# 프리셋/스킬 오버라이드 적용
# ─────────────────────────────────────
active_preset = st.session_state.get("selected_preset")
active_community = st.session_state.get("active_community_skill")

if active_preset and active_preset in PRESETS:
    st.session_state.active_community_skill = None  # 프리셋 선택 시 커뮤니티 해제
    active_community = None

filter_params = {
    "max_recovery": max_recovery, "min_hhld": min_hhld,
    "effective_gus": effective_gus, "filter_all_gus": filter_all_gus,
    "selected_tiers": selected_tiers, "min_recovery": 0,
    "max_policy_change": max_policy_change,
}
apply_skill_overrides(filter_params, active_preset, active_community)

# 오버라이드된 값 꺼내기
max_recovery = filter_params["max_recovery"]
min_hhld = filter_params["min_hhld"]
effective_gus = filter_params["effective_gus"]
filter_all_gus = filter_params["filter_all_gus"]
selected_tiers = filter_params["selected_tiers"]
min_recovery = filter_params.get("min_recovery", 0)
max_policy_change = filter_params["max_policy_change"]

# ─────────────────────────────────────
# 자동 계산
# ─────────────────────────────────────
annual_income = contract_salary + bonus
monthly_income = contract_salary // 12 if contract_salary > 0 else 0
dsr_monthly_income = annual_income // 12 if annual_income > 0 else 0

policy = LoanPolicy(base_interest_rate=interest_rate / 100)
user = UserFinance(
    seed_money=seed_money, monthly_income=dsr_monthly_income,
    monthly_expense=monthly_expense, buyer_type=buyer_type,
    will_reside=will_reside,
)
sys_result = calculate_affordability(user, policy)
max_loan = int(sys_result.final_max_loan)

# 희망 대출 적용 (0이면 대출 없음)
loan_over_limit = False
if desired_loan_억 > 0:
    desired_loan = int(desired_loan_억 * 10000)
    if desired_loan > max_loan:
        loan_over_limit = True
    loan_amount = min(desired_loan, max_loan)
else:
    loan_amount = 0

budget = seed_money + loan_amount
mr = (interest_rate / 100) / 12
n = 360
if loan_amount > 0 and mr > 0:
    monthly_pay = loan_amount * (mr * (1 + mr) ** n) / ((1 + mr) ** n - 1)
else:
    monthly_pay = 0

pay_ratio = monthly_pay / monthly_income * 100 if monthly_income > 0 else 0

# ─────────────────────────────────────
# 결과 요약 카드
# ─────────────────────────────────────
if seed_money > 0 or annual_income > 0:
    budget_label = "갭투자 가능" if gap_invest_mode else "매수 가능 집값"
    budget_display = f"{budget / 10000:.1f}억"
    st.markdown(
        render_summary_card(budget_label, budget_display, seed_money_억, loan_amount, monthly_pay, pay_ratio, max_loan=max_loan),
        unsafe_allow_html=True,
    )
    if loan_over_limit:
        if max_loan > 0:
            st.warning(f"희망 대출 {desired_loan_억:.1f}억이 한도({max_loan/10000:.1f}억)를 초과하여 {max_loan/10000:.1f}억으로 적용됩니다.", icon=None)
        else:
            st.warning(f"희망 대출 {desired_loan_억:.1f}억을 입력했지만 연봉 미입력으로 대출 한도가 0입니다. 연봉을 입력해주세요.", icon=None)
    if sys_result.warnings:
        with st.expander(f"참고사항 ({len(sys_result.warnings)}건)", expanded=False):
            for w in sys_result.warnings:
                st.warning(w, icon=None)
else:
    st.markdown(render_empty_summary_card(), unsafe_allow_html=True)

# ─────────────────────────────────────
# 탭
# ─────────────────────────────────────
tab1, tab5, tab2, tab3, tab4 = st.tabs(["🏆 추천", "🎯 스킬", "📈 로드맵", "🏦 상환", "ℹ️ 소개"])

# ─────────────────────────────────────
# TAB 1: TOP N 추천
# ─────────────────────────────────────
with tab1:
    if not all_data:
        st.error("분석 데이터가 없습니다.")
    elif seed_money == 0 and annual_income == 0:
        st.info("위에서 종잣돈과 연봉을 입력하면 맞춤 추천이 시작돼요!")
    else:
        if meta:
            st.caption(f"📊 {meta.get('apt_count', 0):,}개 아파트 · 매매 {meta.get('trade_count', 0):,}건 · 전세 {meta.get('rent_count', 0):,}건")

        scoring_params = {
            "min_hhld": min_hhld, "selected_tiers": selected_tiers,
            "filter_all_gus": filter_all_gus, "effective_gus": effective_gus,
            "filter_all_dongs": filter_all_dongs, "selected_dongs": selected_dongs,
            "min_recovery": min_recovery, "max_recovery": max_recovery,
            "max_policy_change": max_policy_change,
            "gap_invest_mode": gap_invest_mode, "budget": budget,
            "seed_money": seed_money, "loan_amount": loan_amount,
            "interest_rate": interest_rate,
        }
        candidates = filter_and_score(all_data, scoring_params, active_preset, active_community)
        top_list = candidates[:top_n]

        if top_list:
            st.caption(f"{len(candidates)}개 후보 중 TOP {len(top_list)}")

            for i, r in enumerate(top_list, 1):
                st.markdown(render_apt_card(i, r), unsafe_allow_html=True)

                # 상세 분석 (접기)
                pcp = r.get("pre_crash_peak", 0)
                ct = r.get("crash_trough", 0)
                history = r.get("price_history", {})

                if (pcp > 0 and ct > 0) or (history and len(history) >= 2):
                    rr = r.get("recovery_rate", 0)
                    with st.expander(f"📊 {r['apt']} 상세 분석"):
                        if pcp > 0 and ct > 0:
                            import pandas as pd
                            crash_drop = pcp - ct
                            current_vs = r["avg_price"] - pcp
                            table_data = [
                                {"시기": "상승기 고점 (20~22)", "가격": f"{pcp/10000:.1f}억", "시점": r.get("pre_crash_ym", ""), "현재 대비": f"{current_vs/10000:+.1f}억"},
                                {"시기": "하락기 저점 (23~24)", "가격": f"{ct/10000:.1f}억", "시점": r.get("crash_trough_ym", ""), "현재 대비": f"{(r['avg_price']-ct)/10000:+.1f}억"},
                                {"시기": "하락 폭", "가격": f"-{crash_drop/10000:.1f}억", "시점": "", "현재 대비": f"고점 대비 {crash_drop/pcp*100:.0f}%↓"},
                                {"시기": "현재", "가격": f"{r['avg_price']/10000:.1f}억", "시점": "최근 3개월", "현재 대비": f"회복률 {rr:.0f}%"},
                            ]
                            st.dataframe(pd.DataFrame(table_data), hide_index=True, width="stretch")

                        if history and len(history) >= 2:
                            import pandas as pd
                            import plotly.graph_objects as go
                            sorted_h = sorted(history.items())
                            yms = [ym for ym, _ in sorted_h]
                            prices = [p / 10000 for _, p in sorted_h]
                            fig = go.Figure()
                            fig.add_trace(go.Scatter(
                                x=yms, y=prices, mode="lines+markers",
                                line=dict(color="#FF6B6B", width=2.5), marker=dict(size=4),
                                hovertemplate="%{x}<br>%{y:.1f}억원<extra></extra>",
                            ))
                            latest_p = r.get("latest_price", 0)
                            latest_ym_g = r.get("latest_ym", "")
                            if latest_p and latest_ym_g:
                                fig.add_trace(go.Scatter(
                                    x=[latest_ym_g], y=[latest_p / 10000],
                                    mode="markers+text",
                                    marker=dict(size=12, color="#FF6B6B", symbol="star", line=dict(width=2, color="white")),
                                    text=[f"{latest_p/10000:.1f}억"], textposition="top center",
                                    textfont=dict(size=11, color="#FF6B6B"),
                                    hovertemplate=f"최근 실거래가<br>{latest_ym_g}<br>{latest_p/10000:.1f}억원<extra></extra>",
                                ))
                            fig.add_hline(y=r["peak"]/10000, line_dash="dash", line_color="red", opacity=0.5,
                                          annotation_text=f"전고점 {r['peak']/10000:.1f}억", annotation_position="top left")
                            fig.add_hline(y=r["trough"]/10000, line_dash="dash", line_color="blue", opacity=0.5,
                                          annotation_text=f"전저점 {r['trough']/10000:.1f}억", annotation_position="bottom left")
                            fig.update_layout(height=280, margin=dict(l=0, r=0, t=20, b=0),
                                              xaxis_title="", yaxis_title="억원",
                                              hovermode="x unified", showlegend=False)
                            st.plotly_chart(fig, width="stretch")

                        # 실거래 내역
                        trade_index = load_trade_index()
                        trades_filtered = trade_index.get((r["gu"], r["apt"], r.get("dong", ""), r.get("area_type", "")), [])
                        if trades_filtered:
                            import pandas as pd
                            st.markdown("**최근 실거래 내역**")
                            rows = []
                            for t in trades_filtered[:15]:
                                floor = t.get("floor", "")
                                floor_str = f"{floor}층" if floor else ""
                                if floor == 1:
                                    floor_str = "⚠️ 1층"
                                deal_type = t.get("deal_type", "")
                                rows.append({
                                    "거래일": f"{t['year']}.{t['month']:02d}",
                                    "매매가": f"{t['price']/10000:.1f}억",
                                    "층": floor_str,
                                    "비고": "직거래" if deal_type == "직거래" else "",
                                })
                            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

        else:
            if gap_invest_mode:
                st.info("갭 범위에 맞는 아파트가 없어요. 상세 설정에서 조건을 조정해보세요.")
            elif seed_money > 0 or annual_income > 0:
                budget_max = int(budget * 1.10)
                budget_min = int(budget * 0.80)
                st.info(f"예산 범위({budget_min/10000:.1f}~{budget_max/10000:.1f}억)에 맞는 아파트가 없어요. 조건을 조정해보세요.")

# ─────────────────────────────────────
# TAB 2: 로드맵
# ─────────────────────────────────────
with tab2:
    st.markdown("### 📈 연도별 매수 가능 금액")
    annual_saving = (monthly_income - monthly_expense) * 12 + bonus
    annual_save = int(annual_saving)

    if annual_income == 0:
        st.info("연봉을 입력하면 연도별 로드맵을 볼 수 있어요.")
    else:
        st.caption(f"연간 저축 {annual_saving/10000:.1f}억 기준")
        roadmap_data = []
        for yr in range(7):
            year = 2026 + yr
            s = seed_money + annual_save * yr
            total = s + loan_amount
            if total > 150000:
                loan_used = min(loan_amount, 40000)
                total_adj = s + loan_used
            else:
                loan_used = loan_amount
                total_adj = total
            tiers = []
            if total_adj >= 150000: tiers.append("1티어")
            if total_adj >= 100000: tiers.append("2티어")
            if total_adj >= 80000: tiers.append("3티어")
            if total_adj >= 60000: tiers.append("4티어")
            roadmap_data.append({
                "연도": f"{year}년", "종잣돈": f"{s/10000:.0f}억",
                "대출": f"{loan_used/10000:.0f}억", "매수가능": f"{total_adj/10000:.1f}억",
                "가능지역": tiers[0] if tiers else "경기 4티어",
            })
        st.table(roadmap_data)
        st.caption("⚠️ 15억 초과 시 대출 한도 축소")

# ─────────────────────────────────────
# TAB 3: 상환 시뮬
# ─────────────────────────────────────
with tab3:
    st.markdown("### 🏦 대출 상환 시뮬레이션")

    if loan_amount <= 0:
        st.info("대출 금액을 확인해주세요.")
    else:
        sim_loan_억 = st.slider(
            "대출 금액 (억원)", min_value=0.5,
            max_value=max(loan_amount / 10000, 1.0),
            value=max(loan_amount / 10000, 0.5), step=0.5,
        )
        sim_loan = int(sim_loan_억 * 10000)
        r_monthly = (interest_rate / 100) / 12

        scenarios = [
            ("30년 원리금균등", 30, False),
            ("15년 조기상환", 15, False),
            ("거치3년+27년", 30, True),
        ]

        for name, years, is_grace in scenarios:
            months_s = years * 12
            if is_grace:
                grace_pay = sim_loan * (interest_rate / 100) / 12
                after_months = 27 * 12
                after_pay = sim_loan * (r_monthly * (1 + r_monthly) ** after_months) / ((1 + r_monthly) ** after_months - 1)
                total_interest = grace_pay * 36 + after_pay * after_months - sim_loan
                pay_str = f"처음 3년 **{grace_pay:,.0f}만** → 이후 **{after_pay:,.0f}만**/월"
            else:
                monthly_s = sim_loan * (r_monthly * (1 + r_monthly) ** months_s) / ((1 + r_monthly) ** months_s - 1)
                total_interest = monthly_s * months_s - sim_loan
                pct = monthly_s / monthly_income * 100 if monthly_income > 0 else 0
                pay_str = f"월 **{monthly_s:,.0f}만원**" + (f" (월급의 {pct:.0f}%)" if pct > 0 else "")

            st.markdown(f"""
            <div style="background:#1a1d26;border:1px solid #2d3039;border-radius:12px;padding:16px;margin:8px 0">
                <div style="font-weight:700;margin-bottom:4px">{name}</div>
                <div style="font-size:0.9rem">{pay_str}</div>
                <div style="font-size:0.8rem;color:#888;margin-top:4px">총 이자: {total_interest/10000:.1f}억</div>
            </div>
            """, unsafe_allow_html=True)

        st.caption("※ 실제 금리·수수료는 은행/상품에 따라 다름")

# ─────────────────────────────────────
# TAB 4: 소개
# ─────────────────────────────────────
with tab4:
    st.markdown("### ℹ️ 집피티")
    st.markdown("""
**집피티**는 무주택 실수요자를 위한 아파트 맞춤 추천 도구입니다.

내 연봉·종잣돈을 입력하면 DSR/LTV를 자동 계산하고,
예산에 맞는 아파트를 **6가지 항목으로 스코어링**하여 순위를 매깁니다.

---

**데이터**: 국토교통부 실거래가 API + 건축물대장 API (100% 공공 데이터)

**전처리**: 직거래 제외 · 1층 제외 · 25~34평 · 300세대+ · 최근 3개월 거래 기준

**스코어링**: 지역등급(40) + 전세가율(30) + 세대수(20) + 거래량(15) + 회복률(±30) + 토허제(±15)

> 설계 철학: "싸고 저평가된 곳"에 높은 점수를 줍니다.

---
""")
    if meta:
        st.markdown(f"""
| 항목 | 수치 |
|------|------|
| 분석 아파트 | {meta.get('apt_count', 0):,}개 |
| 매매 거래 | {meta.get('trade_count', 0):,}건 |
| 전월세 거래 | {meta.get('rent_count', 0):,}건 |
| 수집일 | {meta.get('collected_at', '?')} |
""")

    st.markdown("""
---
> ⚠️ 본 서비스는 참고용 정보 제공 도구입니다. 투자 판단은 본인 책임이며,
> 대출 한도는 은행/신용등급/상품에 따라 달라지므로 반드시 은행 상담을 병행하세요.
""")

# ─────────────────────────────────────
# TAB 5: 스킬 (커스텀 + 커뮤니티)
# ─────────────────────────────────────
with tab5:
    st.markdown("### 🎯 스킬 마켓 <span style='display:inline-block;background:linear-gradient(135deg,#667eea,#764ba2);color:white;padding:2px 10px;border-radius:12px;font-size:0.65rem;font-weight:700;vertical-align:middle;margin-left:8px'>BETA</span>", unsafe_allow_html=True)
    st.caption("다른 투자자의 전략을 구경하고, 나만의 스킬을 만들어보세요")

    # 온보딩 가이드
    with st.expander("💡 스킬이 뭔가요? (처음이라면 읽어보세요)"):
        st.markdown("""
**스킬 = 나만의 투자 필터 조합**

집피티는 **스킬 기반**으로 동작해요.
"어디서, 어떤 조건으로, 어떻게 정렬할지"를 하나의 스킬로 만들면
매번 필터를 다시 설정할 필요 없이 **원클릭으로 전략을 적용**할 수 있어요.

1. **커뮤니티 랭킹** — 다른 투자자들이 만든 인기 전략을 구경
2. **마음에 드는 스킬 적용** — 버튼 한 번이면 🏆 추천 탭에 바로 반영
3. **직접 만들기** — 원하는 조건을 조합해서 나만의 스킬 생성

> ⚠️ 현재 Beta: 스킬은 현재 세션에만 저장돼요. 새로고침하면 초기화됩니다.
> 향후 로그인 기능과 함께 영구 저장이 지원될 예정이에요.
""")

    # 세션 초기화
    if "custom_skills" not in st.session_state:
        st.session_state.custom_skills = []

    skill_section = st.radio(
        "skill_section", ["🏆 커뮤니티 랭킹", "✏️ 스킬 만들기", "📁 내 스킬"],
        horizontal=True, label_visibility="collapsed",
    )

    # ── 커뮤니티 스킬 랭킹 ──
    if skill_section == "🏆 커뮤니티 랭킹":
        if not COMMUNITY_SKILLS:
            st.info("커뮤니티 스킬이 아직 없습니다.")
        else:
            st.caption(f"{len(COMMUNITY_SKILLS)}개 스킬 · 좋아요순")
            ranked = sorted(COMMUNITY_SKILLS, key=lambda s: -s["likes"])
            saved_names = {s["name"] for s in st.session_state.custom_skills}

            for rank, skill in enumerate(ranked, 1):
                cfg = skill.get("config", {})
                tags_html = build_skill_tags_html(cfg)
                st.markdown(render_community_skill_card(rank, skill, tags_html), unsafe_allow_html=True)

                col_a, col_b = st.columns([1, 1])
                with col_a:
                    if skill["name"] in saved_names:
                        st.button("✅ 저장됨", key=f"comm_save_{rank}", disabled=True, width="stretch")
                    else:
                        if st.button("💾 내 스킬로 저장", key=f"comm_save_{rank}", width="stretch"):
                            st.session_state.custom_skills.append({
                                "name": skill["name"], "desc": skill["desc"],
                                "author": skill["author"], "config": cfg, "source": "community",
                            })
                            st.toast(f"✅ '{skill['name']}' 저장!")
                            st.rerun()
                with col_b:
                    if st.button("🎯 바로 적용", key=f"comm_apply_{rank}", width="stretch"):
                        st.session_state.active_community_skill = cfg
                        st.session_state.selected_preset = None
                        st.toast(f"✅ '{skill['name']}' 적용! 🏆 추천 탭을 확인하세요")

    # ── 스킬 만들기 ──
    elif skill_section == "✏️ 스킬 만들기":
        st.markdown("""
        <div style="background:#1a1d26;border:1px solid #2d3039;border-radius:12px;padding:14px;margin:8px 0;font-size:0.85rem">
            💡 모든 항목을 채울 필요 없어요. 원하는 조건만 설정하면 나머지는 기본값이 적용됩니다.
        </div>
        """, unsafe_allow_html=True)

        with st.form("create_skill_form"):
            skill_name = st.text_input(
                "스킬 이름 *", placeholder="예: 나의 강남 저평가 전략",
                help="나중에 구분하기 쉬운 이름을 지어주세요",
            )
            skill_desc = st.text_input(
                "설명", placeholder="예: 강남3구에서 고점 대비 80% 미만 회복된 대단지",
                help="어떤 전략인지 간단히 메모 (선택)",
            )

            st.markdown("**📍 지역 조건**")
            cs_col1, cs_col2 = st.columns(2)
            with cs_col1:
                cs_tiers_display = st.multiselect(
                    "지역 등급", options=[TIER_DISPLAY[t] for t in TIER_KEYS_ORDERED],
                    default=[], key="cs_tiers",
                    help="비워두면 전체 등급에서 찾아요",
                )
            with cs_col2:
                cs_gus = st.multiselect(
                    "특정 구", options=sorted(_seoul_gus + _gyeonggi_gus),
                    default=[], key="cs_gus",
                    help="비워두면 전체 구에서 찾아요",
                )

            st.markdown("**🏢 아파트 조건**")
            ac_col1, ac_col2 = st.columns(2)
            with ac_col1:
                cs_min_hhld = st.number_input(
                    "최소 세대수", min_value=300, max_value=5000, value=300, step=100, key="cs_hhld",
                    help="대단지를 원하면 1000+",
                )
            with ac_col2:
                cs_min_ratio = st.number_input(
                    "최소 전세가율 (%)", min_value=0, max_value=100, value=0, step=5, key="cs_ratio",
                    help="소액갭은 65%+ 추천",
                )

            st.markdown("**📈 가격 조건**")
            pr_col1, pr_col2 = st.columns(2)
            with pr_col1:
                cs_max_recovery = st.slider(
                    "최대 회복률 (22년 고점 대비 %)", 0, 200, 200, 5, key="cs_recovery",
                    help="낮출수록 저평가. 90% = 아직 10%↓",
                )
            with pr_col2:
                cs_max_gap = st.number_input(
                    "최대 갭 (만원, 0=제한없음)", min_value=0, max_value=200000, value=0, step=5000, key="cs_gap",
                    help="소액갭이면 20000(2억) 추천",
                )

            st.markdown("**🔢 정렬**")
            cs_sort = st.selectbox(
                "결과 정렬", ["🏆 종합 점수순 (기본)", "💰 갭 적은순 (소액갭)", "📉 급매순 (최근 하락)"],
                key="cs_sort", help="추천 리스트 정렬 기준",
            )

            submitted = st.form_submit_button("💾 스킬 저장하기", width="stretch")

        if submitted:
            if not skill_name.strip():
                st.error("스킬 이름을 입력해주세요!")
            else:
                new_cfg = {}
                if cs_tiers_display:
                    new_cfg["force_tiers"] = [TIER_REVERSE.get(d, d) for d in cs_tiers_display]
                if cs_gus:
                    new_cfg["force_gus"] = cs_gus
                if cs_min_hhld > 300:
                    new_cfg["min_hhld"] = cs_min_hhld
                if cs_max_recovery < 200:
                    new_cfg["max_recovery"] = cs_max_recovery
                if cs_min_ratio > 0:
                    new_cfg["min_ratio"] = cs_min_ratio
                if cs_max_gap > 0:
                    new_cfg["max_gap"] = cs_max_gap
                sort_map = {"💰 갭 적은순 (소액갭)": "gap_asc", "📉 급매순 (최근 하락)": "drop_desc"}
                if cs_sort in sort_map:
                    new_cfg["sort_by"] = sort_map[cs_sort]

                # 같은 이름 덮어쓰기
                st.session_state.custom_skills = [
                    s for s in st.session_state.custom_skills if s["name"] != skill_name.strip()
                ]
                st.session_state.custom_skills.append({
                    "name": skill_name.strip(),
                    "desc": skill_desc.strip() or skill_name.strip(),
                    "author": "나", "config": new_cfg, "source": "custom",
                })
                st.success(f"✅ '{skill_name}' 저장 완료! 📁 내 스킬 탭에서 확인하세요")

    # ── 내 스킬 ──
    elif skill_section == "📁 내 스킬":
        saved = st.session_state.custom_skills
        if not saved:
            st.markdown("""
            <div style="text-align:center;padding:40px 20px;color:#888">
                <div style="font-size:2rem;margin-bottom:12px">📭</div>
                <div style="font-size:1rem;font-weight:600;margin-bottom:8px">아직 저장된 스킬이 없어요</div>
                <div style="font-size:0.85rem">
                    🏆 커뮤니티 랭킹에서 마음에 드는 스킬을 저장하거나<br>
                    ✏️ 스킬 만들기에서 직접 만들어보세요!
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.caption(f"💾 {len(saved)}개 스킬 · 현재 세션에 저장됨")

            for idx, skill in enumerate(saved):
                cfg = skill.get("config", {})
                source_tag = ""
                if skill.get("source") == "community":
                    source_tag = '<span class="tag tag-blue">커뮤니티</span>'
                elif skill.get("source") == "custom":
                    source_tag = '<span class="tag tag-green">직접 만든 스킬</span>'

                summary = build_my_skill_summary(cfg)
                st.markdown(render_my_skill_card(skill, source_tag, summary), unsafe_allow_html=True)

                c1, c2 = st.columns([4, 1])
                with c1:
                    if st.button("🎯 추천에 적용", key=f"my_apply_{idx}", width="stretch"):
                        st.session_state.active_community_skill = cfg
                        st.session_state.selected_preset = None
                        st.toast(f"✅ '{skill['name']}' 적용! 🏆 추천 탭을 확인하세요")
                with c2:
                    if st.button("🗑️", key=f"my_del_{idx}", width="stretch"):
                        st.session_state.custom_skills.pop(idx)
                        st.rerun()

            # JSON 내보내기/가져오기
            st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
            st.caption("💡 JSON으로 내보내면 나중에 다시 가져올 수 있어요")
            exp_col, imp_col = st.columns(2)
            with exp_col:
                st.download_button(
                    "📤 내보내기", data=json.dumps(saved, ensure_ascii=False, indent=2),
                    file_name="jipiti_skills.json", mime="application/json", width="stretch",
                )
            with imp_col:
                uploaded = st.file_uploader("📥", type=["json"], key="skill_import", label_visibility="collapsed")

            if uploaded:
                try:
                    imported = json.loads(uploaded.read().decode("utf-8"))
                    if isinstance(imported, list):
                        existing = {s["name"] for s in st.session_state.custom_skills}
                        added = sum(1 for s in imported if isinstance(s, dict) and s.get("name") and s["name"] not in existing)
                        for s in imported:
                            if isinstance(s, dict) and s.get("name") and s["name"] not in existing:
                                st.session_state.custom_skills.append(s)
                        if added:
                            st.success(f"✅ {added}개 스킬 가져오기 완료!")
                            st.rerun()
                        else:
                            st.info("새로 추가할 스킬이 없어요")
                    else:
                        st.error("올바른 JSON 형식이 아닙니다")
                except Exception as e:
                    st.error(f"파일 오류: {e}")

# 푸터
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
st.caption("🏠 집피티 | 국토교통부 실거래가 API 기반 | 투자 판단은 본인 책임")
