# search/utils/search_fulltext.py 
import re
from django.db import connection

def _boolean(q: str) -> str:
    tokens = [t for t in re.split(r"\s+", (q or "").strip()) if t]
    return " ".join(f"+{t}*" for t in tokens)

def fulltext_candidates(query: str, limit: int = 2000):
    if not query:
        return []
    if connection.vendor != "mysql":
        # FTS 미지원 DB에서는 빈 리스트(또는 icontains fallback을 호출부에서)
        return []
    boolean = _boolean(query)
    if not boolean:
        return []
    sql = """
        SELECT id
        FROM paper
        WHERE MATCH(title, abstract) AGAINST (%s IN BOOLEAN MODE)
        ORDER BY
          MATCH(title, abstract) AGAINST (%s IN BOOLEAN MODE) DESC,
          year DESC, citation DESC
        LIMIT %s
    """
    with connection.cursor() as cur:
        cur.execute(sql, [boolean, boolean, limit])
        return [row[0] for row in cur.fetchall()]
