"""
집피티 HTML 카드 렌더링 함수
"""
from src.constants import TIER_DISPLAY, TIER_EMOJI


def render_summary_card(budget_label, budget_display, seed_money_억, loan_amount, monthly_pay, pay_ratio, max_loan=None):
    """결과 요약 카드 HTML을 반환한다."""
    loan_line = f"대출 {loan_amount/10000:.1f}억"
    if max_loan is not None and max_loan != loan_amount:
        loan_line += f" <span style='font-size:0.75rem;opacity:0.7'>(한도 {max_loan/10000:.1f}억)</span>"
    return f"""<div class="summary-card">
<div style="font-size:0.85rem;opacity:0.8">{budget_label}</div>
<div class="big">{budget_display}</div>
<div class="sub">종잣돈 {seed_money_억:.1f}억 + {loan_line} &nbsp;&middot;&nbsp; 월 상환 {monthly_pay:,.0f}만원 ({pay_ratio:.0f}%)</div>
</div>"""


def render_empty_summary_card():
    """입력 전 빈 요약 카드 HTML을 반환한다."""
    return """<div class="summary-card" style="text-align:center;">
<div class="big" style="font-size:1.5rem;">종잣돈과 연봉을 입력해보세요</div>
<div class="sub">30초면 맞춤 추천을 받을 수 있어요</div>
</div>"""


def render_apt_card(rank, r):
    """아파트 추천 카드 HTML을 반환한다."""
    tier_display = TIER_DISPLAY.get(r["tier"], r["tier"])
    tier_emoji = TIER_EMOJI.get(r["tier"], "")
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
    tags = _build_tags(r, rr)

    # 10.15 변동
    policy_str = _build_policy_metric(r, latest)

    # 회복률
    recovery_str = _build_recovery_metric(rr)

    return f"""<div class="apt-card">
<div><span class="apt-rank">{rank}</span><span class="apt-name">{r['apt']}</span></div>
<div class="apt-meta">{tier_emoji} {loc} &middot; {tier_display} &middot; {area_type}({pyeong}평) &middot; {r.get('hhld',0):,}세대</div>
<div style="margin-top:8px">{tags}</div>
<div class="metric-grid">
<div class="metric-item"><span class="metric-label">최근 거래가</span><span class="metric-value">{latest/10000:.1f}억 <span style="font-size:0.7rem;color:#888">{latest_ym}</span></span></div>
<div class="metric-item"><span class="metric-label">전세가율</span><span class="metric-value">{r['ratio']:.0f}%</span></div>
<div class="metric-item"><span class="metric-label">갭(매매-전세)</span><span class="metric-value">{gap/10000:.1f}억</span></div>
<div class="metric-item"><span class="metric-label">월 상환</span><span class="metric-value">{r['monthly_pay']:,}만원</span></div>
{policy_str}{recovery_str}
</div></div>"""


def render_community_skill_card(rank, skill, tags_html):
    """커뮤니티 스킬 카드 HTML을 반환한다."""
    medal = {1: "\U0001f947", 2: "\U0001f948", 3: "\U0001f949"}.get(rank, f"#{rank}")
    return f"""<div class="apt-card">
<div style="display:flex;justify-content:space-between;align-items:center">
<div><span style="font-size:1.2rem;margin-right:6px">{medal}</span><span class="apt-name">{skill['name']}</span></div>
<span style="color:#FF6B6B;font-size:0.85rem">\u2764\ufe0f {skill['likes']}</span>
</div>
<div class="apt-meta" style="margin-top:4px">by {skill['author']}</div>
<div style="font-size:0.85rem;margin-top:8px;color:#d1d5db">{skill['desc']}</div>
<div style="margin-top:8px">{tags_html}</div>
</div>"""


def render_my_skill_card(skill, source_tag, summary):
    """내 스킬 카드 HTML을 반환한다."""
    return f"""<div class="apt-card">
<div><span class="apt-name">{skill['name']}</span> {source_tag}</div>
<div style="font-size:0.85rem;margin-top:4px;color:#d1d5db">{skill.get('desc', '')}</div>
<div style="font-size:0.75rem;margin-top:6px;color:#888">{summary}</div>
</div>"""


def build_skill_tags_html(cfg):
    """스킬 config에서 필터 태그 HTML을 생성한다."""
    from src.constants import SORT_LABELS
    tags = []
    if "force_tiers" in cfg:
        for t in cfg["force_tiers"]:
            tags.append(TIER_DISPLAY.get(t, t))
    if "force_gus" in cfg:
        tags.extend(cfg["force_gus"])
    if "min_hhld" in cfg:
        tags.append(f"{cfg['min_hhld']}세대+")
    if "max_recovery" in cfg:
        tags.append(f"회복률~{cfg['max_recovery']}%")
    if "min_ratio" in cfg:
        tags.append(f"전세가율{cfg['min_ratio']}%+")
    if "max_gap" in cfg:
        tags.append(f"갭~{cfg['max_gap']/10000:.0f}억")
    if "sort_by" in cfg:
        tags.append(SORT_LABELS.get(cfg["sort_by"], cfg["sort_by"]))
    return " ".join(f'<span class="tag tag-blue">{t}</span>' for t in tags)


def build_my_skill_summary(cfg):
    """내 스킬의 필터 요약 문자열을 생성한다."""
    parts = []
    if "force_tiers" in cfg:
        parts.append(", ".join(TIER_DISPLAY.get(t, t) for t in cfg["force_tiers"]))
    if "force_gus" in cfg:
        parts.append(", ".join(cfg["force_gus"]))
    if "min_hhld" in cfg:
        parts.append(f"{cfg['min_hhld']}세대+")
    if "max_recovery" in cfg:
        parts.append(f"회복률~{cfg['max_recovery']}%")
    if "min_ratio" in cfg:
        parts.append(f"전세가율{cfg['min_ratio']}%+")
    return " \u00b7 ".join(parts) if parts else "기본 필터"


# ── 내부 헬퍼 ──

def _build_tags(r, rr):
    """아파트 카드용 태그 HTML을 생성한다."""
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
        tags += '<span class="tag tag-gray">프리미엄</span>'
    return tags


def _build_policy_metric(r, latest):
    """10.15 정책 변동 metric HTML을 생성한다."""
    pa = r.get("policy_avg", 0)
    if pa > 0:
        diff_policy = latest - pa
        pct = round(diff_policy / pa * 100, 1)
        return f'<div class="metric-item"><span class="metric-label">10.15 전후</span><span class="metric-value">{pct:+.1f}%</span></div>'
    return ""


def _build_recovery_metric(rr):
    """회복률 metric HTML을 생성한다."""
    if rr > 0:
        if rr >= 100:
            return f'<div class="metric-item"><span class="metric-label">22년 고점 대비</span><span class="metric-value" style="color:#51CF66">{rr:.0f}% 돌파</span></div>'
        else:
            return f'<div class="metric-item"><span class="metric-label">22년 고점 대비</span><span class="metric-value" style="color:#FF6B6B">{rr:.0f}% ({100-rr:.0f}%\u2193)</span></div>'
    return ""
