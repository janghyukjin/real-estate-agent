#!/bin/bash
# 내집마련 AI 비서 실행 스크립트
cd "$(dirname "$0")"
export $(cat .env | grep -v '^#' | xargs)
streamlit run web_app.py --server.headless true --server.port 8502
