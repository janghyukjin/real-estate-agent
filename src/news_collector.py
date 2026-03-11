"""
News collector for the real estate AI agent.
Collects news from Naver Search API and Google News RSS.
"""

import os
import json
import hashlib
import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
NEWS_FILE = DATA_DIR / "news.json"

DEFAULT_QUERIES = ["부동산 시세", "아파트 매매", "부동산 정책", "전세 시장"]


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&quot;", '"').replace("&amp;", "&")
    text = text.replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&apos;", "'")
    return text.strip()


def _article_hash(title: str) -> str:
    """Create a hash for deduplication based on normalized title."""
    normalized = re.sub(r"\s+", "", title.lower())
    return hashlib.md5(normalized.encode()).hexdigest()


def collect_naver_news(query: str, display: int = 10) -> list[dict]:
    """
    Collect news from Naver News Search API.

    Args:
        query: Search keyword
        display: Number of results (max 100)

    Returns:
        List of {title, description, link, pubDate, source}
    """
    client_id = os.getenv("NAVER_CLIENT_ID", "")
    client_secret = os.getenv("NAVER_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("[WARN] NAVER_CLIENT_ID / NAVER_CLIENT_SECRET not set. Skipping Naver news.")
        return []

    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }
    params = {
        "query": query,
        "display": min(display, 100),
        "sort": "date",
    }

    try:
        resp = httpx.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"[ERROR] Naver news API failed for '{query}': {e}")
        return []

    results = []
    for item in data.get("items", []):
        results.append({
            "title": _strip_html(item.get("title", "")),
            "description": _strip_html(item.get("description", "")),
            "link": item.get("originallink") or item.get("link", ""),
            "pubDate": item.get("pubDate", ""),
            "source": "naver",
            "query": query,
        })
    return results


def collect_google_news_rss(query: str) -> list[dict]:
    """
    Collect news from Google News RSS feed (no API key needed).

    Args:
        query: Search keyword

    Returns:
        List of {title, description, link, pubDate, source}
    """
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=ko&gl=KR&ceid=KR:ko"

    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True)
        resp.raise_for_status()
        xml_text = resp.text
    except Exception as e:
        print(f"[ERROR] Google News RSS failed for '{query}': {e}")
        return []

    # Simple XML parsing without external dependency
    import xml.etree.ElementTree as ET

    results = []
    try:
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        if channel is None:
            return []

        for item in channel.findall("item"):
            title_el = item.find("title")
            desc_el = item.find("description")
            link_el = item.find("link")
            pub_el = item.find("pubDate")

            results.append({
                "title": _strip_html(title_el.text or "") if title_el is not None else "",
                "description": _strip_html(desc_el.text or "") if desc_el is not None else "",
                "link": (link_el.text or "") if link_el is not None else "",
                "pubDate": (pub_el.text or "") if pub_el is not None else "",
                "source": "google",
                "query": query,
            })
    except ET.ParseError as e:
        print(f"[ERROR] Google News RSS parse error: {e}")

    return results


def _title_similarity(a: str, b: str) -> float:
    """Simple Jaccard similarity on character bigrams."""
    if not a or not b:
        return 0.0
    a_norm = re.sub(r"\s+", "", a)
    b_norm = re.sub(r"\s+", "", b)
    if len(a_norm) < 2 or len(b_norm) < 2:
        return 0.0
    a_bigrams = set(a_norm[i : i + 2] for i in range(len(a_norm) - 1))
    b_bigrams = set(b_norm[i : i + 2] for i in range(len(b_norm) - 1))
    intersection = a_bigrams & b_bigrams
    union = a_bigrams | b_bigrams
    return len(intersection) / len(union) if union else 0.0


def collect_all_news(
    queries: Optional[list[str]] = None,
    naver_display: int = 10,
) -> list[dict]:
    """
    Collect news from all sources and deduplicate.

    Args:
        queries: List of search queries. Uses DEFAULT_QUERIES if None.
        naver_display: Number of Naver results per query.

    Returns:
        Deduplicated list of news articles.
    """
    if queries is None:
        queries = DEFAULT_QUERIES

    all_articles: list[dict] = []

    for q in queries:
        all_articles.extend(collect_naver_news(q, display=naver_display))
        all_articles.extend(collect_google_news_rss(q))

    # Deduplicate: exact hash first, then fuzzy title similarity
    seen_hashes: set[str] = set()
    unique: list[dict] = []

    for article in all_articles:
        h = _article_hash(article["title"])
        if h in seen_hashes:
            continue

        # Check fuzzy similarity against already-accepted articles
        is_dup = False
        for accepted in unique:
            if _title_similarity(article["title"], accepted["title"]) > 0.7:
                is_dup = True
                break

        if not is_dup:
            seen_hashes.add(h)
            unique.append(article)

    return unique


def save_news(articles: list[dict], filepath: Optional[Path] = None) -> Path:
    """
    Save news articles to JSON, merging with existing data.
    Idempotent: skips duplicates already in the file.

    Returns:
        Path to the saved file.
    """
    filepath = filepath or NEWS_FILE
    filepath.parent.mkdir(parents=True, exist_ok=True)

    # Load existing news
    existing: list[dict] = []
    if filepath.exists():
        try:
            existing = json.loads(filepath.read_text(encoding="utf-8")).get("articles", [])
        except (json.JSONDecodeError, AttributeError):
            existing = []

    existing_hashes = {_article_hash(a["title"]) for a in existing}

    new_count = 0
    for article in articles:
        h = _article_hash(article["title"])
        if h not in existing_hashes:
            existing.append(article)
            existing_hashes.add(h)
            new_count += 1

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total_count": len(existing),
        "articles": existing,
    }
    filepath.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INFO] Saved {new_count} new articles (total: {len(existing)}) to {filepath}")
    return filepath


def run():
    """CLI entrypoint: collect all news and save."""
    articles = collect_all_news()
    save_news(articles)


if __name__ == "__main__":
    run()
