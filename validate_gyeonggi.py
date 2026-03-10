"""
경기 지역 추가 후 데이터 정합성 검증 스크립트
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def validate():
    print("=" * 60)
    print("경기 지역 데이터 정합성 검증")
    print("=" * 60)

    # 1. raw 데이터 로드
    with open(os.path.join(DATA_DIR, "raw_trades.json")) as f:
        trades = json.load(f)
    with open(os.path.join(DATA_DIR, "raw_rents.json")) as f:
        rents = json.load(f)

    print(f"\n[1] raw 데이터")
    print(f"  매매: {len(trades):,}건")
    print(f"  전세: {len(rents):,}건")

    # 2. 지역별 건수 확인
    from src.api_client import SEOUL_TIERS
    trade_by_gu = {}
    rent_by_gu = {}
    for t in trades:
        trade_by_gu[t["gu"]] = trade_by_gu.get(t["gu"], 0) + 1
    for r in rents:
        rent_by_gu[r["gu"]] = rent_by_gu.get(r["gu"], 0) + 1

    print(f"\n[2] 지역별 거래 건수 (SEOUL_TIERS 등록: {len(SEOUL_TIERS)}개)")
    print(f"  {'지역':<16} {'등급':<16} {'매매':>8} {'전세':>8}")
    print(f"  {'-'*16} {'-'*16} {'-'*8} {'-'*8}")

    gyeonggi_trades = 0
    gyeonggi_rents = 0
    missing_data = []

    for gu in sorted(SEOUL_TIERS.keys()):
        tier = SEOUL_TIERS[gu]
        tc = trade_by_gu.get(gu, 0)
        rc = rent_by_gu.get(gu, 0)
        if "경기" in tier:
            gyeonggi_trades += tc
            gyeonggi_rents += rc
        flag = " ⚠️ 데이터없음!" if tc == 0 else ""
        print(f"  {gu:<16} {tier:<16} {tc:>8,} {rc:>8,}{flag}")
        if tc == 0:
            missing_data.append(gu)

    print(f"\n  경기 합계: 매매 {gyeonggi_trades:,}건 / 전세 {gyeonggi_rents:,}건")

    if missing_data:
        print(f"\n  ⚠️ 데이터 없는 지역: {missing_data}")

    # 3. 경기 지역 동(洞) 분포
    print(f"\n[3] 경기 지역 동(洞) 분포 (상위 아파트)")
    gyeonggi_gus = [gu for gu in SEOUL_TIERS if "경기" in SEOUL_TIERS[gu]]
    for gu in sorted(gyeonggi_gus):
        gu_trades = [t for t in trades if t["gu"] == gu and 59 <= t["area"] <= 112]
        dongs = {}
        apts = {}
        for t in gu_trades:
            dongs[t.get("dong", "")] = dongs.get(t.get("dong", ""), 0) + 1
            apts[t["apt"]] = apts.get(t["apt"], 0) + 1
        if not dongs:
            continue
        top_dongs = sorted(dongs.items(), key=lambda x: -x[1])[:5]
        top_apts = sorted(apts.items(), key=lambda x: -x[1])[:3]
        dong_str = ", ".join(f"{d}({c})" for d, c in top_dongs)
        apt_str = ", ".join(f"{a}({c})" for a, c in top_apts)
        print(f"  {gu}: {len(gu_trades):,}건 | 동: {dong_str}")
        print(f"    → 아파트: {apt_str}")

    # 4. bjdong_codes 매칭률 확인
    print(f"\n[4] bjdong_codes 매칭률")
    with open(os.path.join(DATA_DIR, "bjdong_codes.json")) as f:
        bjdong_codes = json.load(f)
    from src.api_client import REGION_CODES

    for gu in sorted(gyeonggi_gus):
        gu_trades = [t for t in trades if t["gu"] == gu and 59 <= t["area"] <= 112]
        dongs_in_trades = set(t.get("dong", "") for t in gu_trades if t.get("dong"))
        code = REGION_CODES.get(gu)
        if not code:
            print(f"  {gu}: REGION_CODES에 없음!")
            continue
        bjdong = bjdong_codes.get(code, {})
        matched = dongs_in_trades & set(bjdong.keys())
        unmatched = dongs_in_trades - set(bjdong.keys())
        total = len(dongs_in_trades)
        pct = len(matched) / total * 100 if total > 0 else 0
        print(f"  {gu}: {len(matched)}/{total} ({pct:.0f}%)", end="")
        if unmatched:
            print(f"  ⚠️ 미매칭: {unmatched}")
        else:
            print()

    # 5. apt_cache 매칭률 (세대수)
    print(f"\n[5] 세대수 캐시 매칭률")
    from src.building_ledger import get_household_count

    for gu in sorted(gyeonggi_gus):
        gu_trades = [t for t in trades if t["gu"] == gu and 59 <= t["area"] <= 112]
        # 유니크 아파트
        apt_set = set()
        for t in gu_trades:
            apt_set.add((t["apt"], t.get("dong", "")))

        matched = 0
        matched_300 = 0
        unmatched_apts = []
        for apt, dong in apt_set:
            hhld = get_household_count(apt, dong)
            if hhld:
                matched += 1
                if hhld >= 300:
                    matched_300 += 1
            else:
                unmatched_apts.append(apt)

        total = len(apt_set)
        pct = matched / total * 100 if total > 0 else 0
        print(f"  {gu}: {matched}/{total} ({pct:.0f}%) | 300세대+: {matched_300}", end="")
        if unmatched_apts and len(unmatched_apts) <= 10:
            print(f"  미매칭: {unmatched_apts[:5]}")
        elif unmatched_apts:
            print(f"  미매칭: {len(unmatched_apts)}개")
        else:
            print()

    # 6. analysis.json 확인 (reanalyze 후)
    analysis_path = os.path.join(DATA_DIR, "analysis.json")
    if os.path.exists(analysis_path):
        with open(analysis_path) as f:
            analysis = json.load(f)
        print(f"\n[6] analysis.json")
        print(f"  총 아파트: {len(analysis)}개")
        for gu in sorted(gyeonggi_gus):
            cnt = len([a for a in analysis if a["gu"] == gu])
            if cnt > 0:
                print(f"  {gu}: {cnt}개")


if __name__ == "__main__":
    validate()
