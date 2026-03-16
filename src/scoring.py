"""
집피티 스코어링 및 필터링 로직
"""
from src.constants import PRESETS, TIER_SCORES


def apply_skill_overrides(params, active_preset, active_community):
    """프리셋/커뮤니티 스킬 오버라이드를 params dict에 적용한다.

    params는 현재 필터 설정값 dict (max_recovery, min_hhld 등).
    active_preset: 선택된 프리셋 이름 (str or None)
    active_community: 세션의 커뮤니티 스킬 config (dict or None)

    Returns: 업데이트된 params (같은 dict 참조)
    """
    override_keys = [
        "max_recovery", "min_hhld", "force_gus", "force_tiers",
        "min_recovery_override", "max_policy_change",
    ]

    def _apply(source):
        for key in override_keys:
            if key in source:
                if key == "force_gus":
                    params["effective_gus"] = set(source["force_gus"])
                    params["filter_all_gus"] = False
                elif key == "force_tiers":
                    params["selected_tiers"] = list(source["force_tiers"])
                elif key == "min_recovery_override":
                    params["min_recovery"] = source["min_recovery_override"]
                else:
                    params[key] = source[key]

    # 커뮤니티 스킬 먼저 (프리셋이 있으면 덮어씀)
    if active_community and not active_preset:
        _apply(active_community)

    # 프리셋 우선
    if active_preset and active_preset in PRESETS:
        _apply(PRESETS[active_preset])

    return params


def _get_effective_cfg(active_preset, active_community):
    """프리셋/커뮤니티 스킬의 병합된 설정을 반환한다."""
    preset_cfg = PRESETS.get(active_preset, {}) if active_preset else {}
    skill_cfg = active_community if (active_community and not active_preset) else {}
    return {**skill_cfg, **preset_cfg}


def filter_and_score(all_data, params, active_preset, active_community):
    """all_data에서 필터링 + 스코어링을 수행하고 정렬된 후보 리스트를 반환한다.

    params keys:
        min_hhld, selected_tiers, filter_all_gus, effective_gus,
        filter_all_dongs, selected_dongs, min_recovery, max_recovery,
        max_policy_change, gap_invest_mode, budget, seed_money,
        loan_amount, interest_rate
    """
    min_hhld = params["min_hhld"]
    selected_tiers = params["selected_tiers"]
    filter_all_tiers = "전체" in selected_tiers
    filter_all_gus = params["filter_all_gus"]
    effective_gus = params["effective_gus"]
    filter_all_dongs = params["filter_all_dongs"]
    selected_dongs = params["selected_dongs"]
    min_recovery = params.get("min_recovery", 0)
    max_recovery = params["max_recovery"]
    max_policy_change = params["max_policy_change"]
    gap_invest_mode = params["gap_invest_mode"]
    seed_money = params["seed_money"]
    loan_amount = params["loan_amount"]
    budget = params["budget"]
    interest_rate = params["interest_rate"]

    mr = (interest_rate / 100) / 12
    n = 360

    if gap_invest_mode:
        gap_budget = seed_money + loan_amount
        gap_max = int(gap_budget * 1.10)
        gap_min = int(gap_budget * 0.90)
    else:
        budget_max = int(budget * 1.10)
        budget_min = int(budget * 0.80)

    effective_cfg = _get_effective_cfg(active_preset, active_community)

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

        # 전세가율/갭 필터 (프리셋 또는 커뮤니티 스킬)
        if effective_cfg.get("min_ratio") and r["ratio"] < effective_cfg["min_ratio"]:
            continue
        if effective_cfg.get("max_gap") and r["gap"] > effective_cfg["max_gap"]:
            continue

        if gap_invest_mode:
            apt_gap = r["gap"]
            if apt_gap > gap_max or apt_gap < gap_min:
                continue
        else:
            if r["avg_price"] > budget_max or r["avg_price"] < budget_min:
                continue

        # 스코어링
        score = _calculate_score(r, rr)

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

        # 급매 포착용: 최근가 vs 평균 낙폭
        latest_pr = r.get("latest_price", r["avg_price"])
        drop_pct = (latest_pr - r["avg_price"]) / r["avg_price"] * 100 if r["avg_price"] > 0 else 0

        candidates.append({
            **r, "score": score, "loan_needed": loan_needed,
            "monthly_pay": mp, "drop_pct": drop_pct,
        })

    # 정렬
    sort_mode = effective_cfg.get("sort_by")
    if sort_mode == "gap_asc":
        candidates.sort(key=lambda x: x["gap"])
    elif sort_mode == "drop_desc":
        candidates.sort(key=lambda x: x["drop_pct"])
    else:
        candidates.sort(key=lambda x: -x["score"])

    return candidates


def _calculate_score(r, rr):
    """단일 아파트의 종합 점수를 계산한다."""
    tier_score = TIER_SCORES.get(r["tier"], 0)

    # 전세가율: 50~70% 구간이 이상적 (저평가 신호)
    ratio_val = r["ratio"]
    if 50 <= ratio_val <= 70:
        ratio_score = 30
    elif ratio_val < 50:
        ratio_score = max(0, 30 - (50 - ratio_val) * 1.0)
    else:
        ratio_score = max(0, 30 - (ratio_val - 70) * 1.5)

    # 세대수: 300~5000+ 선형 스케일 (대단지일수록 유리)
    hhld = r.get("hhld", 0)
    hhld_score = min((hhld - 300) / 200, 20)  # 300세대=0점, 4300세대=20점

    # 거래량: 최근 3개월 거래 건수 (유동성 지표)
    volume_score = min(r["count"] * 3, 15)

    # 회복률: 낮을수록 아직 덜 오름 = 저평가 가능성
    if rr > 0:
        if rr < 50:
            recovery_score = 30          # 회복률 50% 미만 = 적극 매수 기회
        elif rr < 80:
            recovery_score = 15          # 50~80% = 기회
        elif rr < 100:
            recovery_score = 0           # 80~100% = 중립
        else:
            recovery_score = -15         # 100% 초과 = 전고점 돌파, 단기 부담
    else:
        recovery_score = 0

    # 정책 변동: 정책 시행 후 가격 변화 (토허제 등)
    pa = r.get("policy_avg", 0)
    if pa > 0:
        latest_p = r.get("latest_price", r["avg_price"])
        policy_pct_val = (latest_p - pa) / pa * 100
        policy_score = -policy_pct_val * 0.5
        policy_score = max(-15, min(15, policy_score))
    else:
        policy_score = 0

    return round(tier_score + ratio_score + hhld_score + volume_score + recovery_score + policy_score, 1)
