# main/services/news_clients.py
import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from datetime import timedelta
from urllib.parse import urlparse
import re, html

# -----------------------------
# GNews (무료키 필요) - settings에서 직접 읽기
# -----------------------------
def gnews_search(q, n=3):
    key = settings.GNEWS_KEY
    if not key:
        return []
    try:
        r = requests.get(
            "https://gnews.io/api/v4/search",
            params={"q": q, "lang": "en", "max": n, "apikey": key},
            timeout=6,
        )
        r.raise_for_status()
        data = r.json().get("articles", [])
        return [{
            "title": a.get("title"),
            "link": a.get("url"),
            "pubDate": a.get("publishedAt"),
            "source": (a.get("source") or {}).get("name"),
        } for a in data]
    except requests.HTTPError as e:
        print("[GNEWS_ERR]", e.__class__.__name__, getattr(e.response, "status_code", None))
        return []
    except Exception as e:
        print("[GNEWS_ERR]", e.__class__.__name__, str(e)[:200])
        return []

# -----------------------------
# The Guardian (무료키 필요) - settings에서 직접 읽기
# -----------------------------
def guardian_search(q, n=3, section=None, from_days=180):
    key = settings.GUARDIAN_KEY
    if not key:
        return []
    try:
        params = {
            "q": q,
            "page-size": n,
            "order-by": "newest",
            "api-key": key,
            "from-date": (timezone.now() - timedelta(days=from_days)).date().isoformat(),
            "query-fields": "headline",  # 제목 중심
        }
        if section:
            params["section"] = section  # "technology", "science" 등
        r = requests.get("https://content.guardianapis.com/search", params=params, timeout=6)
        r.raise_for_status()
        data = r.json().get("response", {}).get("results", [])
        return [{
            "title": a.get("webTitle"),
            "link": a.get("webUrl"),
            "pubDate": a.get("webPublicationDate"),
            "source": "The Guardian",
        } for a in data]
    except requests.HTTPError as e:
        print("[GUARDIAN_ERR]", e.__class__.__name__, getattr(e.response, "status_code", None))
        return []
    except Exception as e:
        print("[GUARDIAN_ERR]", e.__class__.__name__, str(e)[:200])
        return []

# -----------------------------
# GDELT (키 불필요) + 429 쿨다운 5분
# -----------------------------
def gdelt_search(q, n=3):
    block_until = cache.get("gdelt_block_until_ts")
    if block_until and timezone.now().timestamp() < block_until:
        return []
    try:
        r = requests.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={"query": q, "mode": "ArtList", "maxrecords": n, "format": "JSON"},
            timeout=8,
        )
        r.raise_for_status()
        data = r.json().get("articles", [])
        return [{
            "title": a.get("title"),
            "link": a.get("url"),
            "pubDate": a.get("seendate"),
            "source": a.get("sourceCommonName"),
        } for a in data]
    except requests.HTTPError as e:
        status = getattr(e.response, "status_code", None)
        print("[GDELT_ERR]", e.__class__.__name__, status)
        if status == 429:
            cache.set("gdelt_block_until_ts", timezone.now().timestamp() + 300, 300)
        return []
    except Exception as e:
        print("[GDELT_ERR]", e.__class__.__name__, str(e)[:200])
        return []

def _strip_tags(s: str) -> str:
    # <b>태그 등 제거 + HTML 엔티티 해제
    if not s: return s
    return html.unescape(re.sub(r"<\/?b>", "", s))

def _host_from(url: str) -> str:
    try:
        return urlparse(url).netloc or "Naver News"
    except Exception:
        return "Naver News"

def naver_search(q, n=3, sort="date"):
    """네이버 뉴스 검색 API (JSON)"""
    cid = settings.NAVER_CLIENT_ID
    csec = settings.NAVER_CLIENT_SECRET
    if not (cid and csec):
        return []
    try:
        r = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            params={
                "query": q,                 # UTF-8
                "display": min(max(n,1), 100),
                "start": 1,
                "sort": sort,               # sim | date
            },
            headers={
                "X-Naver-Client-Id": cid,
                "X-Naver-Client-Secret": csec,
            },
            timeout=6,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        out = []
        for it in items:
            title = _strip_tags(it.get("title") or "")
            # originallink(언론사 원문) 있으면 그걸 우선 사용
            link = it.get("originallink") or it.get("link")
            out.append({
                "title": title,
                "link": link,
                "pubDate": it.get("pubDate"),
                "source": _host_from(link),
            })
        return out
    except requests.HTTPError as e:
        print("[NAVER_ERR]", e.__class__.__name__, getattr(e.response, "status_code", None))
        return []
    except Exception as e:
        print("[NAVER_ERR]", e.__class__.__name__, str(e)[:200])
        return []