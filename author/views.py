# ✅ author 앱에 포함될 view 함수 정리 및 이전 (from views.py)
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.db.models import Count, Sum
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.decorators import login_required
from django.db import connection
import requests
import json
import re
import os
from django.conf import settings
from django.core.paginator import Paginator
from main.models import Author, Paper, Paper_author, Paper_part, Paper_keyword, Affiliation, Country, Paper_affiliation
from django.db.models.functions import Coalesce
from datetime import datetime
# ✅ 저자 상세 페이지 뷰 함수 (author_page.html에서 사용)
def author_page(request, author_id):
    author = get_object_or_404(Author, id=author_id)
    paper_ids = Paper_author.objects.filter(author_id=author.id).values_list('paper_id', flat=True)

    publication_count = len(paper_ids)
    total_citations = Paper.objects.filter(id__in=paper_ids).aggregate(Sum('citation'))['citation__sum'] or 0
    avg_citations = total_citations / publication_count if publication_count > 0 else 0

    keyword_counts = (
        Paper_keyword.objects.filter(paper_id__in=paper_ids)
        .values('keyword_id', 'keyword_id__keyword_name')
        .annotate(count=Count('keyword_id'))
        .order_by('-count')[:3]
    )
    keywords = [{'id': item['keyword_id'], 'name': item['keyword_id__keyword_name']} for item in keyword_counts]

    part_counts = (
        Paper_part.objects.filter(paper_id__in=paper_ids)
        .values('part_id__name')
        .annotate(count=Count('part_id'))
        .order_by('-count')
    )
    main_part = part_counts.first()['part_id__name'] if part_counts.exists() else "정보 없음"

    affiliation = Affiliation.objects.filter(name=author.affiliation).first()
    affiliation_id = affiliation.id if affiliation else None
    country = affiliation.country_id.name if affiliation and affiliation.country_id else "정보 없음"
    country_id = affiliation.country_id.id if affiliation and affiliation.country_id else None

    like_count = author.like_author_set.count() if hasattr(author, 'like_author_set') else 0
    user_liked = False
    if request.user.is_authenticated:
        user_liked = author.like_author_set.filter(user_id=request.user.id).exists()

     # ✅ 논문 리스트
    papers = Paper.objects.filter(id__in=paper_ids).order_by('-year')
    paginator = Paginator(papers, 10)  # 10개씩 페이지네이션
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    page_range = paginator.get_elided_page_range(number=page_obj.number, on_each_side=2, on_ends=1)

    context = {
        'author': author,
        'publication_count': publication_count,
        'total_citations': total_citations,
        'avg_citations': avg_citations,
        'keywords': keywords,
        'main_part': main_part,
        'country': country,
        'country_id': country_id,
        'affiliation_id': affiliation_id,
        'like_count': like_count,
        'user_liked': user_liked,
        'page_obj': page_obj,
        'page_range': page_range,
    }
    return render(request, 'author/author_page.html', context)

# ✅ 저자 분석 API (정량적 분석용 데이터 제공)
def author_analysis_api(request, author_id):
    author = get_object_or_404(Author, id=author_id)

    # 1) 본인 논문 id 목록
    paper_ids_qs = Paper_author.objects.filter(
        author_id=author.id
    ).values_list('paper_id', flat=True)

    # 본인 전체 출판 수
    publication_count = Paper_author.objects.filter(
        author_id=author.id
    ).values('paper_id').distinct().count()

    # 2) 연도별 출판 수
    year_chart_data = (
        Paper.objects.filter(id__in=paper_ids_qs)
        .values('year')
        .annotate(count=Count('id'))
        .order_by('year')
    )
    year_chart_dict = {item['year']: item['count'] for item in year_chart_data}

    # 3) 공동저자(나와 같은 논문에 참여) + 나와의 공동연구 횟수(count)
    coauthors_base = (
        Paper_author.objects.filter(paper_id__in=paper_ids_qs)
        .exclude(author_id=author.id)
        .values('author_id', 'author_id__name')
        .annotate(count=Count('paper_id', distinct=True))   # ✅ 공동연구 횟수
        .order_by('-count')[:10]                            # 필요시 상한 조정
    )
    coauthor_ids = [row['author_id'] for row in coauthors_base]

    # 4) 공동저자들의 '전체 논문 수(pubs)' 한 번에 계산
    pubs_map = dict(
        Paper_author.objects.filter(author_id__in=coauthor_ids)
        .values('author_id')
        .annotate(pubs=Count('paper_id', distinct=True))
        .values_list('author_id', 'pubs')
    )

    # 5) 네트워크 응답: pubs 포함
    network_data = [
        {
            "id": row["author_id"],
            "name": row["author_id__name"],
            "count": row["count"],                 # 나와의 공동연구 횟수
            "pubs": pubs_map.get(row["author_id"], 0)  # 해당 저자의 전체 논문 수
        }
        for row in coauthors_base
    ]

    # 6) 파트별 분포
    part_chart_data = (
        Paper_part.objects.filter(paper_id__in=paper_ids_qs)
        .values('part_id__name')
        .annotate(count=Count('part_id'))
        .order_by('-count')
    )
    part_chart_dict = {item['part_id__name']: item['count'] for item in part_chart_data}

   # 7) 키워드 TOP N  ✅ FBV에서는 request.GET 사용 + 안전한 클램프
    try:
        req_limit = int(request.GET.get('max_words', 80))
    except (TypeError, ValueError):
        req_limit = 80
    LIMIT = max(10, min(req_limit, 200))   # 10~200 사이로 제한(원하는 범위로 조정)

    keyword_counts = (
        Paper_keyword.objects.filter(paper_id__in=paper_ids_qs)
        .values('keyword_id__keyword_name')
        .annotate(count=Count('keyword_id'))
        .order_by('-count')[:LIMIT]
    )
    keyword_dict = {i['keyword_id__keyword_name']: i['count'] for i in keyword_counts}

    # ✅ publication_count(부모 노드 논문 수)도 같이 내려줌
    response_data = {
        "publication_count": publication_count,   # 부모 노드 총 논문 수
        "year_chart_data": year_chart_dict,
        "network_data": network_data,             # ← pubs 포함됨
        "part_chart_data": part_chart_dict,
        "keyword_data": keyword_dict,
    }
    return JsonResponse(response_data)

OLLAMA_URL = ""
@login_required
def analyze_author(request, author_id):
    """저자의 정량 데이터 → 전략까지 제시하는 정성 분석 (Ollama)"""
    author = get_object_or_404(Author, id=author_id)

    # ---------- 1) 집계 ----------
    paper_ids = list(
        Paper_author.objects.filter(author_id=author)
        .values_list('paper_id', flat=True)
    )
    pubs = Paper.objects.filter(id__in=paper_ids)
    publication_count = len(paper_ids)

    year_rows = pubs.values('year').annotate(cnt=Count('id')).order_by('year')
    year_chart_dict = {r['year']: r['cnt'] for r in year_rows if r['year']}
    years = sorted(year_chart_dict.keys())
    first_year = years[0] if years else None
    last_year  = years[-1] if years else None
    active_span = (last_year - first_year + 1) if (first_year and last_year) else 0

    def last_n_sum(n):
        if not years: return 0
        tail = [y for y in years if y >= (last_year - n + 1)]
        return sum(year_chart_dict.get(y, 0) for y in tail)

    def prev_n_sum(n):
        if not years: return 0
        prev = [y for y in years if (last_year - 2*n) < y < (last_year - n + 1)]
        return sum(year_chart_dict.get(y, 0) for y in prev)

    recent3 = last_n_sum(3)
    prev3   = prev_n_sum(3)
    recent_ratio = (recent3 / publication_count) if publication_count else 0
    if recent3 > prev3 * 1.15:
        trend = "상승"
    elif recent3 < prev3 * 0.85:
        trend = "하락"
    else:
        trend = "보합"

    citations = [c or 0 for c in pubs.values_list('citation', flat=True)]
    total_citations = sum(citations)
    avg_citations   = (total_citations / publication_count) if publication_count else 0
    max_citation    = max(citations) if citations else 0
    top_cited       = pubs.filter(citation=Coalesce(max_citation, 0)).first()
    top_cited_paper = f"{(top_cited.title[:60]+'…') if top_cited and len(top_cited.title)>60 else (top_cited.title if top_cited else '정보 없음')} ({max_citation}회)"

    def h_index_like(cites):
        arr = sorted(cites, reverse=True); h = 0
        for i, c in enumerate(arr, start=1):
            if c >= i: h = i
            else: break
        return h
    h_index = h_index_like(citations)

    coauthors_base = (
        Paper_author.objects.filter(paper_id__in=paper_ids)
        .exclude(author_id=author)
        .values('author_id__name')
        .annotate(cnt=Count('paper_id', distinct=True))
        .order_by('-cnt')
    )
    coauthor_count = coauthors_base.count()
    top_coauthors  = [f"{r['author_id__name']}({r['cnt']})" for r in coauthors_base[:5]]

    authors_per_paper = (
        Paper_author.objects.filter(paper_id__in=paper_ids)
        .values('paper_id').annotate(acnt=Count('author_id'))
        .values_list('acnt', flat=True)
    )
    avg_authors_per_paper = round(sum(authors_per_paper)/len(authors_per_paper), 2) if authors_per_paper else 0

    affiliation_count = (
        Paper_affiliation.objects.filter(paper_id__in=paper_ids)
        .values('affiliation_id').distinct().count()
    )

    venue_top_qs = (
        pubs.values('published_in')
        .annotate(cnt=Count('id'))
        .order_by('-cnt')[:5]
    )
    venue_top = [v for v in venue_top_qs if v['published_in']]

    part_counts = (
        Paper_part.objects.filter(paper_id__in=paper_ids)
        .values('part_id__name')
        .annotate(cnt=Count('part_id'))
        .order_by('-cnt')
    )
    main_part = part_counts.first()['part_id__name'] if part_counts.exists() else "정보 없음"

    kw_rows = (
        Paper_keyword.objects.filter(paper_id__in=paper_ids)
        .values('keyword_id__keyword_name')
        .annotate(cnt=Count('keyword_id'))
        .order_by('-cnt')
    )
    top_keywords = [f"{r['keyword_id__keyword_name']}({r['cnt']})" for r in kw_rows[:10]]
    keyword_total_unique = kw_rows.count()

    # 초기 3년 vs 최근 3년 키워드
    early_year_cut  = (first_year + 2) if first_year else None
    recent_year_cut = (last_year - 2)  if last_year  else None
    early_ids  = list(pubs.filter(year__lte=early_year_cut).values_list('id', flat=True)) if early_year_cut else []
    recent_ids = list(pubs.filter(year__gte=recent_year_cut).values_list('id', flat=True)) if recent_year_cut else []

    early_kw_qs = (
        Paper_keyword.objects.filter(paper_id__in=early_ids)
        .values('keyword_id__keyword_name').annotate(cnt=Count('keyword_id'))
        .order_by('-cnt')[:5]
    ) if early_ids else []
    recent_kw_qs = (
        Paper_keyword.objects.filter(paper_id__in=recent_ids)
        .values('keyword_id__keyword_name').annotate(cnt=Count('keyword_id'))
        .order_by('-cnt')[:5]
    ) if recent_ids else []
    early_kw  = ", ".join([k['keyword_id__keyword_name'] for k in early_kw_qs]) if early_kw_qs else "정보 부족"
    recent_kw = ", ".join([k['keyword_id__keyword_name'] for k in recent_kw_qs]) if recent_kw_qs else "정보 부족"

    # ---------- 2) 프롬프트 ----------
    prompt = f"""
당신은 연구전략 컨설턴트입니다. 아래 '정량 지표'를 바탕으로 연구자 {author.name}에 대한
정성 분석과 함께 **실행 가능한 전략**을 한국어로만 작성하세요.

[정량 지표]
- 활동기간: {first_year} ~ {last_year} (연차 {active_span}년), 최근3년 비중: {recent_ratio:.0%}, 추세: {trend}
- 총 출판수: {publication_count}편, 총 인용수: {total_citations}회, 평균: {avg_citations:.2f}, 최고: {max_citation}, h-index(간이): {h_index}
- 최고 인용 논문: {top_cited_paper}
- 공저자 수: {coauthor_count}명, 상위 공저자: {', '.join(top_coauthors)}
- 논문당 평균 저자 수: {avg_authors_per_paper}, 참여 기관 수: {affiliation_count}
- 대표 venue TOP3: {', '.join([f"{v['published_in']}({v['cnt']})" for v in venue_top[:3]])}
- 대표 파트: {main_part}
- 키워드 고유 개수: {keyword_total_unique}
- 상위 키워드 TOP10: {', '.join(top_keywords)}
- 초기 3년 키워드: {early_kw} / 최근 3년 키워드: {recent_kw}
- 연도별 출판 수: {year_chart_dict}

[작성 형식]
1. 핵심 연구 분야와 연도별 추세 — 지표를 근거로 해석(4~6문장)
2. 영향력 분석 — 인용/최고논문/h-index 해석 + 한계(4~6문장)
3. 협업 네트워크 — 공저 구조 특징, 확장 제안(4~6문장)
4. 키워드 변화와 향후 연구 방향 — 초기→최근 이동, 응용 도메인(4~6문장)
5. 전략 인사이트 — (a)단기 6개월 (b)중기 12개월 로 나눠 **실행 항목** 3~5개씩 ✔ 체크리스트 형태
6. 협업/펀딩·데이터 전략 — 타깃 기관/저자, 유망 펀딩 키워드, 추천 벤치마크·데이터셋 3개
7. 출판 전략 — 권장 venue(국제학회/저널) 3~5개와 각 이유(간결)
요약(TL;DR): 핵심 3줄.
반드시 한국어로만, 과장 없이 명료하게. 마크다운/기호 없이 순수 텍스트.
""".strip()

    # ---------- 3) Ollama 호출 ----------
    try:
        res = requests.post(
            OLLAMA_URL,
            json={"model": "gemma", "prompt": prompt, "stream": False},
            headers={"Content-Type": "application/json"},
            timeout=120
        )
        j = res.json()
        if "response" not in j:
            return JsonResponse({"error":"Ollama 응답에 'response'가 없습니다."}, status=500)
        raw = j["response"].strip()
        raw = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', raw)
    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": f"요청 실패: {str(e)}"}, status=500)
    except json.JSONDecodeError as e:
        return JsonResponse({"error": f"JSON 파싱 실패: {str(e)}"}, status=500)

    # ---------- 4) 섹션 파싱 & HTML 렌더 ----------
    def build_sections(text: str) -> str:
        sections = []
       # 1) "1. 제목" 섹션 우선
        chunks = re.split(r'\n\s*(?=\d+\.\s)', text)
        for c in chunks:
            m = re.match(r'(\d+)\.\s*([^\n]+)\n(.*)', c, flags=re.S)
            if not m:
                continue
            no, title, body = m.groups()
            body_lines = [l.strip() for l in body.split('\n') if l.strip()]

            if no == '5':
                # (a)/(b) 버킷형 처리
                html_parts, bucket = [], []
                for line in body_lines:
                    if re.match(r'^\(?[ab]\)', line, flags=re.I):
                        if bucket:
                            html_parts.append('<ul class="ana-list">' + ''.join(f'<li>✔ {x}</li>' for x in bucket) + '</ul>')
                            bucket = []
                        html_parts.append(f"<p class='ana-subhead'>{line}</p>")
                    else:
                        bucket.append(line)
                if bucket:
                    html_parts.append('<ul class="ana-list">' + ''.join(f'<li>✔ {x}</li>' for x in bucket) + '</ul>')
                body_html = ''.join(html_parts)
            else:
                body_html = ''.join(f"<p>{l}</p>" for l in body_lines)

            # ✅ 이 줄이 **누락**되어 있었음 — 꼭 추가!
            sections.append(
                f"<div class='ana-sec' data-no='{no}'>{body_html}</div>"
            )

        if sections:
            return ''.join(sections)

        # 2) "## 제목"
        blocks = re.split(r'\n(?=##\s*)', text)
        for i, blk in enumerate(blocks, start=1):
            mm = re.match(r'##\s*([^\n]+)\n?(.*)', blk, flags=re.S)
            if mm:
                title, b = mm.groups()
                body_html = ''.join(f"<p>{l.strip()}</p>" for l in b.split('\n') if l.strip())
                sections.append(f"<div class='ana-sec' data-no='{i}'>{body_html}</div>")
        if sections:
            return ''.join(sections)

        # 3) 폴백
        body_html = ''.join(f"<p>{l.strip()}</p>" for l in text.split('\n') if l.strip())
        return f"<div class='ana-sec' data-no='1'><h5>분석 결과</h5>{body_html}</div>"

    # TL;DR 추출
    tldr_html = ""
    m = re.search(r'(요약|TL;DR)\s*[:：]?\s*(.*)', raw, flags=re.I|re.S)
    if m:
        tldr_text = m.group(2).strip()
        tldr_lines = [l.strip('- •').strip() for l in tldr_text.split('\n') if l.strip()]
        tldr_html = "<div class='ana-tldr'><h5>요약 (TL;DR)</h5>" + \
                    "".join(f"<p>• {l}</p>" for l in tldr_lines[:3]) + "</div>"

    sections_html = build_sections(raw)
    

    header_html = f"""
    <div class="ana-head">
      <div class="title">{author.name} 연구자 정성적 분석</div>
      <div class="ana-badges">
        <span class="badge-chip"><i>📅</i> 활동 {active_span}년</span>
        <span class="badge-chip"><i>📈</i> 최근3년 {recent_ratio:.0%}</span>
        <span class="badge-chip"><i>📚</i> {publication_count}편</span>
        <span class="badge-chip"><i>⭐</i> h-index {h_index}</span>
      </div>
    </div>
    """

    html_output = f"""
    <style>
    .ana-card, .ana-card * {{
      font-family: "Pretendard","Inter",-apple-system,BlinkMacSystemFont,"Segoe UI",
                   "Roboto","Apple SD Gothic Neo","Noto Sans KR",system-ui,sans-serif !important;
      letter-spacing:-0.2px; -webkit-font-smoothing:antialiased; -moz-osx-font-smoothing:grayscale;
      word-break:keep-all;
      text-align:left !important;
    }}
    .ana-card{{background:#fff;border:1px solid #E9E5FF;border-radius:16px;
      box-shadow:0 10px 24px rgba(105,0,184,.08);overflow:hidden}}
    .ana-head{{padding:14px 18px;background:linear-gradient(135deg,#cdb4ff 0%,#e9ddff 100%);
      border-bottom:1px solid #E3DBFF;display:flex;align-items:center;gap:12px;flex-wrap:wrap}}
    .ana-head .title{{font-weight:900;font-size:1.4rem;color:#111;letter-spacing:-.3px}}
    .ana-badges{{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}}
    .badge-chip{{display:inline-flex;align-items:center;gap:6px;padding:6px 10px;border-radius:999px;
      background:#ffffffcc;border:1px solid #D9D2FF;color:#1f1f1f;font-weight:800;font-size:.82rem}}
    .badge-chip i{{font-style:normal;opacity:.85}}
    .ana-body{{padding:18px 20px;max-height:100%;overflow:auto}}
    .ana-body p{{margin:.35rem 0;line-height:1.85;color:#2d2d2d;font-size:1.18rem}}
    .ana-sec{{position:relative;padding:14px 16px 14px 56px;border-radius:12px;border:none solid #EFEAFD;
      background:#ffffff;margin-bottom:18px;box-shadow:none}}
    .ana-sec::before{{content:none !important;position:absolute;left:14px;top:14px;width:30px;height:30px;border-radius:50%;
      display:inline-flex;align-items:center;justify-content:center;background:#6b5bd4;color:#fff;font-weight:900;
      font-size:.92rem;box-shadow:0 4px 8px rgba(107,91,212,.25)}}
    .ana-sec h5{{margin:0 0 8px;font-weight:900;font-size:1.12rem;color:#111}}
    .ana-sec h5::after{{content:"";display:block;width:72px;height:3px;border-radius:3px;
      background:linear-gradient(90deg,#6b5bd4,#b084f7);margin-top:6px;opacity:.35}}
    .ana-list{{margin:.35rem 0 .5rem .2rem;padding-left:1rem}}
    .ana-list li{{margin:.28rem 0;line-height:1.8;color:#2d2d2d;font-size:.98rem}}
    .ana-tldr{{padding:14px 16px;border-radius:12px;margin-top:12px;background:#FFF9EC;border:1px solid #FFE3B3}}
    .ana-tldr h5{{margin:0 0 6px;font-weight:900;color:#7a4a00}}
    .ana-tldr p{{margin:.25rem 0;color:#4a360d}}
    .ana-subhead{{ margin:.5rem 0 .2rem; font-weight:900; font-size:1.05rem; color:#111; letter-spacing:-.2px }}
    .ana-sec p strong {{
  display: block;
  font-size: 1.35rem;           /* 주제 제목 크기 크게 */
  font-weight: 900;
  color: #111;                  /* 검정색 강조 */
  margin-bottom: 6px;
  margin-top: 12px;
}}
    </style>

    <div class='ana-card'>
      {header_html}
      <div class='ana-body'>
        {sections_html}
        {tldr_html}
      </div>
    </div>
    """

    return JsonResponse({"analysis": html_output}, json_dumps_params={'ensure_ascii': False})
    
@login_required
def like_author(request, author_id):
    """저자 좋아요 추가 및 취소 기능"""
    user_id = request.session.get('user_id')  # ✅ 세션에서 user_id 가져오기

    if not user_id:
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)  # 🔥 로그인 필요 시 401 응답

    with connection.cursor() as cursor:
        # ✅ 1. 현재 사용자의 좋아요 여부 확인
        cursor.execute("""
            SELECT count FROM like_author WHERE user_id = %s AND author_id = %s
        """, [user_id, author_id])
        row = cursor.fetchone()  # 결과 가져오기

        if row is None:
            # ✅ 좋아요가 없는 경우 → 새로 추가
            cursor.execute("""
                INSERT INTO like_author (user_id, author_id, count) VALUES (%s, %s, 1)
            """, [user_id, author_id])
            like_count = 1  # 새로 추가된 경우 count = 1
            liked = True  # ✅ 좋아요 상태

        else:
            # ✅ 이미 좋아요를 눌렀다면 → 삭제 (좋아요 취소)
            cursor.execute("""
                DELETE FROM like_author WHERE user_id = %s AND author_id = %s
            """, [user_id, author_id])
            like_count = 0  # 좋아요 삭제 시 count = 0
            liked = False  # ✅ 좋아요 취소 상태

        # ✅ 최종 좋아요 개수 가져오기
        cursor.execute("""
            SELECT COUNT(*) FROM like_author WHERE author_id = %s
        """, [author_id])
        total_likes = cursor.fetchone()[0]  # 해당 저자의 총 좋아요 수 가져오기

    # ✅ JSON 응답 반환
    return JsonResponse({"liked": liked, "count": total_likes})


@csrf_exempt  
def save_paper(request):
    """ 논문 저장 (내 서재 담기) """
    if request.method == 'POST':
        user_id = request.session.get('user_id')
        if not user_id:
            return JsonResponse({'error': '로그인이 필요합니다.'}, status=401)

        try:
            data = json.loads(request.body)
            paper_ids = data.get('paper_ids', [])  

            if not paper_ids:
                return JsonResponse({'error': '논문 ID가 필요합니다.'}, status=400)

            with connection.cursor() as cursor:
                # ✅ 현재 유저가 저장한 논문 목록 조회
                cursor.execute("SELECT paper_id FROM savedpaper WHERE user_id = %s", [user_id])
                saved_paper_ids = {row[0] for row in cursor.fetchall()}  # ✅ Set으로 변환하여 중복 체크

                for paper_id in paper_ids:
                    if int(paper_id) in saved_paper_ids:  # ✅ 이미 저장된 논문인지 확인
                        #print(f"⚠ 논문 {paper_id}은(는) 이미 저장된 논문이므로 건너뜁니다.")
                        continue

                    cursor.execute("SELECT part_id FROM paper_part WHERE paper_id = %s", [paper_id])
                    part_ids = cursor.fetchall()

                    if not part_ids:
                        #print(f"⚠ 논문 {paper_id}에 연결된 파트 없음. 저장 건너뜀.")
                        continue

                    print(f"📌 Paper {paper_id} 관련 Part 조회 결과: {part_ids}")

                    for part_id in part_ids:
                        cursor.execute("""
                            INSERT INTO savedpaper (user_id, paper_id, part_id, saved_at)
                            VALUES (%s, %s, %s, NOW())
                        """, [user_id, paper_id, part_id[0]])

                        #print(f"✅ 저장 완료: User {user_id}, Paper {paper_id}, Part {part_id[0]}")

            connection.commit()  # ✅ 트랜잭션 커밋
            return JsonResponse({'message': '논문이 저장되었습니다.'})

        except Exception as e:
            print(f"❌ 오류 발생: {e}")
            return JsonResponse({'error': str(e)}, status=500)

    return JsonResponse({'error': '잘못된 요청입니다.'}, status=400)


def get_saved_papers(request):
    """현재 사용자가 저장한 논문 ID 목록을 반환하는 API"""
    user_id = request.session.get('user_id')
    if not user_id:
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT paper_id FROM savedpaper WHERE user_id = %s", [user_id])
            saved_paper_ids = [row[0] for row in cursor.fetchall()]  # 논문 ID 리스트 생성

        return JsonResponse({"saved_paper_ids": saved_paper_ids})

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return JsonResponse({"error": str(e)}, status=500)

#pdf저장
@csrf_exempt
def pdf_upload_view(request):
    """📄 JavaScript에서 생성된 PDF를 서버에 저장 (로그인 필요)"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "잘못된 요청"}, status=400)

    # ✅ 로그인하지 않은 사용자는 JSON 형식으로 403 응답 반환
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "로그인이 필요합니다."}, status=403)

    if "pdf" not in request.FILES:
        return JsonResponse({"success": False, "error": "파일이 없습니다."}, status=400)

    pdf_file = request.FILES["pdf"]
    content_type = request.POST.get("content_type", "unknown")
    object_title = request.POST.get("object_title", "unknown")  # ✅ JavaScript에서 `objectTitle` 받기

    user_id = request.user.id  # ✅ 로그인한 사용자 ID 가져오기

    # ✅ 저장할 경로 설정
    base_folder = os.path.join(settings.BASE_DIR, "main", "pdfs", str(user_id))
    category_folder = os.path.join(base_folder, content_type)
    os.makedirs(category_folder, exist_ok=True)

    # ✅ 파일명 설정 (author + eom의 경우 예외 처리)
    if content_type == "author" and object_title.lower() == "eom":
        file_name = "author_eom.pdf"
    else:
        file_name = f"{content_type}_{object_title}.pdf"

    file_path = os.path.join(category_folder, file_name)

    # ✅ PDF 저장
    with open(file_path, "wb") as f:
        for chunk in pdf_file.chunks():
            f.write(chunk)

    return JsonResponse({"success": True})  # ✅ 성공 메시지 필요 없음