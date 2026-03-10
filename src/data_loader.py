"""
데이터 로드 함수 — @st.cache_data 함수를 별도 파일로 분리
Python 3.14 tokenizer가 web_app.py의 CSS를 파싱하다 에러나는 문제 방지
"""
import json
import os
import streamlit as st

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


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


@st.cache_data
def load_trade_index():
    raw_path = os.path.join(DATA_DIR, "raw_trades.json")
    if not os.path.exists(raw_path):
        return {}
    idx = {}
    # Only keep fields needed for display: year, month, price, floor, deal_type
    # The index key already captures gu, apt, dong, area — no need to store them per record
    _KEEP = ("year", "month", "price", "floor", "deal_type")
    with open(raw_path) as f:
        raw_trades = json.load(f)
    for t in raw_trades:
        area_type = f"{int(t['area'])}㎡"
        key = (t["gu"], t["apt"], t.get("dong", ""), area_type)
        idx.setdefault(key, []).append({k: t[k] for k in _KEEP if k in t})
    del raw_trades
    for key in idx:
        idx[key].sort(key=lambda x: (x["year"], x["month"]), reverse=True)
    return idx


def load_community_skills():
    path = os.path.join(DATA_DIR, "community_skills.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return []
