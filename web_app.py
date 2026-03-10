"""
🏠 집피티 — 내집마련 AI 비서 — 웹앱 (토스 스타일 UX)
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
st.set_page_config(
    page_title="집피티 — 내집마련 AI 비서",
    page_icon="🏠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# 토스 스타일 CSS
st.markdown("""<style>
    /* 전체 */
    .block-container { max-width: 640px !important; padding: 1rem 1rem 4rem !important; }
    [data-testid="stSidebar"] { display: none; }
    h1 { font-size: 1.8rem !important; font-weight: 800 !important; letter-spacing: -1px; }
    h3 { font-size: 1.1rem !important; font-weight: 700 !important; margin-bottom: 0 !important; }
    /* 입력 필드 */
    .stNumberInput > div > div > input { font-size: 1.2rem !important; font-weight: 700 !important; }
    .stRadio > div { gap: 0.5rem; }
    .stRadio label { font-weight: 600 !important; }
    /* 카드 */
    .summary-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        border-radius: 16px; padding: 24px; margin: 16px 0; color: white;
    }
    .summary-card .big { font-size: 2rem; font-weight: 800; }
    .summary-card .sub { font-size: 0.9rem; opacity: 0.85; margin-top: 4px; }
    .apt-card {
        background: #1a1d26; border: 1px solid #2d3039; border-radius: 16px;
        padding: 20px; margin: 12px 0; transition: border-color 0.2s;
    }
    .apt-card:hover { border-color: #FF6B6B; }
    .apt-rank {
        display: inline-block; background: #FF6B6B; color: white;
        width: 28px; height: 28px; border-radius: 50%; text-align: center;
        line-height: 28px; font-weight: 800; font-size: 0.85rem; margin-right: 8px;
    }
    .apt-name { font-size: 1.1rem; font-weight: 700; }
    .apt-meta { font-size: 0.8rem; color: #9CA3AF; margin-top: 2px; }
    .metric-grid {
        display: grid; grid-template-columns: repeat(2, 1fr);
        gap: 4px 12px; margin: 12px 0 8px;
    }
    .metric-item {
        padding: 8px 0; border-bottom: 1px solid rgba(128,128,128,0.12);
    }
    .metric-label { font-size: 0.72rem; color: #888; display: block; }
    .metric-value { font-size: 0.95rem; font-weight: 600; }
    .tag {
        display: inline-block; padding: 2px 8px; border-radius: 4px;
        font-size: 0.7rem; font-weight: 600; margin-right: 4px;
    }
    .tag-green { background: rgba(81,207,102,0.15); color: #51CF66; }
    .tag-red { background: rgba(255,107,107,0.15); color: #FF6B6B; }
    .tag-blue { background: rgba(77,171,247,0.15); color: #4DABF7; }
    .tag-gray { background: rgba(156,163,175,0.1); color: #9CA3AF; }
    /* 구분선 */
    .divider { border-top: 1px solid #2d3039; margin: 20px 0; }
    /* 상세 설정 */
    .stExpander { border: 1px solid #2d3039 !important; border-radius: 12px !important; }
    /* word-break */
    * { word-break: keep-all; }
</style>""", unsafe_allow_html=True)

# ─────────────────────────────────────
# 데이터 로드
# ─────────────────────────────────────
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


@st.cache_data
def load_data():
    analysis, meta = [], {}
    path = os.path.join(DATA_DIR, "analysis.json")
    if os.path.exists(path):
        with open(path) as f:
            analysis = json.load(f)
    meta_path = os.path.join(DATA_DIR, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
    return analysis, meta


all_data, meta = load_data()
_seoul_gus = sorted(set(r["gu"] for r in all_data if "경기" not in r.get("tier", "")))
_gyeonggi_gus = sorted(set(r["gu"] for r in all_data if "경기" in r.get("tier", "")))


@st.cache_data
def load_trade_index():
    raw_path = os.path.join(DATA_DIR, "raw_trades.json")
    if not os.path.exists(raw_path):
        return {}
    idx = {}
    with open(raw_path) as f:
        raw_trades = json.load(f)
    for t in raw_trades:
        area_type = f"{int(t['area'])}㎡"
        key = (t["gu"], t["apt"], t.get("dong", ""), area_type)
        idx.setdefault(key, []).append(t)
    del raw_trades
    for key in idx:
        idx[key].sort(key=lambda x: (x["year"], x["month"]), reverse=True)
    return idx


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

    will_reside = st.checkbox("실거주 예정", value=True)
    gap_invest_mode = st.checkbox("갭투자 모드 (전세끼고 매수)", value=False)
    if gap_invest_mode:
        will_reside = False

    st.markdown("---")
    st.markdown("**필터**")

    tier_options = ["전체", "상급지", "상급지(경기)", "중상급지", "중상급지(경기)", "중하급지", "중하급지(경기)", "하급지", "하급지(경기)"]
    selected_tiers = st.multiselect("지역 등급", options=tier_options, default=["전체"])

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

# 상세 설정 밖에서 기본값 세팅
if "bonus" not in dir():
    bonus = 0
if "monthly_expense" not in dir():
    monthly_expense = 150
if "buyer_type" not in dir():
    buyer_type = BuyerType.FIRST_TIME
if "interest_rate" not in dir():
    interest_rate = 4.2
if "will_reside" not in dir():
    will_reside = True
if "gap_invest_mode" not in dir():
    gap_invest_mode = False
if "selected_tiers" not in dir():
    selected_tiers = ["전체"]
if "filter_all_gus" not in dir():
    filter_all_gus = True
if "effective_gus" not in dir():
    effective_gus = set(_seoul_gus + _gyeonggi_gus)
if "filter_all_dongs" not in dir():
    filter_all_dongs = True
if "selected_dongs" not in dir():
    selected_dongs = ["전체"]
if "max_recovery" not in dir():
    max_recovery = 200
if "max_policy_change" not in dir():
    max_policy_change = 100
if "min_hhld" not in dir():
    min_hhld = 300
if "top_n" not in dir():
    top_n = 10

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
loan_amount = int(sys_result.final_max_loan)

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
    if gap_invest_mode:
        budget_label = "갭투자 가능"
        budget_display = f"{budget / 10000:.1f}억"
    else:
        budget_label = "매수 가능 집값"
        budget_display = f"{budget / 10000:.1f}억"

    card_html = f"""
    <div class="summary-card">
        <div style="font-size:0.85rem;opacity:0.8">{budget_label}</div>
        <div class="big">{budget_display}</div>
        <div class="sub">
            종잣돈 {seed_money_억:.1f}억 + 대출 {loan_amount/10000:.1f}억
            &nbsp;·&nbsp; 월 상환 {monthly_pay:,.0f}만원 ({pay_ratio:.0f}%)
        </div>
    </div>
    """
    st.markdown(card_html, unsafe_allow_html=True)

    for w in sys_result.warnings:
        st.warning(w)
else:
    st.markdown("""
    <div class="summary-card" style="text-align:center;">
        <div class="big" style="font-size:1.5rem;">종잣돈과 연봉을 입력해보세요</div>
        <div class="sub">30초면 맞춤 추천을 받을 수 있어요</div>
    </div>
    """, unsafe_allow_html=True)

# ─────────────────────────────────────
# 탭
# ─────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["🏆 추천", "📈 로드맵", "🏦 상환", "ℹ️ 소개"])

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

        gap_budget = seed_money + loan_amount
        if gap_invest_mode:
            gap_max = int(gap_budget * 1.10)
            gap_min = int(gap_budget * 0.90)
        else:
            budget_max = int(budget * 1.10)
            budget_min = int(budget * 0.80)

        # 스코어링
        filter_all_tiers = "전체" in selected_tiers
        candidates = []
        for r in all_data:
            if r.get("hhld", 0) < min_hhld:
                continue
            if not filter_all_tiers and r.get("tier", "") not in selected_tiers:
                continue
            if not filter_all_gus and r["gu"] not in effective_gus:
                continue
            if not filter_all_dongs and r.get("dong", "") not in selected_dongs:
                continue
            rr = r.get("recovery_rate", 0)
            if rr < min_recovery or rr > max_recovery:
                continue
            pa = r.get("policy_avg", 0)
            if pa > 0:
                latest_p = r.get("latest_price", r["avg_price"])
                policy_pct = round((latest_p - pa) / pa * 100, 1)
                if policy_pct > max_policy_change:
                    continue

            if gap_invest_mode:
                apt_gap = r["gap"]
                if apt_gap > gap_max or apt_gap < gap_min:
                    continue
            else:
                if r["avg_price"] > budget_max or r["avg_price"] < budget_min:
                    continue

            # 스코어링
            tier_score = {
                "상급지": 40, "상급지(경기)": 30,
                "중상급지": 25, "중상급지(경기)": 20,
                "중하급지": 10, "중하급지(경기)": 8,
                "하급지": 0, "하급지(경기)": 0,
            }.get(r["tier"], 0)

            ratio_val = r["ratio"]
            if 50 <= ratio_val <= 70:
                ratio_score = 30
            elif ratio_val < 50:
                ratio_score = max(0, 30 - (50 - ratio_val) * 1.0)
            else:
                ratio_score = max(0, 30 - (ratio_val - 70) * 1.5)

            hhld_score = min(r.get("hhld", 0) / 100, 20)
            volume_score = min(r["count"] * 3, 15)

            if rr > 0:
                recovery_score = (100 - rr) * 0.3
                recovery_score = max(-30, min(30, recovery_score))
            else:
                recovery_score = 0

            pa = r.get("policy_avg", 0)
            if pa > 0:
                latest_p = r.get("latest_price", r["avg_price"])
                policy_pct_val = (latest_p - pa) / pa * 100
                policy_score = -policy_pct_val * 0.5
                policy_score = max(-15, min(15, policy_score))
            else:
                policy_score = 0

            score = round(tier_score + ratio_score + hhld_score + volume_score + recovery_score + policy_score, 1)

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
        top_list = candidates[:top_n]

        if top_list:
            st.caption(f"{len(candidates)}개 후보 중 TOP {len(top_list)}")

            for i, r in enumerate(top_list, 1):
                tier_emoji = {"상급지": "👑", "상급지(경기)": "👑", "중상급지": "🏙️", "중상급지(경기)": "🏙️", "중하급지": "🏘️", "중하급지(경기)": "🏘️", "하급지": "🏠", "하급지(경기)": "🏠"}.get(r["tier"], "")
                area_type = r.get("area_type", "")
                area_num = int(area_type.replace("㎡", "")) if "㎡" in area_type else 0
                pyeong = round(area_num * 0.3025) if area_num else ""
                dong = r.get("dong", "")
                loc = f"{r['gu']} {dong}" if dong else r['gu']
                latest = r.get("latest_price", r["avg_price"])
                latest_ym = r.get("latest_ym", "")
                gap = r["gap"]
                rr = r.get("recovery_rate", 0)

                # 태그
                tags = ""
                if rr > 0 and rr < 85:
                    tags += '<span class="tag tag-red">저평가</span>'
                elif rr > 0 and rr < 95:
                    tags += '<span class="tag tag-red">미회복</span>'
                elif rr >= 100:
                    tags += '<span class="tag tag-green">고점 돌파</span>'
                if r.get("hhld", 0) >= 1000:
                    tags += '<span class="tag tag-blue">대단지</span>'
                if r["ratio"] >= 65:
                    tags += '<span class="tag tag-green">소액갭</span>'
                if r["tier"] in ("상급지", "상급지(경기)"):
                    tags += '<span class="tag tag-gray">상급지</span>'

                # 10.15 변동
                pa = r.get("policy_avg", 0)
                policy_str = ""
                if pa > 0:
                    diff_policy = latest - pa
                    pct = round(diff_policy / pa * 100, 1)
                    policy_str = f'<div class="metric-item"><span class="metric-label">10.15 전후</span><span class="metric-value">{pct:+.1f}%</span></div>'

                # 회복률
                recovery_str = ""
                if rr > 0:
                    if rr >= 100:
                        recovery_str = f'<div class="metric-item"><span class="metric-label">22년 고점 대비</span><span class="metric-value" style="color:#51CF66">{rr:.0f}% 돌파</span></div>'
                    else:
                        recovery_str = f'<div class="metric-item"><span class="metric-label">22년 고점 대비</span><span class="metric-value" style="color:#FF6B6B">{rr:.0f}% ({100-rr:.0f}%↓)</span></div>'

                card_html = f"""
                <div class="apt-card">
                    <div>
                        <span class="apt-rank">{i}</span>
                        <span class="apt-name">{r['apt']}</span>
                    </div>
                    <div class="apt-meta">{tier_emoji} {loc} · {r['tier']} · {area_type}({pyeong}평) · {r.get('hhld',0):,}세대</div>
                    <div style="margin-top:8px">{tags}</div>
                    <div class="metric-grid">
                        <div class="metric-item"><span class="metric-label">최근 거래가</span><span class="metric-value">{latest/10000:.1f}억 <span style="font-size:0.7rem;color:#888">{latest_ym}</span></span></div>
                        <div class="metric-item"><span class="metric-label">전세가율</span><span class="metric-value">{r['ratio']:.0f}%</span></div>
                        <div class="metric-item"><span class="metric-label">갭(매매-전세)</span><span class="metric-value">{gap/10000:.1f}억</span></div>
                        <div class="metric-item"><span class="metric-label">월 상환</span><span class="metric-value">{r['monthly_pay']:,}만원</span></div>
                        {policy_str}
                        {recovery_str}
                    </div>
                </div>
                """
                st.markdown(card_html, unsafe_allow_html=True)

                # 시기별 비교 + 그래프 (접기)
                pcp = r.get("pre_crash_peak", 0)
                ct = r.get("crash_trough", 0)
                history = r.get("price_history", {})

                if (pcp > 0 and ct > 0) or (history and len(history) >= 2):
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
                            st.dataframe(pd.DataFrame(table_data), hide_index=True, use_container_width=True)

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
                            st.plotly_chart(fig, use_container_width=True)

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
                            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
        else:
            if gap_invest_mode:
                st.info(f"갭 범위에 맞는 아파트가 없어요. 상세 설정에서 조건을 조정해보세요.")
            elif seed_money > 0 or annual_income > 0:
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
        st.caption(f"연간 저축 {annual_saving/10000:.1f}억 기준 (월급저축 {(monthly_income-monthly_expense)*12:,}만 + 인센 {bonus:,}만)")

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
            if total_adj >= 150000: tiers.append("상급지")
            if total_adj >= 100000: tiers.append("중상급지")
            if total_adj >= 80000: tiers.append("중하급지")
            if total_adj >= 60000: tiers.append("하급지")
            roadmap_data.append({
                "연도": f"{year}년", "종잣돈": f"{s/10000:.0f}억",
                "대출": f"{loan_used/10000:.0f}억", "매수가능": f"{total_adj/10000:.1f}억",
                "가능지역": tiers[0] if tiers else "경기",
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
# 푸터
# ─────────────────────────────────────
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
st.caption("🏠 집피티 | 국토교통부 실거래가 API 기반 | 투자 판단은 본인 책임")
