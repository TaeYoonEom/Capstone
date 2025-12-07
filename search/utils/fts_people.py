# search/utils/fts_people.py
import re
from typing import List, Optional, Sequence, Union
from django.db import connection

# 안전한 테이블/컬럼 화이트리스트 (SQL 인젝션 방지)
TABLE_WHITELIST = {
    "author": {"name"},
    "affiliation": {"name"},
    "keyword": {"keyword_name"},
    "country": {"name"},
}

def _vendor_supports_fts() -> bool:
    # MySQL/MariaDB에서만 사용 (SQLite/PostgreSQL일 때는 None 리턴하여 fallback 유도)
    return connection.vendor == "mysql"

def _normalize_cols(table: str, cols: Union[str, Sequence[str]]) -> List[str]:
    if isinstance(cols, str):
        cols = [cols]
    cols = list(cols)
    # 화이트리스트 검증
    allowed = TABLE_WHITELIST.get(table, set())
    for c in cols:
        if c not in allowed:
            raise ValueError(f"FTS not allowed on {table}.{c}")
    return cols

def fts_candidates(
    table: str,
    cols: Union[str, Sequence[str]],
    query: str,
    limit: int = 2000,
) -> Optional[List[int]]:
    """
    MySQL/MariaDB FULLTEXT로 후보 id 리스트를 뽑는다.
    - 지원 DB가 아니면 None 반환(뷰에서 icontains fallback)
    - 검색어가 비어있으면 [] 반환
    - cols: 단일 문자열 또는 문자열 리스트
    """
    q = (query or "").strip()
    if not q:
        return []

    if not _vendor_supports_fts():
        # SQLite/Postgres 등에서는 FTS 미지원 → None으로 fallback 유도
        return None

    cols = _normalize_cols(table, cols)

    # +token* 형태의 BOOLEAN MODE 쿼리 생성
    tokens = [t for t in re.split(r"\s+", q) if t]
    if not tokens:
        return []

    boolean = " ".join(f"+{t}*" for t in tokens)
    cols_sql = ", ".join(cols)

    # 안전한 파라미터 바인딩 사용
    sql = f"""
        SELECT id
        FROM {table}
        WHERE MATCH({cols_sql}) AGAINST (%s IN BOOLEAN MODE)
        ORDER BY
            MATCH({cols_sql}) AGAINST (%s IN BOOLEAN MODE) DESC
        LIMIT %s
    """
    with connection.cursor() as cur:
        cur.execute(sql, [boolean, boolean, int(limit)])
        return [int(row[0]) for row in cur.fetchall()]
