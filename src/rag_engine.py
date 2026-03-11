"""
RAG (Retrieval-Augmented Generation) engine for the real estate AI agent.
Combines ChromaDB vector search with Claude Haiku for question answering.
"""

import json
import os
from pathlib import Path
from typing import Optional

import anthropic
import chromadb
from sentence_transformers import SentenceTransformer

from .news_indexer import (
    CHROMA_DIR,
    MODEL_NAME,
    NEWS_COLLECTION,
    REAL_ESTATE_COLLECTION,
)

SYSTEM_PROMPT = (
    "당신은 부동산 AI 비서 '집피티'입니다. "
    "실거래가 데이터와 최신 뉴스를 기반으로 답변합니다. "
    "투자 조언이 아닌 데이터 기반 정보를 제공하며, 항상 출처를 밝힙니다."
)

MODEL_ID = "claude-haiku-4-5-20251001"


class RAGEngine:
    """
    Retrieval-Augmented Generation engine.

    Usage:
        engine = RAGEngine()
        answer = engine.ask("강남 아파트 전망은?")
        print(answer["answer"])
        print(answer["sources"])
    """

    def __init__(
        self,
        chroma_dir: Optional[Path] = None,
        embedding_model: Optional[SentenceTransformer] = None,
    ):
        self._chroma_dir = chroma_dir or CHROMA_DIR
        self._model: Optional[SentenceTransformer] = embedding_model
        self._chroma: Optional[chromadb.ClientAPI] = None
        self._anthropic: Optional[anthropic.Anthropic] = None

    @property
    def embedding_model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(MODEL_NAME)
        return self._model

    @property
    def chroma_client(self) -> chromadb.ClientAPI:
        if self._chroma is None:
            self._chroma = chromadb.PersistentClient(path=str(self._chroma_dir))
        return self._chroma

    @property
    def anthropic_client(self) -> anthropic.Anthropic:
        if self._anthropic is None:
            api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not api_key:
                raise ValueError(
                    "ANTHROPIC_API_KEY not set. "
                    "Add it to .env or set it as an environment variable."
                )
            self._anthropic = anthropic.Anthropic(api_key=api_key)
        return self._anthropic

    def _get_collection(self, name: str) -> Optional[chromadb.Collection]:
        """Safely get a ChromaDB collection, returning None if it doesn't exist."""
        try:
            return self.chroma_client.get_collection(name=name)
        except Exception:
            return None

    def search(
        self,
        query: str,
        n_results: int = 5,
        collection: str = "both",
    ) -> dict:
        """
        Search relevant documents from vector collections.

        Args:
            query: Search query in Korean.
            n_results: Number of results per collection.
            collection: "news", "real_estate", or "both".

        Returns:
            Dict with "news" and/or "real_estate" keys, each containing
            a list of {document, metadata, distance}.
        """
        query_embedding = self.embedding_model.encode(query).tolist()
        results = {}

        if collection in ("news", "both"):
            news_col = self._get_collection(NEWS_COLLECTION)
            if news_col is not None:
                try:
                    res = news_col.query(
                        query_embeddings=[query_embedding],
                        n_results=n_results,
                    )
                    results["news"] = self._parse_chroma_results(res)
                except Exception as e:
                    print(f"[WARN] News search failed: {e}")
                    results["news"] = []
            else:
                results["news"] = []

        if collection in ("real_estate", "both"):
            re_col = self._get_collection(REAL_ESTATE_COLLECTION)
            if re_col is not None:
                try:
                    res = re_col.query(
                        query_embeddings=[query_embedding],
                        n_results=n_results,
                    )
                    results["real_estate"] = self._parse_chroma_results(res)
                except Exception as e:
                    print(f"[WARN] Real estate search failed: {e}")
                    results["real_estate"] = []
            else:
                results["real_estate"] = []

        return results

    @staticmethod
    def _parse_chroma_results(results: dict) -> list[dict]:
        """Parse ChromaDB query results into a flat list."""
        parsed = []
        if not results or not results.get("documents"):
            return parsed

        docs = results["documents"][0] if results["documents"] else []
        metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
        dists = results["distances"][0] if results.get("distances") else [0.0] * len(docs)

        for doc, meta, dist in zip(docs, metas, dists):
            parsed.append({
                "document": doc,
                "metadata": meta,
                "distance": dist,
            })
        return parsed

    def _build_context(
        self,
        search_results: dict,
        user_context: Optional[dict] = None,
    ) -> str:
        """Build the context string for the LLM prompt."""
        sections = []

        # Real estate data context
        re_results = search_results.get("real_estate", [])
        if re_results:
            lines = ["[관련 아파트 데이터]"]
            for i, item in enumerate(re_results, 1):
                lines.append(f"{i}. {item['document']}")
                # Include raw data if available
                raw = item.get("metadata", {}).get("raw_json", "")
                if raw:
                    try:
                        apt = json.loads(raw)
                        detail_parts = []
                        for key in ["avg_price", "recent_price", "jeonse_ratio", "recovery_rate", "score"]:
                            if key in apt and apt[key] is not None:
                                detail_parts.append(f"{key}={apt[key]}")
                        if detail_parts:
                            lines.append(f"   상세: {', '.join(detail_parts)}")
                    except json.JSONDecodeError:
                        pass
            sections.append("\n".join(lines))

        # News context
        news_results = search_results.get("news", [])
        if news_results:
            lines = ["[관련 뉴스]"]
            for i, item in enumerate(news_results, 1):
                meta = item.get("metadata", {})
                title = meta.get("title", item["document"][:80])
                pub = meta.get("pubDate", "")
                lines.append(f"{i}. [{pub}] {title}")
                lines.append(f"   {item['document'][:200]}")
            sections.append("\n".join(lines))

        # User context (budget, preferences, etc.)
        if user_context:
            lines = ["[사용자 정보]"]
            for key, val in user_context.items():
                lines.append(f"- {key}: {val}")
            sections.append("\n".join(lines))

        if not sections:
            return "관련 데이터를 찾지 못했습니다."

        return "\n\n".join(sections)

    def ask(
        self,
        question: str,
        context_from_app: Optional[dict] = None,
        n_results: int = 5,
    ) -> dict:
        """
        Full RAG pipeline: embed question, search, build context, call Claude.

        Args:
            question: User's question in Korean.
            context_from_app: Optional dict with user budget/preferences.
            n_results: Number of search results per collection.

        Returns:
            Dict with "answer", "sources", and "search_results".
        """
        # 1-2. Search both collections
        search_results = self.search(question, n_results=n_results, collection="both")

        # 3. Build context
        context = self._build_context(search_results, context_from_app)

        # 4. Call Claude Haiku
        user_message = (
            f"다음 데이터를 참고하여 질문에 답변하세요.\n\n"
            f"{context}\n\n"
            f"질문: {question}"
        )

        try:
            response = self.anthropic_client.messages.create(
                model=MODEL_ID,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            )
            answer = response.content[0].text
        except Exception as e:
            answer = f"답변 생성 중 오류가 발생했습니다: {e}"

        # 5. Compile sources
        sources = []
        for item in search_results.get("news", []):
            meta = item.get("metadata", {})
            sources.append({
                "type": "news",
                "title": meta.get("title", ""),
                "link": meta.get("link", ""),
            })
        for item in search_results.get("real_estate", []):
            meta = item.get("metadata", {})
            sources.append({
                "type": "real_estate",
                "apt_name": meta.get("apt_name", ""),
                "gu": meta.get("gu", ""),
                "dong": meta.get("dong", ""),
            })

        return {
            "answer": answer,
            "sources": sources,
            "search_results": search_results,
        }
