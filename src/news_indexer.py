"""
News and real estate data indexer using KR-SBERT + ChromaDB.
Embeds articles and apartment analysis into vector collections for RAG retrieval.
"""

import json
from pathlib import Path
from typing import Optional

import chromadb
from sentence_transformers import SentenceTransformer

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHROMA_DIR = DATA_DIR / "chroma_db"
NEWS_FILE = DATA_DIR / "news.json"
ANALYSIS_FILE = DATA_DIR / "analysis.json"

MODEL_NAME = "snunlp/KR-SBERT-V40K-klueNLI-augSTS"

NEWS_COLLECTION = "news"
REAL_ESTATE_COLLECTION = "real_estate"


def _load_model() -> SentenceTransformer:
    """Load the Korean SBERT model."""
    print(f"[INFO] Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)
    print("[INFO] Model loaded.")
    return model


def _get_chroma_client(persist_dir: Optional[Path] = None) -> chromadb.ClientAPI:
    """Create a persistent ChromaDB client."""
    persist_dir = persist_dir or CHROMA_DIR
    persist_dir.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(persist_dir))


def _format_apartment_text(apt: dict) -> str:
    """
    Create a searchable text representation of an apartment analysis entry.
    Example: "강남구 역삼동 래미안 84㎡ 1,200세대 매매 15억 전세가율 52% 회복률 87% 토허제후 +3.2%"
    """
    parts = []

    gu = apt.get("gu", "")
    dong = apt.get("dong", "")
    name = apt.get("apt_name", "")
    if gu:
        parts.append(gu)
    if dong:
        parts.append(dong)
    if name:
        parts.append(name)

    area = apt.get("area_m2") or apt.get("area")
    if area:
        parts.append(f"{area}㎡")

    households = apt.get("households") or apt.get("total_households")
    if households:
        parts.append(f"{households:,}세대")

    # Price info
    price = apt.get("avg_price") or apt.get("recent_price")
    if price:
        eok = price / 10000 if price > 10000 else price
        parts.append(f"매매 {eok:.1f}억")

    jeonse_ratio = apt.get("jeonse_ratio") or apt.get("rent_ratio")
    if jeonse_ratio:
        parts.append(f"전세가율 {jeonse_ratio:.0f}%")

    recovery = apt.get("recovery_rate") or apt.get("recovery")
    if recovery:
        parts.append(f"회복률 {recovery:.0f}%")

    # Permission-zone related changes
    toho_change = apt.get("toho_change") or apt.get("post_toho_change")
    if toho_change is not None:
        sign = "+" if toho_change > 0 else ""
        parts.append(f"토허제후 {sign}{toho_change:.1f}%")

    score = apt.get("score") or apt.get("total_score")
    if score:
        parts.append(f"점수 {score:.1f}")

    return " ".join(parts)


def index_news(
    news_list: list[dict],
    model: Optional[SentenceTransformer] = None,
    chroma_client: Optional[chromadb.ClientAPI] = None,
) -> int:
    """
    Embed news articles and store in ChromaDB.

    Args:
        news_list: List of news article dicts with title, description, link, etc.
        model: Pre-loaded SentenceTransformer (loaded if None).
        chroma_client: Pre-created ChromaDB client (created if None).

    Returns:
        Number of articles indexed.
    """
    if not news_list:
        print("[INFO] No news articles to index.")
        return 0

    if model is None:
        model = _load_model()
    if chroma_client is None:
        chroma_client = _get_chroma_client()

    collection = chroma_client.get_or_create_collection(
        name=NEWS_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    # Prepare texts and metadata
    texts = []
    ids = []
    metadatas = []

    existing_ids = set()
    try:
        existing = collection.get()
        if existing and existing.get("ids"):
            existing_ids = set(existing["ids"])
    except Exception:
        pass

    for i, article in enumerate(news_list):
        title = article.get("title", "")
        desc = article.get("description", "")
        text = f"{title}. {desc}".strip()
        if not text or text == ".":
            continue

        doc_id = f"news_{hash(title) & 0xFFFFFFFF:08x}_{i}"
        if doc_id in existing_ids:
            continue

        texts.append(text)
        ids.append(doc_id)
        metadatas.append({
            "title": title[:500],
            "link": article.get("link", "")[:500],
            "pubDate": article.get("pubDate", ""),
            "source": article.get("source", ""),
            "query": article.get("query", ""),
            "type": "news",
        })

    if not texts:
        print("[INFO] All news articles already indexed.")
        return 0

    # Embed in batches
    BATCH_SIZE = 64
    total_added = 0
    for start in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[start : start + BATCH_SIZE]
        batch_ids = ids[start : start + BATCH_SIZE]
        batch_meta = metadatas[start : start + BATCH_SIZE]

        embeddings = model.encode(batch_texts, show_progress_bar=False).tolist()
        collection.add(
            documents=batch_texts,
            embeddings=embeddings,
            ids=batch_ids,
            metadatas=batch_meta,
        )
        total_added += len(batch_texts)

    print(f"[INFO] Indexed {total_added} news articles into '{NEWS_COLLECTION}' collection.")
    return total_added


def index_real_estate_data(
    analysis_data: Optional[list[dict]] = None,
    model: Optional[SentenceTransformer] = None,
    chroma_client: Optional[chromadb.ClientAPI] = None,
) -> int:
    """
    Embed apartment analysis data and store in ChromaDB.

    Args:
        analysis_data: List of apartment analysis dicts. Loaded from file if None.
        model: Pre-loaded SentenceTransformer.
        chroma_client: Pre-created ChromaDB client.

    Returns:
        Number of apartments indexed.
    """
    if analysis_data is None:
        if not ANALYSIS_FILE.exists():
            print(f"[ERROR] Analysis file not found: {ANALYSIS_FILE}")
            return 0
        analysis_data = json.loads(ANALYSIS_FILE.read_text(encoding="utf-8"))
        if isinstance(analysis_data, dict):
            analysis_data = analysis_data.get("results", analysis_data.get("data", []))

    if not analysis_data:
        print("[INFO] No real estate data to index.")
        return 0

    if model is None:
        model = _load_model()
    if chroma_client is None:
        chroma_client = _get_chroma_client()

    # Recreate collection for full reindex (real estate data is a snapshot)
    try:
        chroma_client.delete_collection(name=REAL_ESTATE_COLLECTION)
    except Exception:
        pass

    collection = chroma_client.create_collection(
        name=REAL_ESTATE_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )

    texts = []
    ids = []
    metadatas = []

    for i, apt in enumerate(analysis_data):
        text = _format_apartment_text(apt)
        if not text.strip():
            continue

        doc_id = f"apt_{i:05d}"
        texts.append(text)
        ids.append(doc_id)
        metadatas.append({
            "gu": apt.get("gu", ""),
            "dong": apt.get("dong", ""),
            "apt_name": apt.get("apt_name", ""),
            "area_m2": str(apt.get("area_m2", apt.get("area", ""))),
            "households": str(apt.get("households", apt.get("total_households", ""))),
            "type": "real_estate",
            "raw_json": json.dumps(apt, ensure_ascii=False)[:1000],
        })

    if not texts:
        print("[INFO] No valid real estate entries to index.")
        return 0

    # Embed in batches
    BATCH_SIZE = 64
    total_added = 0
    for start in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[start : start + BATCH_SIZE]
        batch_ids = ids[start : start + BATCH_SIZE]
        batch_meta = metadatas[start : start + BATCH_SIZE]

        embeddings = model.encode(batch_texts, show_progress_bar=(len(texts) > 100)).tolist()
        collection.add(
            documents=batch_texts,
            embeddings=embeddings,
            ids=batch_ids,
            metadatas=batch_meta,
        )
        total_added += len(batch_texts)

    print(f"[INFO] Indexed {total_added} apartments into '{REAL_ESTATE_COLLECTION}' collection.")
    return total_added


def build_index():
    """CLI entrypoint: index both news and real estate data."""
    model = _load_model()
    client = _get_chroma_client()

    # Index news
    if NEWS_FILE.exists():
        news_data = json.loads(NEWS_FILE.read_text(encoding="utf-8"))
        articles = news_data.get("articles", [])
        index_news(articles, model=model, chroma_client=client)
    else:
        print(f"[WARN] News file not found: {NEWS_FILE}. Run news_collector.py first.")

    # Index real estate
    index_real_estate_data(model=model, chroma_client=client)


if __name__ == "__main__":
    build_index()
