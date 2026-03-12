"""
Streamlit UI component for the AI assistant tab.
Call render_ai_tab(analysis_data, user_context) from web_app.py.
"""

import os
from typing import Optional

import streamlit as st


def _get_user_ip() -> str:
    """Streamlit Cloud에서 사용자 IP 추출 (로컬은 127.0.0.1)"""
    try:
        headers = st.context.headers
        # Streamlit Cloud는 X-Forwarded-For 헤더 사용
        forwarded = headers.get("X-Forwarded-For", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return headers.get("X-Real-Ip", "127.0.0.1")
    except Exception:
        return "127.0.0.1"

# ---------------------------------------------------------------------------
# Lazy imports — avoid crashing if heavy deps are not yet installed
# ---------------------------------------------------------------------------

def _check_dependencies() -> list[str]:
    """Return list of missing dependency names."""
    missing = []
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        missing.append("sentence-transformers")
    try:
        import chromadb  # noqa: F401
    except ImportError:
        missing.append("chromadb")
    try:
        import anthropic  # noqa: F401
    except ImportError:
        missing.append("anthropic")
    return missing


@st.cache_resource(show_spinner="임베딩 모델 로딩중... (최초 1회, ~400MB)")
def _get_rag_engine():
    """Load the RAG engine with cached embedding model."""
    from .rag_engine import RAGEngine
    engine = RAGEngine()
    # Force model load so it's cached
    _ = engine.embedding_model
    return engine


EXAMPLE_QUESTIONS = [
    "강남 아파트 전망",
    "소액갭 추천",
    "토허제 영향",
    "동탄 아파트 투자",
    "전세가율 높은 아파트",
]

from .rate_limiter import check_limit, log_question, get_stats, DAILY_LIMIT


def render_ai_tab(
    analysis_data: Optional[list[dict]] = None,
    user_context: Optional[dict] = None,
):
    """
    Render the AI assistant tab in Streamlit.

    Args:
        analysis_data: Apartment analysis data (for re-indexing).
        user_context: Dict with user budget/preferences for context.
    """
    st.header("AI 부동산 비서")
    st.caption("실거래가 데이터와 최신 뉴스를 기반으로 답변하는 AI 비서예요.")

    # -----------------------------------------------------------------------
    # Dependency / API key check
    # -----------------------------------------------------------------------
    missing = _check_dependencies()
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if missing or not api_key:
        st.markdown("""
<div style="background:#1a1d26;border:1px solid #2d3039;border-radius:16px;padding:32px;text-align:center;margin:20px 0;">
<div style="font-size:2.5rem;margin-bottom:12px;">🤖</div>
<div style="font-size:1.1rem;font-weight:700;margin-bottom:8px;">신기능 출시 준비 중!</div>
<div style="font-size:0.9rem;color:#9CA3AF;">AI에게 부동산 관련 질문을 하면<br>실거래 데이터 + 최신 뉴스를 기반으로 답변해드려요.</div>
<div style="margin-top:16px;font-size:0.8rem;color:#FF6B6B;font-weight:600;">Coming Soon</div>
</div>
""", unsafe_allow_html=True)
        return

    # -----------------------------------------------------------------------
    # News refresh button (sidebar-style)
    # -----------------------------------------------------------------------
    col_refresh, col_status = st.columns([1, 3])
    with col_refresh:
        if st.button("뉴스 최신화", key="ai_news_refresh"):
            with st.spinner("뉴스 수집 중..."):
                try:
                    from .news_collector import collect_all_news, save_news
                    articles = collect_all_news()
                    save_news(articles)
                    st.success(f"{len(articles)}건 수집 완료")

                    # Re-index news
                    with st.spinner("뉴스 인덱싱 중..."):
                        from .news_indexer import index_news
                        engine = _get_rag_engine()
                        index_news(articles, model=engine.embedding_model, chroma_client=engine.chroma_client)
                        st.success("인덱싱 완료")
                except Exception as e:
                    st.error(f"뉴스 수집 실패: {e}")

    with col_status:
        naver_ok = bool(os.getenv("NAVER_CLIENT_ID")) and bool(os.getenv("NAVER_CLIENT_SECRET"))
        status_parts = []
        status_parts.append(f"Anthropic API: {'OK' if api_key else 'Missing'}")
        status_parts.append(f"Naver API: {'OK' if naver_ok else 'Not set (Google RSS only)'}")
        st.caption(" | ".join(status_parts))

    st.divider()

    # -----------------------------------------------------------------------
    # Example question buttons
    # -----------------------------------------------------------------------
    st.write("**예시 질문:**")
    btn_cols = st.columns(len(EXAMPLE_QUESTIONS))
    selected_example = None
    for i, q in enumerate(EXAMPLE_QUESTIONS):
        with btn_cols[i]:
            if st.button(q, key=f"example_{i}"):
                selected_example = q

    # -----------------------------------------------------------------------
    # Question input
    # -----------------------------------------------------------------------
    question = st.text_input(
        "질문을 입력하세요",
        value=selected_example or "",
        placeholder="예: 지금 강남 사도 될까?",
        key="ai_question_input",
    )

    # -----------------------------------------------------------------------
    # Rate limit (SQLite, IP별 일일 10회)
    # -----------------------------------------------------------------------
    user_ip = _get_user_ip()
    allowed, remaining = check_limit(user_ip)
    st.caption(f"남은 질문 횟수: {remaining}/{DAILY_LIMIT} (일일 제한)")

    if st.button("질문하기", key="ai_ask_btn", type="primary") and question:
        if not allowed:
            st.warning("오늘 질문 횟수를 모두 사용했습니다 (10회/일). 내일 다시 이용해주세요!")
            return

        engine = _get_rag_engine()

        with st.spinner("답변 생성 중..."):
            result = engine.ask(
                question=question,
                context_from_app=user_context,
                n_results=5,
            )
        log_question(user_ip)

        # -------------------------------------------------------------------
        # Display answer
        # -------------------------------------------------------------------
        st.subheader("답변")
        st.markdown(result["answer"])

        # -------------------------------------------------------------------
        # Display sources
        # -------------------------------------------------------------------
        sources = result.get("sources", [])
        if sources:
            with st.expander("참고 자료 (출처)", expanded=False):
                news_sources = [s for s in sources if s.get("type") == "news"]
                re_sources = [s for s in sources if s.get("type") == "real_estate"]

                if news_sources:
                    st.write("**뉴스:**")
                    for s in news_sources:
                        title = s.get("title", "제목 없음")
                        link = s.get("link", "")
                        if link:
                            st.markdown(f"- [{title}]({link})")
                        else:
                            st.markdown(f"- {title}")

                if re_sources:
                    st.write("**아파트 데이터:**")
                    for s in re_sources:
                        name = s.get("apt_name", "")
                        gu = s.get("gu", "")
                        dong = s.get("dong", "")
                        st.markdown(f"- {gu} {dong} {name}")

        # -------------------------------------------------------------------
        # Debug: raw search results (collapsed)
        # -------------------------------------------------------------------
        with st.expander("검색 결과 상세 (디버그)", expanded=False):
            search_results = result.get("search_results", {})

            re_items = search_results.get("real_estate", [])
            if re_items:
                st.write(f"**아파트 데이터** ({len(re_items)}건)")
                for item in re_items:
                    st.text(f"[거리: {item['distance']:.4f}] {item['document'][:120]}")

            news_items = search_results.get("news", [])
            if news_items:
                st.write(f"**뉴스** ({len(news_items)}건)")
                for item in news_items:
                    st.text(f"[거리: {item['distance']:.4f}] {item['document'][:120]}")
