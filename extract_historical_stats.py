"""
analysis.json에서 변하지 않는 과거 통계를 추출 → data/historical_stats.json
이 파일을 Git에 커밋하면, 이후 reanalyze.py가 raw_trades.json 없이도
pre_crash_peak, policy_avg, price_history 등을 참조할 수 있다.
"""
import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")


def extract():
    with open(os.path.join(DATA_DIR, "analysis.json")) as f:
        analysis = json.load(f)

    stats = {}
    for a in analysis:
        key = f"{a['gu']}|{a['apt']}|{a.get('area_type', '')}"
        stats[key] = {
            "pre_crash_peak": a.get("pre_crash_peak", 0),
            "pre_crash_ym": a.get("pre_crash_ym", ""),
            "crash_trough": a.get("crash_trough", 0),
            "crash_trough_ym": a.get("crash_trough_ym", ""),
            "policy_avg": a.get("policy_avg", 0),
            "peak": a.get("peak", 0),
            "peak_ym": a.get("peak_ym", ""),
            "trough": a.get("trough", 0),
            "trough_ym": a.get("trough_ym", ""),
            "price_history": a.get("price_history", {}),
        }

    out_path = os.path.join(DATA_DIR, "historical_stats.json")
    with open(out_path, "w") as f:
        json.dump(stats, f, ensure_ascii=False, indent=None, separators=(",", ":"))

    print(f"historical_stats.json 저장: {len(stats):,}개 아파트")
    size_mb = os.path.getsize(out_path) / 1024 / 1024
    print(f"파일 크기: {size_mb:.1f}MB")


if __name__ == "__main__":
    extract()
