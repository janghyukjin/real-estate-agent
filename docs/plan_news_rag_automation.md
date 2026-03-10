# 부동산 AI 비서 — 뉴스 API + RAG + 자동화 플랜

## 1. 뉴스 API 소스

### 추천 조합

| 소스 | 유형 | 한도 | 비용 | 법적 리스크 |
|------|------|------|------|------------|
| **네이버 뉴스 검색 API** (Primary) | REST API | 25,000회/일 | 무료 | 낮음 (공식 API) |
| 국토교통부 RSS | RSS | 무제한 | 무료 | 없음 |
| 뉴스와이어 부동산 RSS | RSS | 무제한 | 무료 | 없음 |
| Google News RSS | RSS | 무제한 | 무료 | 낮음 |

- 네이버 API: 제목+요약+링크 반환 (본문 미포함). 본문 필요시 og:description 메타태그 추출
- 등록: 네이버 개발자센터에서 Client ID/Secret 발급 → `.env`에 추가

## 2. RAG 파이프라인

### 선택 스택

| 항목 | 선택 | 이유 |
|------|------|------|
| 임베딩 | **KR-SBERT** (snunlp/KR-SBERT-V40K-klueNLI-augSTS) | 한국어 특화, 무료, 로컬 |
| 벡터DB | **ChromaDB** | 로컬, pip install, 뉴스 규모에 충분 |
| LLM | Ollama(개발) / Claude Haiku(운영) | 비용 효율 |

### 흐름
```
뉴스 수집 (API/RSS)
  → 전처리 (중복제거, 키워드태깅)
  → KR-SBERT 임베딩
  → ChromaDB 저장
  → 사용자 질의 → 유사도 검색 (top-k)
  → LLM 요약/답변
```

### 예상 월 비용
- 전부 로컬: **$0**
- LLM API 사용 시: **$5-15/월**

## 3. n8n 자동화

### 워크플로우 3개

**WF1: 일일 실거래 갱신 (매일 06:00)**
```
Cron → 국토부 API 호출 → collect_data.py → reanalyze.py → 알림
```

**WF2: 일일 뉴스 수집 (매일 08:00, 18:00)**
```
Cron → 네이버 API + RSS → 중복제거 → news_indexer.py → ChromaDB → 알림
```

**WF3: 주간 캐시 갱신 (일요일 04:00)**
```
Cron → build_cache.py → 알림
```

### n8n 구성
- Docker Compose: n8n + PostgreSQL
- 최소 사양: 2GB RAM, 2 vCPU
- 알림: Telegram Bot (무료)

## 4. 아키텍처

```
┌─────────────────────────────────────────────────┐
│              n8n (Docker)                        │
│  WF1: 실거래 06:00 │ WF2: 뉴스 08/18:00        │
│  WF3: 캐시 일 04:00 │ Alert: Telegram          │
└──────────┬──────────────────┬────────────────────┘
           │                  │
           v                  v
┌─────────────────┐  ┌──────────────┐  ┌──────────┐
│ Python 스크립트  │  │  ChromaDB    │  │ External │
│ collect_data.py │  │  뉴스 임베딩  │  │ APIs     │
│ reanalyze.py    │  │  + 메타데이터  │  │ 국토부   │
│ news_indexer.py │  │              │  │ 네이버   │
└────────┬────────┘  └──────┬───────┘  └──────────┘
         │                  │
         v                  v
┌───────────────────────────────────────────┐
│      Streamlit 웹앱 (web_app.py)          │
│  [기존] 매물 분석 / 대출 계산기           │
│  [신규] 뉴스 피드 탭                      │
│  [신규] AI Q&A (RAG 기반)                 │
└───────────────────────────────────────────┘
         │
    ┌────┴────┐
    v         v
  main      beta
  (prod)    (test)
```

## 5. 구현 로드맵

### Phase 1: 뉴스 수집 + 단순 표시 (1-2주)
1. 네이버 API 키 발급, `.env` 추가
2. `news_collector.py`: 네이버 API + RSS 수집 → `data/news.json`
3. web_app.py에 "부동산 뉴스" 탭 추가
4. 키워드별 필터 UI

### Phase 2: RAG 연동 (2-3주)
1. `pip install chromadb sentence-transformers`
2. `news_indexer.py`: 임베딩 + ChromaDB 저장
3. `src/news_rag.py`: 질의 → top-k 검색
4. LLM 요약 연동 (Ollama/Claude)
5. web_app.py에 AI Q&A 위젯
6. 30일 뉴스 자동 만료

### Phase 3: n8n 자동화 (1-2주)
1. Docker Compose 구성
2. Telegram Bot + 알림
3. WF1~3 구현 + 에러 핸들링

**총 4-7주**

## 6. Beta 환경 분리

### 추천: GitHub 브랜치 기반 (Streamlit Cloud)

- `main` 브랜치 → **prod** (`real-estate-agent.streamlit.app`)
- `beta` 브랜치 → **beta** (`real-estate-agent-beta.streamlit.app`)
- 같은 레포에서 Streamlit Cloud 앱 2개 생성 (브랜치만 다르게)
- Secrets 별도 관리 가능
- Beta는 테마 색상 다르게 설정하면 시각적 구분

### 워크플로우
```
feature/* → beta (테스트) → main (배포)
```
