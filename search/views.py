from django.shortcuts import render
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.db import connection
from django.db.models import Q, Count, Avg, Sum
from django.core.paginator import Paginator
from django.apps import apps

import json
import re
import numpy as np
import torch
from collections import defaultdict
from urllib.parse import unquote
from sklearn.feature_extraction.text import TfidfVectorizer
from datetime import datetime

from main.models import (
    Paper, PaperEmbedding, Paper_author, Paper_part, Paper_keyword, Paper_affiliation, Paper_country,
    Author, Affiliation, Country, Keyword
)
from django.urls import reverse
from collections import defaultdict
from .utils.search_fulltext import fulltext_candidates    # 논문 FTS
from .utils.fts_people import fts_candidates   
# 검색어 처리 띄어쓰기
def generate_and_query(search_fields, query):
    search_words = query.split()
    query_filter = Q()
    
    for word in search_words:
        word_filter = Q()
        for field in search_fields:
            word_filter |= Q(**{f"{field}__icontains": word}) 
        query_filter &= word_filter
        
    return query_filter


import numpy as np
import torch
from datetime import datetime
from django.db.models import Q
from django.apps import apps

def _cosine_topk(query_vec16, mat16, ids, already_normed=False):
    """
    query_vec16: (D,) float16/32
    mat16: (N, D) float16/32
    ids: 길이 N의 paper_id 리스트
    """
    q = query_vec16.astype(np.float32, copy=False)
    M = mat16.astype(np.float32, copy=False)

    if not already_normed:
        q_norm = np.linalg.norm(q) + 1e-8
        q = q / q_norm
        M_norm = np.linalg.norm(M, axis=1, keepdims=True) + 1e-8
        M = M / M_norm

    sims = M @ q  # (N,)
    k = min(TOP_K, len(sims))
    if k <= 0:
        return []

    # argpartition으로 Top-K 인덱스 추출 후, 그 내부를 내림차순 정렬
    idx = np.argpartition(-sims, k - 1)[:k]
    order = np.argsort(-sims[idx])
    idx_sorted = idx[order]

    return [(ids[i], float(sims[i])) for i in idx_sorted]


TOP_N_CAND = 2000
TOP_K = 100

def search_papers_with_embedding(query, request, user_id):
    cfg = apps.get_app_config('main')
    tokenizer, model = cfg.tokenizer, cfg.model
    model.eval()

    # 1) 쿼리 임베딩
    q_inputs = tokenizer(query, return_tensors='pt', padding=True, truncation=True, max_length=256)
    with torch.no_grad():
        q_vec = (model(**q_inputs).last_hidden_state[:, 0, :].squeeze(0).cpu().to(torch.float32).numpy())
        q_vec = q_vec / (np.linalg.norm(q_vec) + 1e-8)  # 안전 정규화

    # 2) FULLTEXT 후보
    cand_ids = fulltext_candidates(query, limit=TOP_N_CAND)
    if not cand_ids:
        return {"results": [], "results_count": 0, "available_filters": {}}

    # 3) 임베딩 로드: norm_vector 우선 사용
    from main.models import PaperEmbedding
    has_norm = any(f.name == 'norm_vector' for f in PaperEmbedding._meta.fields)
    emb_qs = PaperEmbedding.objects.filter(paper_id__in=cand_ids)\
            .values_list('paper_id', 'norm_vector' if has_norm else 'vector')

    id2idx = {pid: i for i, pid in enumerate(cand_ids)}
    mat = [None] * len(cand_ids)
    for pid, vec in emb_qs:
        i = id2idx.get(pid)
        if i is not None and vec:
            mat[i] = np.array(vec, dtype=np.float16)

    pairs = [(cid, v) for cid, v in zip(cand_ids, mat) if v is not None]
    if not pairs:
        return {"results": [], "results_count": 0, "available_filters": {}}

    cand_ids, mat = zip(*pairs)
    M = np.stack(mat, axis=0).astype(np.float32, copy=False)
    if not has_norm:
        M /= (np.linalg.norm(M, axis=1, keepdims=True) + 1e-8)  # 백업용

    # 4) 코사인 Top-K
    sims = M @ q_vec  # 내적 = 코사인
    k = min(TOP_K, len(sims))
    top_idx = np.argpartition(-sims, k-1)[:k]
    order = np.argsort(-sims[top_idx])
    top_ids = [int(cand_ids[i]) for i in top_idx[order]]

    # 5) 메타 로드 + 직렬화 (prefetch)
    qs = Paper.objects.filter(id__in=top_ids)\
        .prefetch_related('part_papers__part_id','keyword_papers__keyword_id','author_papers__author_id')\
        .only('id','title','year','citation','published_in','abstract')
    pmap = {p.id: p for p in qs}
    ordered = [pmap[i] for i in top_ids if i in pmap]

    data = []
    for p in ordered:
        part_obj = p.part_papers.all().first()
        part_name = part_obj.part_id.name if part_obj else None
        kws = [{"id": pk.keyword_id.id, "name": pk.keyword_id.keyword_name} for pk in p.keyword_papers.all()[:5]]
        authors = [{"id": a.author_id.id, "name": a.author_id.name} for a in p.author_papers.all()]
        data.append({
            "id": p.id, "title": p.title, "year": p.year, "citation": p.citation,
            "published_in": p.published_in, "part": part_name, "abstract": p.abstract,
            "keyword_pairs": kws, "author_pairs": authors, "author_names": [a["name"] for a in authors],
        })

    # 6) 좋아요/필터
    paper_ids = [d["id"] for d in data]
    liked_items, total_likes = get_like_data(user_id, "like_paper", "paper_id", paper_ids)
    for d in data:
        pid = d["id"]; d["liked"] = liked_items.get(pid, False); d["like_count"] = total_likes.get(pid, 0)

    selected = {
        'years': get_filter_list(request,'years'),
        'parts': get_filter_list(request,'parts'),
        'authors': get_filter_list(request,'authors'),
        'publishers': get_filter_list(request,'publishers'),
    }
    filtered = data
    if selected['years']:
        ys = set(selected['years']); filtered = [i for i in filtered if i['year'] and str(i['year']) in ys]
    if selected['parts']:
        ps = set(selected['parts']); filtered = [i for i in filtered if i['part'] and i['part'] in ps]
    if selected['authors']:
        as_ = set(selected['authors']); filtered = [i for i in filtered if any(a in as_ for a in i['author_names'])]
    if selected['publishers']:
        pub = set(selected['publishers']); filtered = [i for i in filtered if i['published_in'] and i['published_in'] in pub]

    available = extract_filters_from_results(filtered, {
        "years":"year","parts":"part","authors":"author_names","publishers":"published_in"
    })

    return {"results": filtered, "results_count": len(filtered), "available_filters": available}


# 정렬
def apply_sorting(queryset, request, sorting_options, default_sort='title'):
    sort_by = request.GET.get('sort_by', default_sort)  
    sort_order = request.GET.get('sort_order', 'desc') 

    if sort_by not in sorting_options:
        sort_by = default_sort  

    sort_field = sorting_options[sort_by]
     # 내림차순 정렬 처리
    return queryset.order_by(f"-{sort_field}" if sort_order == 'desc' else sort_field)

#  필터 리스트 추출
def get_filter_list(request, key):
    return request.GET.getlist(f"{key}[]") or request.GET.getlist(key)

# 필터 적용 가능한 목록(중복 제거, 정렬) 추출
def extract_filters_from_results(results, filter_fields):
    available_filters = {key: set() for key in filter_fields.keys()}

    def _to_filter_value(x):
        # dict이면 사람이 읽는 name 필드를 사용
        if isinstance(x, dict):
            for k in ("name", "keyword_name", "title"):
                if k in x and x[k]:
                    return str(x[k])
            # name 못 찾으면 dict 전체를 문자열화
            return json.dumps(x, ensure_ascii=False)
        return x  # 문자열이나 숫자는 그대로 반환

    for item in results:
        for key, value in filter_fields.items():
            field_value = item.get(value) if isinstance(item, dict) else getattr(item, value, None)

            if isinstance(field_value, list):
                for v in field_value:
                    norm = _to_filter_value(v)
                    if norm:
                        available_filters[key].add(norm)
            elif field_value:
                norm = _to_filter_value(field_value)
                if norm:
                    available_filters[key].add(norm)

    return {k: sorted(v) for k, v in available_filters.items() if v}

def _in_clause_params(seq):
    placeholders = ",".join(["%s"] * len(seq))
    return f"({placeholders})", list(seq)

def get_like_data(user_id, table_name, column_name, item_ids):
    if not item_ids:
        return {}, {}
    clause, params = _in_clause_params(item_ids)
    liked_items, total_likes = {}, {}
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT {column_name}, COUNT(*) FROM {table_name} WHERE {column_name} IN {clause} GROUP BY {column_name}",
            params
        )
        total_likes = {row[0]: row[1] for row in cursor.fetchall()}
    if user_id:
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {column_name} FROM {table_name} WHERE user_id=%s AND {column_name} IN {clause}",
                [user_id] + params
            )
            liked_items = {row[0]: True for row in cursor.fetchall()}
    return liked_items, total_likes


# 페이지네이션 처리 함수
def get_custom_page_range(current_page, total_pages, max_page_links=10):
    start = max(1, current_page - max_page_links // 2)
    end = min(total_pages, start + max_page_links - 1)
    return range(start, end + 1)

def boundary_regex(q):
    # 영문/숫자 경계를 기준으로 'ai' 같은 짧은 토큰도 엄격 매칭
    safe = re.escape(q.lower())
    return rf'(^|[^A-Za-z0-9]){safe}([^A-Za-z0-9]|$)'

def search_papers_accuracy(query, request, user_id):
    q = (query or '').strip().lower()
    if not q:
        return {"results": [], "results_count": 0, "available_filters": {}}

    rx = boundary_regex(q)

    title_hits = Paper.objects.filter(title__iregex=rx).values_list('id', flat=True)
    abs_hits   = Paper.objects.filter(abstract__iregex=rx).values_list('id', flat=True)
    kw_hits    = (Paper_keyword.objects
                  .filter(keyword_id__keyword_name__iregex=rx)
                  .values_list('paper_id', flat=True))

    from collections import Counter
    c = Counter()
    for pid in title_hits: c[pid] += 3
    for pid in kw_hits:    c[pid] += 2
    for pid in abs_hits:   c[pid] += 1

    if not c:
        return {"results": [], "results_count": 0, "available_filters": {}}

    paper_ids = list(c.keys())
    qs = (Paper.objects.filter(id__in=paper_ids)
          .prefetch_related('part_papers__part_id', 'keyword_papers__keyword_id', 'author_papers__author_id')
          .only('id','title','year','citation','published_in','abstract'))

    paper_map = {p.id: p for p in qs}
    ordered = sorted(
        paper_ids,
        key=lambda pid: (c[pid], paper_map[pid].citation or 0, paper_map[pid].year or 0),
        reverse=True
    )

    # 1) 데이터 수집
    data = []
    for pid in ordered:
        p = paper_map.get(pid)
        if not p:
            continue
        part_obj = p.part_papers.all().first()
        part_name = part_obj.part_id.name if part_obj else None
        kws = [{"id": pk.keyword_id.id, "name": pk.keyword_id.keyword_name}
               for pk in p.keyword_papers.all()[:5]]
        authors = [{"id": a.author_id.id, "name": a.author_id.name}
                   for a in p.author_papers.all()]
        data.append({
            "id": p.id,
            "title": p.title,
            "year": p.year,
            "citation": p.citation,
            "published_in": p.published_in,
            "part": part_name,
            "abstract": p.abstract,
            "keyword_pairs": kws,
            "author_pairs": authors,
            "author_names": [a["name"] for a in authors],
            "_score": c[pid],
        })

    # 2) 좋아요 집계 (반복문 밖에서 한 번에)
    paper_ids = [item["id"] for item in data]
    liked_items, total_likes = get_like_data(
        user_id=user_id,
        table_name="like_paper",
        column_name="paper_id",
        item_ids=paper_ids
    )

    # 3) 좋아요 주입
    for item in data:
        pid = item["id"]
        item["liked"] = liked_items.get(pid, False)
        item["like_count"] = total_likes.get(pid, 0)

    selected_filters = {
        'years': get_filter_list(request, 'years'),
        'parts': get_filter_list(request, 'parts'),
        'authors': get_filter_list(request, 'authors'),
        'publishers': get_filter_list(request, 'publishers'),
    }

    filtered_data = data
    if selected_filters['years']:
        filtered_data = [i for i in filtered_data
                         if i.get('year') and str(i['year']) in selected_filters['years']]

    if selected_filters['parts']:
        filtered_data = [i for i in filtered_data
                         if i.get('part') and i['part'] in selected_filters['parts']]

    if selected_filters['authors']:
        filtered_data = [i for i in filtered_data
                         if any(a in selected_filters['authors'] for a in i.get('author_names', []))]

    if selected_filters['publishers']:
        filtered_data = [i for i in filtered_data
                         if i.get('published_in') and i['published_in'] in selected_filters['publishers']]

    data = filtered_data

    # ⬇⬇⬇ 추가: 필터 목록도 현재 결과 기준으로 다시 계산
    available_filters = extract_filters_from_results(data, {
        "years": "year",
        "parts": "part",
        "authors": "author_names",
        "publishers": "published_in",
    })


    return {
        "results": data,
        "results_count": len(data),
        "available_filters": available_filters,
    }

def search_authors(query, request, user_id):
    search_fields = ['name']
    query_filter = generate_and_query(search_fields, query)

    authors = Author.objects.filter(query_filter).annotate(
        total_citations=Sum('author_authors__paper_id__citation'),
        paper_count=Count('author_authors__paper_id', distinct=True)
    )
    sorting_options = {
        'papers': 'paper_count',
        'citations': 'total_citations',
        'title': 'name',
    }
    authors = apply_sorting(authors, request, sorting_options)

    data = []
    for author in authors:
        paper_ids = Paper_author.objects.filter(author_id=author.id).values_list("paper_id", flat=True)

        main_part_obj = (
            Paper_part.objects
            .filter(paper_id__in=paper_ids)
            .values('part_id__name')
            .annotate(count=Count('part_id'))
            .order_by('-count')
            .first()
        )
        main_part = main_part_obj['part_id__name'] if main_part_obj else "정보 없음"

        keyword_counts = (
            Paper_keyword.objects.filter(paper_id__in=paper_ids)
            .values('keyword_id', 'keyword_id__keyword_name')
            .annotate(count=Count('keyword_id'))
            .order_by('-count')[:5]
        )
        top_keywords = [
            {"id": k['keyword_id'], "name": k['keyword_id__keyword_name']}
            for k in keyword_counts
        ]
        aff_obj = Affiliation.objects.filter(name__iexact=author.affiliation).first()
        affiliation_id = aff_obj.id if aff_obj else None
        country_name = aff_obj.country_id.name if (aff_obj and aff_obj.country_id) else "정보 없음"
        country_id = aff_obj.country_id.id if (aff_obj and aff_obj.country_id) else None


        data.append({
            "id": author.id,
            "name": author.name,
            "affiliation": author.affiliation,
            "total_citations": author.total_citations,
            "paper_count": author.paper_count,
            "main_part": main_part,
            "top_keywords": top_keywords,
            "country": country_name,
            "affiliation_id": affiliation_id,
            "country_id": country_id, 
        })

    # 좋아요 정보
    author_ids = [a["id"] for a in data]
    liked_items, total_likes = get_like_data(user_id, "like_author", "author_id", author_ids)
    for a in data:
        a["liked"] = liked_items.get(a["id"], False)
        a["like_count"] = total_likes.get(a["id"], 0)
    
    selected_filters = {
        'parts': get_filter_list(request, 'parts'),
        'countries': get_filter_list(request, 'countries'),
        'authors': get_filter_list(request, 'authors'),
        'affiliations': get_filter_list(request, 'affiliations'),
    }
    filtered_data = data

    if selected_filters['parts']:
        filtered_data = [
            d for d in filtered_data
            if d.get('main_part') and d['main_part'] in selected_filters['parts']
        ]
    if selected_filters['countries']:
        filtered_data = [
            d for d in filtered_data
            if d.get('country') and d['country'] in selected_filters['countries']
        ]
    if selected_filters['authors']:
        filtered_data = [
            d for d in filtered_data
            if d.get('name') and d['name'] in selected_filters['authors']
        ]
    if selected_filters['affiliations']:
        filtered_data = [
            d for d in filtered_data
            if d.get('affiliation') and d['affiliation'] in selected_filters['affiliations']
        ]

    data = filtered_data

    filter_fields = {
        "parts": "main_part",
        "countries": "country",
        "authors": "name",
        "affiliations": "affiliation",
    }
    available_filters = extract_filters_from_results(data, filter_fields)

    return {
        "results": data,
        "results_count": len(data),
        "available_filters": available_filters
    }

from django.db.models import Q, Count, Avg, Sum, Subquery, OuterRef, CharField

def search_affiliations_base_qs(query, request):
    # 0) 후보 추출 (FTS 또는 icontains)
    cand_ids = fts_candidates("affiliation", "name", query, limit=2000)
    if cand_ids is None:
        query_filter = generate_and_query(['name'], query)
        base_qs = Affiliation.objects.filter(query_filter)
    else:
        if not cand_ids:
            return Affiliation.objects.none()
        base_qs = Affiliation.objects.filter(id__in=cand_ids)

    # 1) 기본 집계
    qs = base_qs.annotate(
        paper_count=Count('affiliation_keywords__paper_id', distinct=True),
        avg_citations=Avg('affiliation_keywords__paper_id__citation'),
    )

    # 2) main_part 서브쿼리
    aff_papers = Paper_affiliation.objects.filter(
        affiliation_id=OuterRef('pk')
    ).values('paper_id')

    main_part_sq = (
        Paper_part.objects
        .filter(paper_id__in=Subquery(aff_papers))
        .values('part_id__name')
        .annotate(c=Count('part_id'))
        .order_by('-c')
        .values('part_id__name')[:1]
    )

    # 🔑 타입 명시!
    qs = qs.annotate(main_part=Subquery(main_part_sq, output_field=CharField()))

    # 3) ✅ 좌측 체크박스 값들을 실제 쿼리에 반영
    sel_parts        = set(get_filter_list(request, "parts") or [])
    sel_countries    = set(get_filter_list(request, "countries") or [])
    sel_authors      = set(get_filter_list(request, "authors") or [])
    sel_affiliations = set(get_filter_list(request, "affiliations") or [])

    if sel_parts:
        part_papers_sq = Paper_part.objects.filter(
            part_id__name__in=sel_parts
        ).values('paper_id')
        aff_ids_sq = Paper_affiliation.objects.filter(
            paper_id__in=Subquery(part_papers_sq)
        ).values('affiliation_id')
        qs = qs.filter(id__in=Subquery(aff_ids_sq))

    if sel_countries:
        # 체크박스 값은 "국가명"이므로 name 기준으로 매칭
        qs = qs.filter(country_id__name__in=sel_countries)

    if sel_affiliations:
        qs = qs.filter(name__in=sel_affiliations)

    if sel_authors:
        # 저자명으로 affiliations 필터링
        author_papers_sq = Paper_author.objects.filter(
            author_id__name__in=sel_authors
        ).values('paper_id')
        aff_ids_sq = Paper_affiliation.objects.filter(
            paper_id__in=Subquery(author_papers_sq)
        ).values('affiliation_id')
        qs = qs.filter(id__in=Subquery(aff_ids_sq))

    # 4) 정렬은 DB에서
    sorting_options = {'papers': 'paper_count', 'citations': 'avg_citations', 'title': 'name'}
    qs = apply_sorting(qs, request, sorting_options)

    return qs.select_related('country_id')

from django.urls import reverse

def enrich_affiliations_page(objs, user_id):
    # 기관 id 수집
    aff_ids = [a.id for a in objs]

    # ✅ 항상 미리 초기화 (조기반환/빈 결과 대비)
    authors_map = {aid: [] for aid in aff_ids}
    kw_map      = {aid: [] for aid in aff_ids}
    part_map    = {aid: "-" for aid in aff_ids}

    if not aff_ids:
        return []  # 안전 조기 반환

    # ---------- 저자 Top-5 ----------
    # (distinct 저자 목록을 모은 뒤, 상위 5개만 잘라서 매핑)
    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT paff.affiliation_id, a.id, a.name
            FROM paper_affiliation paff
            JOIN paper_author pa ON pa.paper_id = paff.paper_id
            JOIN author a ON a.id = pa.author_id
            WHERE paff.affiliation_id IN ({",".join(["%s"]*len(aff_ids))})
            GROUP BY paff.affiliation_id, a.id, a.name
            ORDER BY paff.affiliation_id ASC, a.name ASC
            """,
            aff_ids
        )
        rows = cur.fetchall()

    tmp_auth = defaultdict(list)
    for aff_id, author_id, author_name in rows:
        tmp_auth[aff_id].append({"id": author_id, "name": author_name})
    for k, v in tmp_auth.items():
        authors_map[k] = v[:5]  # 상위 5명

    # ---------- 키워드 Top-5 ----------
    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT paff.affiliation_id, k.id, k.keyword_name, COUNT(*) AS c
            FROM paper_affiliation paff
            JOIN paper_keyword pk ON pk.paper_id = paff.paper_id
            JOIN keyword k ON k.id = pk.keyword_id
            WHERE paff.affiliation_id IN ({",".join(["%s"]*len(aff_ids))})
            GROUP BY paff.affiliation_id, k.id, k.keyword_name
            ORDER BY paff.affiliation_id ASC, c DESC, k.keyword_name ASC
            """,
            aff_ids
        )
        rows = cur.fetchall()

    cur_aff = None
    bucket = []
    for aff_id, kid, kname, _cnt in rows:
        if cur_aff != aff_id:
            if cur_aff is not None:
                kw_map[cur_aff] = bucket[:5]
            cur_aff = aff_id
            bucket = []
        bucket.append({"id": kid, "name": kname})
    if cur_aff is not None:
        kw_map[cur_aff] = bucket[:5]

    # ---------- 메인 파트(연구분야) 최빈 보정 ----------
    with connection.cursor() as cur:
        cur.execute(
            f"""
            SELECT paff.affiliation_id, ptn.name, COUNT(*) AS c
            FROM paper_affiliation paff
            JOIN paper_part pp ON pp.paper_id = paff.paper_id
            JOIN part ptn ON ptn.id = pp.part_id
            WHERE paff.affiliation_id IN ({",".join(["%s"]*len(aff_ids))})
            GROUP BY paff.affiliation_id, ptn.name
            ORDER BY paff.affiliation_id ASC, c DESC, ptn.name ASC
            """,
            aff_ids
        )
        rows = cur.fetchall()

    seen = set()
    for aff_id, part_name, cnt in rows:
        if aff_id not in seen:
            part_map[aff_id] = part_name or "-"
            seen.add(aff_id)

    # ---------- 직렬화 ----------
    data = []
    for a in objs:
        cobj = getattr(a, "country_id", None)
        country_name = getattr(cobj, "name", None) or "정보 없음"
        country_pk   = getattr(cobj, "id", None)

        # annotate(main_part) 값이 있더라도 SQL 최빈값으로 최종 보정
        main_part_annot = getattr(a, "main_part", None)
        main_part_final = part_map.get(a.id) or main_part_annot or "-"

        data.append({
            "id": a.id,
            "name": a.name,
            "paper_count": getattr(a, "paper_count", 0) or 0,
            "avg_citations": round(getattr(a, "avg_citations", 0) or 0, 2),
            "main_part": main_part_final,
            "top_keywords": kw_map.get(a.id, []),     # ✅ 안전 접근
            "authors": authors_map.get(a.id, []),     # ✅ 안전 접근
            "remaining_authors": 0,
            "country": country_name,
            "country_id": country_pk,
            "country_url": reverse("country_page", kwargs={"country_id": country_pk}) if country_pk else None,
        })

    # ---------- 좋아요 ----------
    liked_items, total_likes = get_like_data(user_id, "like_affiliation", "affiliation_id", aff_ids)
    for x in data:
        x["liked"] = liked_items.get(x["id"], False)
        x["like_count"] = total_likes.get(x["id"], 0)

    return data

# --- NEW: affiliation 전체 결과에서 좌측 필터 생성 ---
AFF_FILTER_MAX_IDS = 5000  # 안전 상한선 (필요 시 조정)

def build_available_filters_for_affiliations(qs):
    """
    좌측 필터(국가, 연구분야, 저자, 기관)를 '검색어로 매칭된 전체 결과'에서 생성.
    qs: search_affiliations_base_qs()가 반환한 Annotate 완료 쿼리셋 (main_part 포함)
    반환: {"countries":[...], "parts":[...], "authors":[...], "affiliations":[...]}
    """
    # 1) 국가/연구분야/기관: DB distinct
    countries = list(
        qs.exclude(country_id__isnull=True)
          .values_list('country_id__name', flat=True)
          .distinct()
          .order_by('country_id__name')
    )
    parts = list(
        qs.exclude(main_part__isnull=True)
          .values_list('main_part', flat=True)
          .distinct()
          .order_by('main_part')
    )
    affiliations = list(
        qs.values_list('name', flat=True)
          .distinct()
          .order_by('name')
    )

    # 2) 저자: 현재 결과의 기관 id 집합으로 범위 제한 (상한선 적용)
    aff_ids = list(qs.values_list('id', flat=True)[:AFF_FILTER_MAX_IDS])
    parts = []
    if aff_ids:
        placeholders = ",".join(["%s"] * len(aff_ids))
        sql_parts = f"""
            SELECT DISTINCT ptn.name
            FROM paper_affiliation paff
            JOIN paper_part pp   ON pp.paper_id = paff.paper_id
            JOIN part ptn        ON ptn.id      = pp.part_id
            WHERE paff.affiliation_id IN ({placeholders})
            ORDER BY ptn.name ASC
        """
        with connection.cursor() as cur:
            cur.execute(sql_parts, aff_ids)
            parts = [row[0] for row in cur.fetchall() if row[0]]

    # 3) 저자 역시 동일 (현행 유지)
    authors = []
    if aff_ids:
        placeholders = ",".join(["%s"] * len(aff_ids))
        sql_auth = f"""
            SELECT DISTINCT a.name
            FROM paper_affiliation paff
            JOIN paper_author pa ON pa.paper_id = paff.paper_id
            JOIN author a        ON a.id        = pa.author_id
            WHERE paff.affiliation_id IN ({placeholders})
            ORDER BY a.name ASC
        """
        with connection.cursor() as cur:
            cur.execute(sql_auth, aff_ids)
            authors = [row[0] for row in cur.fetchall() if row[0]]

    return {
        "countries": countries,
        "parts": parts,
        "authors": authors,
        "affiliations": affiliations,
    }

def search_affiliations(query, request, user_id):
    search_fields = ['name']
    query_filter = generate_and_query(search_fields, query)

    affiliations = Affiliation.objects.filter(query_filter).annotate(
        paper_count=Count('affiliation_keywords__paper_id', distinct=True),
        avg_citations=Avg('affiliation_keywords__paper_id__citation')
    )
    sorting_options = {
        'papers': 'paper_count',
        'citations': 'avg_citations',
        'title': 'name',
    }
    affiliations = apply_sorting(affiliations, request, sorting_options)

    data = []
    for aff in affiliations:
        paper_ids = Paper_affiliation.objects.filter(affiliation_id=aff.id).values_list('paper_id', flat=True)

        part_counts = (
            Paper_part.objects.filter(paper_id__in=paper_ids)
            .values('part_id__name')
            .annotate(count=Count('part_id'))
            .order_by('-count')
        )
        main_part = part_counts[0]['part_id__name'] if part_counts.exists() else "-"

        keyword_counts = (
            Paper_keyword.objects.filter(paper_id__in=paper_ids)
            .values('keyword_id', 'keyword_id__keyword_name')
            .annotate(count=Count('keyword_id'))
            .order_by('-count')[:5]
        )
        top_keywords = [
            {"id": k["keyword_id"], "name": k["keyword_id__keyword_name"]}
            for k in keyword_counts
        ]

        authors_qs = (
            Paper_author.objects.filter(paper_id__in=paper_ids)
            .values('author_id', 'author_id__name')
            .distinct()
        )
        all_authors = [
            {"id": it["author_id"], "name": it["author_id__name"]}
            for it in authors_qs
        ]

        if len(all_authors) > 5:
            display_authors = all_authors[:5]
            remaining_authors = len(all_authors) - 5
        else:
            display_authors = all_authors
            remaining_authors = 0

        country_name = aff.country_id.name if aff.country_id else "정보 없음"
        country_id = aff.country_id.id if aff.country_id else None

        data.append({
            "id": aff.id,
            "name": aff.name,
            "paper_count": aff.paper_count,
            "avg_citations": round(aff.avg_citations, 2) if aff.avg_citations else 0,
            "main_part": main_part,
            "top_keywords": top_keywords,
            "authors": display_authors,
            "remaining_authors": remaining_authors,
            "country": country_name,
            "country_id": country_id,
        })
    # 좋아요 정보
    affiliation_ids = [a["id"] for a in data]
    liked_items, total_likes = get_like_data(user_id, "like_affiliation", "affiliation_id", affiliation_ids)
    for a in data:
        a["liked"] = liked_items.get(a["id"], False)
        a["like_count"] = total_likes.get(a["id"], 0)
        
    selected_filters = {
        "parts": get_filter_list(request, "parts"),        
        "countries": get_filter_list(request, "countries"), 
        "authors": get_filter_list(request, "authors"),    
        "affiliations": get_filter_list(request, "affiliations"),
    }
    
    filtered_data = data

    if selected_filters["parts"]:
        filtered_data = [
            d for d in filtered_data 
            if d.get("main_part") and d["main_part"] in selected_filters["parts"]
        ]
    if selected_filters["countries"]:
        filtered_data = [
            d for d in filtered_data 
            if d.get("country") and d["country"] in selected_filters["countries"]
        ]
    if selected_filters["authors"]:
        filtered_data = [
            d for d in filtered_data
            if any(a.get("name") in selected_filters["authors"] for a in d.get("authors", []))
        ]
    if selected_filters["affiliations"]:
        filtered_data = [
            d for d in filtered_data
            if d.get("name") and d["name"] in selected_filters["affiliations"]
        ]

    data = filtered_data

    filter_fields = {
        "countries": "country",
        "parts": "main_part",
        "authors": "authors",      
        "affiliations": "name",
    }
    available_filters = extract_filters_from_results(data, filter_fields)

    return {
        "results": data,
        "results_count": len(data),
        "available_filters": available_filters
    }

def search_keywords(query, request, user_id):
    search_fields = ['keyword_name']
    query_filter = generate_and_query(search_fields, query)

    keywords = Keyword.objects.filter(query_filter).annotate(
        paper_count=Count('keyword_keywords__paper_id', distinct=True)
    )
    sorting_options = {
        'papers': 'paper_count',
        'title': 'keyword_name',
    }
    keywords = apply_sorting(keywords, request, sorting_options)

    data = []
    for keyword in keywords:
        paper_ids = list(
            Paper_keyword.objects.filter(keyword_id=keyword.id).values_list('paper_id', flat=True)
        )

        main_part_obj = (
            Paper_part.objects.filter(paper_id__in=paper_ids)
            .values('part_id__name')
            .annotate(count=Count('part_id'))
            .order_by('-count')
            .first()
        )
        main_part = main_part_obj['part_id__name'] if main_part_obj else None

        main_year_obj = (
            Paper.objects.filter(id__in=paper_ids)
            .values('year')
            .annotate(count=Count('year'))
            .order_by('-count')
            .first()
        )
        main_year = main_year_obj['year'] if main_year_obj else None

        data.append({
            "id": keyword.id,
            "keyword_name": keyword.keyword_name,
            "paper_count": keyword.paper_count,
            "main_part": main_part,
            "main_year": main_year,
        })
    # 좋아요
    keyword_ids = [k["id"] for k in data]
    liked_items, total_likes = get_like_data(user_id, "like_keyword", "keyword_id", keyword_ids)
    for k in data:
        k["liked"] = liked_items.get(k["id"], False)
        k["like_count"] = total_likes.get(k["id"], 0)
        
    selected_filters = {
        "parts": get_filter_list(request, "parts"),  
        "years": get_filter_list(request, "years"),   
    }
    filtered_data = data

    if selected_filters["parts"]:
        filtered_data = [
            d for d in filtered_data
            if d.get("main_part") and d["main_part"] in selected_filters["parts"]
        ]
    if selected_filters["years"]:
        filtered_data = [
            d for d in filtered_data
            if d.get("main_year") and str(d["main_year"]) in selected_filters["years"]
        ]

    data = filtered_data

    filter_fields = {
        "years": "main_year",
        "parts": "main_part",
    }
    available_filters = extract_filters_from_results(data, filter_fields)

    return {
        "results": data,
        "results_count": len(data),
        "available_filters": available_filters
    }

def search_countries(query, request, user_id):
    search_fields = ['name']
    query_filter = generate_and_query(search_fields, query)

    countries = (
        Country.objects
        .filter(query_filter)
        .annotate(
            paper_count=Count('country_countrys__paper_id', distinct=True),
            avg_citations=Avg('country_countrys__paper_id__citation'),
            author_count=Count('country_countrys__paper_id__author_papers__author_id', distinct=True),
            affiliation_count=Count('country_countrys__paper_id__affiliation_papers__affiliation_id', distinct=True),
        )
    )
    sorting_options = {
        'papers': 'paper_count',
        'citations': 'avg_citations',
        'title': 'name',
    }
    countries = apply_sorting(countries, request, sorting_options)

    data = []
    for c in countries:
        paper_ids = (
            Paper_country.objects.filter(country_id=c.id)
            .values_list('paper_id', flat=True)
            .distinct()
        )
        top_keywords = []
        if paper_ids:
            keyword_counts = (
                Paper_keyword.objects.filter(paper_id__in=paper_ids)
                .values('keyword_id', 'keyword_id__keyword_name')
                .annotate(count=Count('keyword_id'))
                .order_by('-count')[:5]
            )
            top_keywords = [
                {"id": k['keyword_id'], "name": k['keyword_id__keyword_name']}
                for k in keyword_counts
            ]
        data.append({
            "id": c.id,
            "name": c.name,
            "paper_count": c.paper_count,
            "avg_citations": round(c.avg_citations, 2) if c.avg_citations else 0,
            "author_count": c.author_count,
            "affiliation_count": c.affiliation_count,
            "top_keywords": top_keywords,
        })
    # 좋아요
    country_ids = [co["id"] for co in data]
    liked_items, total_likes = get_like_data(user_id, "like_country", "country_id", country_ids)
    for co in data:
        co["liked"] = liked_items.get(co["id"], False)
        co["like_count"] = total_likes.get(co["id"], 0)

    filter_fields = {
        "parts": "main_part", 
    }
    available_filters = extract_filters_from_results(data, filter_fields)

    return {
        "results": data,
        "results_count": len(data),
        "available_filters": available_filters
    }

#  TF-IDF + 인용수 가중치 기반 추천 키워드
def recommend_keywords_tfidf_citation(query, max_keywords=30):
    query = unquote(query).strip()
    if not query:
        return [] 

    query_terms = query.split()
    if not query_terms:
        return [] 
    query = unquote(query)

    query_terms = query.split()
    related_keywords = Keyword.objects.filter(
        keyword_name__icontains=query_terms[0]  # 첫 번째 단어 기준으로 우선 필터링
    )

    for term in query_terms[1:]:  # 나머지 단어들도 추가 필터링
        related_keywords |= Keyword.objects.filter(keyword_name__icontains=term)

    if not related_keywords.exists():
        return []

    #  검색어가 포함된 키워드를 갖는 논문 찾기
    paper_ids = Paper_keyword.objects.filter(keyword_id__in=related_keywords).values_list("paper_id", flat=True)

    #  해당 논문에서 등장하는 모든 키워드 가져오기
    all_keywords = (
        Paper_keyword.objects
        .filter(paper_id__in=paper_ids)
        .values_list("keyword_id__keyword_name", flat=True)
    )

    if not all_keywords:
        return []

    # TF-IDF 벡터라이저를 이용한 키워드 중요도 계산
    vectorizer = TfidfVectorizer(ngram_range=(1, 2))  # ✅ 2-gram 추가
    tfidf_matrix = vectorizer.fit_transform(all_keywords)

    # 검색어에 대한 TF-IDF 값 가져오기
    query_vector = vectorizer.transform([" ".join(query_terms)])  # ✅ 띄어쓰기 포함 검색어 처리
    cosine_similarities = np.dot(tfidf_matrix, query_vector.T).toarray().flatten()

    # 키워드별 기본 점수 저장
    keyword_scores = defaultdict(float)
    for i, kw in enumerate(all_keywords):
        keyword_scores[kw] += cosine_similarities[i]  # 기본 TF-IDF 점수 반영

    # 논문 인용수 기반 가중치 추가
    five_years_ago = datetime.now().year - 5
    papers = Paper.objects.filter(id__in=paper_ids).annotate(total_citations=Sum("citation"))

    for paper in papers:
        paper_keywords = Paper_keyword.objects.filter(paper_id=paper.id).values_list("keyword_id__keyword_name", flat=True)
        
        # 논문의 인용수를 가중치로 활용
        weight = paper.citation + (5 if paper.year >= five_years_ago else 0)  # 최근 5년 이내 가중치 추가
        for kw in paper_keywords:
            keyword_scores[kw] += weight  # 가중치 적용
    
    query_terms_lower = set(t.lower() for t in query_terms)

    # 점수가 높은 키워드 중 검색어 제외
    filtered_keywords = [
        (kw, score) for kw, score in keyword_scores.items()
        if kw.lower() not in query_terms_lower
    ]

    sorted_keywords = sorted(filtered_keywords, key=lambda x: x[1], reverse=True)[:max_keywords]
    return [{"text": kw[0], "id": i, "score": kw[1]} for i, kw in enumerate(sorted_keywords)]

def build_base_query(request):
    params = request.GET.copy()
    params.pop('page', None)  # 페이지만 제거
    return params.urlencode()

def get_custom_page_range(current, total, window=2):
    # 1 2 [3] 4 5 형태(엘리드 생략형이 필요하면 대체 가능)
    start = max(1, current - window)
    end = min(total, current + window)
    return range(start, end + 1)

def paginate(queryset, request, default_per_page=10, block_size=10):
    get = request.GET.copy()
    page = int(get.get('page', 1) or 1)
    try:
        per_page = int(get.get('items_per_page', default_per_page))
    except ValueError:
        per_page = default_per_page

    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(page)

    # block 페이지네이션
    current = page_obj.number
    start = ((current - 1) // block_size) * block_size + 1
    end = min(start + block_size - 1, paginator.num_pages)
    page_range = range(start, end + 1)

    # base_query: page만 제거
    get.pop('page', None)
    get.pop('items_per_page', None)

    base_query = get.urlencode()

    return page_obj, page_range, per_page, base_query

# 1) 공통 멀티 정렬 유틸
def _multi_sort_list(data, selected_sorts, sort_order, key_map):
    reverse = (sort_order == 'desc')

    def get_val(item, key):
        v = item.get(key)
        if v is None:
            return 0
        return v.lower() if isinstance(v, str) else v

    def key_tuple(item):
        ks = []
        for s in selected_sorts:
            target = key_map.get(s)
            if not target:
                continue
            if isinstance(target, (list, tuple)):
                ks.extend([get_val(item, t) for t in target])
            else:
                ks.append(get_val(item, target))
        return tuple(ks) if ks else (0,)
    return sorted(data, key=key_tuple, reverse=reverse)

def search(request):
    query = request.GET.get('query', '').strip()
    filter_type = request.GET.get('filter', 'paper')
    sort_order = request.GET.get('sort_order', 'desc')
    raw_per_page = request.GET.get("items_per_page")
    try:
        items_per_page = int(raw_per_page) if raw_per_page else None
    except ValueError:
        items_per_page = None

    # ✅ 멀티 정렬 파싱 (클릭 순서가 우선순위)
    selected_sorts = request.GET.getlist('sort_by')

    # ✅ 기본 정렬: 초기 진입(=sort_by 파라미터가 전혀 없는 경우)에만 accuracy 적용
    if not selected_sorts:
        selected_sorts = ['accuracy']

    user_id = request.user.id if request.user.is_authenticated else None

    key_maps = {
        'paper': {
            'accuracy': '_score',        # search_papers_accuracy()에서만 존재
            'latest': 'year',
            'citations': 'citation',
            'title': 'title',
        },
        'author': {
            'accuracy': 'name',          # 비-paper의 accuracy는 name 기준으로 대체
            'papers': 'paper_count',
            'citations': 'total_citations',
            'title': 'name',
        },
        'affiliation': {
            'accuracy': 'name',
            'papers': 'paper_count',
            'citations': 'avg_citations',
            'title': 'name',
        },
        'keyword': {
            'accuracy': 'keyword_name',
            'papers': 'paper_count',
            'title': 'keyword_name',
        },
        'country': {
            'accuracy': 'name',
            'papers': 'paper_count',
            'citations': 'avg_citations',
            'authors': 'author_count',
            'affiliations': 'affiliation_count',
            'title': 'name',
        },
    }
    if filter_type == 'affiliation':
        base_qs = search_affiliations_base_qs(query, request)  # 정렬까지 DB에서 완료
        page_obj, page_range, per_page, base_query = paginate(
            base_qs, request, default_per_page=(items_per_page or 10)
        )

        available_filters = build_available_filters_for_affiliations(base_qs)

        page_data = enrich_affiliations_page(list(page_obj.object_list), user_id)

        # (선택) 멀티 정렬 2차 보정 (메모리 내)
        results = _multi_sort_list(page_data, selected_sorts, sort_order, key_maps['affiliation'])

        # 추천 키워드(워드클라우드)
        try:
            word_limit = int(request.GET.get('word_limit', 40))
        except ValueError:
            word_limit = 40
        word_limit = max(5, min(word_limit, 100))
        words_data_json = json.dumps(
            recommend_keywords_tfidf_citation(query, max_keywords=word_limit),
            ensure_ascii=False
        )

        context = {
            "filter_type": filter_type,
            "query": query,
            "user_id": user_id,
            "items_per_page": per_page,
            "saved_paper_ids": [],               # affiliation 화면에서는 불필요
            "words_data_json": words_data_json,
            "page_obj": page_obj,
            "page_range": page_range,
            "base_query": base_query,
            "results_count": page_obj.paginator.count,
            "sort_by_list": selected_sorts,
            "sort_order": sort_order,
            "results": results,
            "available_filters": available_filters,
        }

        # 🔑 Ajax 응답 or HTML 렌더링을 **여기서 바로 리턴**
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            html = render_to_string("search/partials/_result_affiliation.html", context, request=request)
            pagination_html = render_to_string("search/partials/_pagination.html", context, request=request)
            return JsonResponse({
                "html": html,
                "results_count": context["results_count"],
                "page": page_obj.number,
                "pagination_html": pagination_html,
                "saved_paper_ids": [],
                "items_per_page": per_page,
            })
        return render(request, "search/searchpage.html", context)
    if filter_type == 'paper':
        data = (search_papers_accuracy(query, request, user_id)
                if 'accuracy' in selected_sorts else
                search_papers_with_embedding(query, request, user_id))
    elif filter_type == 'author':
        data = search_authors(query, request, user_id)
    elif filter_type == 'keyword':
        data = search_keywords(query, request, user_id)
    elif filter_type == 'country':
        data = search_countries(query, request, user_id)
    else:
        data = {"results": [], "results_count": 0, "available_filters": {}}

    results = _multi_sort_list(data.get('results', []), selected_sorts, sort_order, key_maps.get(filter_type, {}))
    page_obj, page_range, per_page, base_query = paginate(
        results, request, default_per_page=(items_per_page or 10)
    )

    data["results"] = list(page_obj.object_list)

    saved_paper_ids = []
    if user_id:
        with connection.cursor() as cursor:
            cursor.execute("SELECT paper_id FROM savedpaper WHERE user_id = %s", [user_id])
            saved_paper_ids = [row[0] for row in cursor.fetchall()]

    # 추천 키워드
    try:
        word_limit = int(request.GET.get('word_limit', 40))
    except ValueError:
        word_limit = 40
    word_limit = max(5, min(word_limit, 100))
    words_data_json = json.dumps(
        recommend_keywords_tfidf_citation(query, max_keywords=word_limit),
        ensure_ascii=False
    )

    # 6) 컨텍스트
    context = {
        "filter_type": filter_type,
        "query": query,
        "user_id": user_id,
        "items_per_page": per_page,
        "saved_paper_ids": saved_paper_ids,
        "words_data_json": words_data_json,
        "page_obj": page_obj,
        "page_range": page_range,
        "base_query": base_query,
        "results_count": page_obj.paginator.count,
        "sort_by_list": selected_sorts,
        "sort_order": sort_order,
        **data,
    }
    if filter_type != 'affiliation':     # ✅ affiliation은 enrich된 dict 유지!
        data["results"] = list(page_obj.object_list)
    context.update(data)

    # 7) Ajax 응답
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        html = render_to_string(f"search/partials/_result_{filter_type}.html", context, request=request)
        pagination_html = render_to_string("search/partials/_pagination.html", context, request=request)
        return JsonResponse({
            "html": html,
            "results_count": page_obj.paginator.count,
            "page": page_obj.number,
            "pagination_html": pagination_html,
            "saved_paper_ids": saved_paper_ids,
            "items_per_page": per_page,
        })

    return render(request, 'search/searchpage.html', context)

from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.db import connection
# views.py
from django.db import connection, transaction

def _has_column(table, column):
    with connection.cursor() as cur:
        desc = connection.introspection.get_table_description(cur, table)
    # Django 5.x: desc[i].name 사용, 드라이버별 호환 위해 getattr 사용
    cols = [getattr(col, "name", col[0]) for col in desc]
    return column in cols

def _toggle_like(table, col, item_id, user_id):
    with transaction.atomic(), connection.cursor() as cur:
        # 이미 눌렀으면 삭제(토글 off)
        cur.execute(f"SELECT 1 FROM {table} WHERE user_id=%s AND {col}=%s", [user_id, item_id])
        if cur.fetchone():
            cur.execute(f"DELETE FROM {table} WHERE user_id=%s AND {col}=%s", [user_id, item_id])
            liked = False
        else:
            # 스키마에 count 컬럼이 있으면 1로 넣기
            if _has_column(table, "count"):
                cur.execute(
                    f"INSERT INTO {table} (user_id, {col}, count) VALUES (%s, %s, 1)",
                    [user_id, item_id]
                )
            else:
                cur.execute(
                    f"INSERT INTO {table} (user_id, {col}) VALUES (%s, %s)",
                    [user_id, item_id]
                )
            liked = True

        # 현재 총 카운트 반환
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {col}=%s", [item_id])
        count = cur.fetchone()[0]
    return liked, count

def _require_user(request):
    if not request.user.is_authenticated:
        return None, JsonResponse({"error":"로그인이 필요합니다."}, status=401)
    return request.user.id, None

@require_POST
def like_paper(request, item_id):
    user_id, err = _require_user(request)
    if err: return err
    liked, count = _toggle_like("like_paper", "paper_id", item_id, user_id)
    return JsonResponse({"liked": liked, "count": count})

@require_POST
def like_author(request, item_id):
    user_id, err = _require_user(request)
    if err: return err
    liked, count = _toggle_like("like_author", "author_id", item_id, user_id)
    return JsonResponse({"liked": liked, "count": count})

@require_POST
def like_keyword(request, item_id):
    user_id, err = _require_user(request)
    if err: return err
    liked, count = _toggle_like("like_keyword", "keyword_id", item_id, user_id)
    return JsonResponse({"liked": liked, "count": count})

@require_POST
def like_country(request, item_id):
    user_id, err = _require_user(request)
    if err: return err
    liked, count = _toggle_like("like_country", "country_id", item_id, user_id)
    return JsonResponse({"liked": liked, "count": count})

@require_POST
def like_affiliation(request, item_id):
    user_id, err = _require_user(request)
    if err: return err
    liked, count = _toggle_like("like_affiliation", "affiliation_id", item_id, user_id)
    return JsonResponse({"liked": liked, "count": count})
