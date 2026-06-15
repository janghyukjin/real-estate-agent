"""raw_trades + raw_rents에서 분당(판교/정자/수내/...) 누락 단지 분석 추가.

reanalyze.py의 analyze_apt를 그대로 재사용 → 본 분석(analysis.json)과 area_type/전세율/
recency/gap/is_at_peak 등 모든 필드를 동일 정의로 계산. 차이는 단 하나, require_hhld=False
(분당 일부 단지는 건축물대장 캐시에 세대수가 없어 reanalyze가 hhld<300으로 탈락시킴).
세대수 미확인(hhld<300) 단지만 신규로 추가한다.
"""
import json
from datetime import datetime
from pathlib import Path

from reanalyze import analyze_apt, get_area_type

# 분당 대상 동 (판교/정자/수내 등 주요 동)
TARGET_DONGS = {"수내동", "정자동", "삼평동", "백현동", "운중동", "대장동",
                "이매동", "야탑동", "서현동", "구미동", "분당동", "금곡동"}


if __name__ == "__main__":
    base = Path(__file__).parent / "data"
    with open(base / "raw_trades.json") as f:
        trades = json.load(f)
    with open(base / "raw_rents.json") as f:
        rents = json.load(f)
    with open(base / "analysis.json") as f:
        existing = json.load(f)
    historical_stats = {}
    hist_path = base / "historical_stats.json"
    if hist_path.exists():
        with open(hist_path) as f:
            historical_stats = json.load(f)

    now = datetime.now()

    # reanalyze와 동일하게 직거래/1층 제외
    trades = [t for t in trades if t.get("deal_type", "") != "직거래"]
    trades = [t for t in trades if t.get("floor", 0) != 1]

    # 분당 대상 동만, reanalyze와 동일 키/필터로 그룹핑 (area_type = int(area)㎡)
    apt_trades = {}
    for t in trades:
        if t.get("gu") != "성남시분당구" or t.get("dong") not in TARGET_DONGS:
            continue
        if not (59 <= t["area"] <= 112):
            continue
        at = get_area_type(t["area"])
        apt_trades.setdefault((t["gu"], t["apt"], t.get("dong", ""), at), []).append(t)

    apt_rents = {}
    for r in rents:
        if r.get("gu") != "성남시분당구":
            continue
        if not (59 <= r["area"] <= 112):
            continue
        at = get_area_type(r["area"])
        apt_rents.setdefault((r["gu"], r["apt"], at), []).append(r["deposit"])

    new_records = []
    for (gu, apt, dong, at), tlist in apt_trades.items():
        rec = analyze_apt(
            gu, apt, dong, at, tlist,
            apt_rents.get((gu, apt, at), []),
            historical_stats, now, require_hhld=False,
        )
        if rec:
            new_records.append(rec)
    print(f"분당 분석 단지(동일 로직, hhld 미요구): {len(new_records)}건")

    # 중복 제외:
    #  - hhld>=300 단지는 reanalyze가 이미 analysis.json에 넣음 → 제외 (신규는 세대수 미확인분만)
    #  - 혹시 모를 정확 키 중복도 방어적으로 제외
    existing_keys = {(a["gu"], a["apt"], a["dong"], a["area_type"]) for a in existing}
    fresh = [
        n for n in new_records
        if n["hhld"] < 300
        and (n["gu"], n["apt"], n["dong"], n["area_type"]) not in existing_keys
    ]
    print(f"중복 제외 후 신규(세대수 미확인 분당): {len(fresh)}건")

    merged = existing + fresh
    with open(base / "analysis_v10.json", "w") as f:
        json.dump(merged, f, ensure_ascii=False)
    print(f"merged: {len(merged)}건 → analysis_v10.json")

    # 본인 자금 + 분당 미리보기 (13~20억 + 룰통과)
    def loan(p):
        return 6.0 if p <= 15 else (4.0 if p <= 25 else 2.0)

    print("\n=== 신규 분당 단지 중 13~20억 + 룰통과(전세율≤40%) ===")
    for n in sorted(fresh, key=lambda x: x["diff_peak"]):
        lp = n["latest_price"] / 10000
        if not (13 <= lp <= 20):
            continue
        if n["ratio"] > 40 or n["ratio"] <= 0:
            continue
        rent = n["avg_rent"] / 10000
        add = max(0, lp - rent - loan(lp) - 5.0)
        print(f"  {n['apt']:<28} {n['area_type']:<5} ({n['dong']:<4}) "
              f"{lp:>5.1f}억  대비{n['diff_peak']:>+6.1f}%  전세율 {n['ratio']:>5.1f}%  "
              f"거래{n['count']}건  {n['build_year']}  최근{n['latest_ym']}")
