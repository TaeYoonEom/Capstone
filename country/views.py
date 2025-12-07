from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.db.models import Count, Sum
from django.db import connection, transaction
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
import requests, re, json, os
from django.conf import settings
from main.models import (
    Country, Affiliation, Paper, Paper_affiliation, Paper_keyword,
    Paper_part, Paper_country, Author, SavedPaper, Paper_author
)
from django.core.paginator import Paginator

def country_page(request, country_id):
    """
    국가 상세 페이지를 렌더링하는 뷰
    - 기관, 저자, 논문, 키워드, 인용 통계 등을 context로 전달
    - 논문은 페이지네이션 처리됨
    """
    # 1) 국가 객체 조회
    country = get_object_or_404(Country, id=country_id)

    # 2) 해당 국가의 모든 기관 조회
    affiliations = Affiliation.objects.filter(country_id=country)

    # 3) 총 기관 수 계산
    total_affiliations = affiliations.count()

    # 4) 주요 기관 및 전체 기관 목록 설정
    main_affiliation = affiliations.first()
    all_affiliations = affiliations

    # 5) 해당 국가 소속 기관들의 저자 조회
    authors = Author.objects.filter(affiliation__in=affiliations.values_list('name', flat=True)).distinct()

    # 6) 총 저자 수 계산
    total_authors = authors.count()

    # 7) 상위 5명의 저자 목록 추출
    top_authors = authors[:5]
    all_authors = authors

    # 8) 해당 국가의 기관이 포함된 논문 ID 목록 조회
    paper_ids = Paper_affiliation.objects.filter(affiliation_id__in=affiliations).values_list('paper_id', flat=True).distinct()

    # 9) 논문 전체 목록 조회 (prefetch 사용)
    papers = Paper.objects.filter(id__in=paper_ids).prefetch_related(
        'author_papers__author_id',
        'keyword_papers__keyword_id',
        'part_papers__part_id'
    )

    # 10) 페이지네이션 설정 (10개씩 나눔)
    paginator = Paginator(papers, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # 11) 논문 총 개수
    publication_count = paginator.count

    # 12) 총 인용 수 및 평균 인용 수 계산
    total_citations = Paper.objects.filter(id__in=paper_ids).aggregate(Sum('citation'))['citation__sum'] or 0
    avg_citations = total_citations / publication_count if publication_count > 0 else 0

    # 13) 상위 3개의 키워드 추출
    keyword_counts = (
        Paper_keyword.objects.filter(paper_id__in=paper_ids)
        .values('keyword_id', 'keyword_id__keyword_name')
        .annotate(count=Count('keyword_id'))
        .order_by('-count')[:3]
    )
    keywords = [{'id': k['keyword_id'], 'keyword_name': k['keyword_id__keyword_name']} for k in keyword_counts]

    # 14) 가장 많이 사용된 논문 파트 추출
    part_counts = (
        Paper_part.objects.filter(paper_id__in=paper_ids)
        .values('part_id__name')
        .annotate(count=Count('part_id'))
        .order_by('-count')
    )
    main_part = part_counts.first()['part_id__name'] if part_counts.exists() else "정보 없음"

    # 15) 좋아요 수 및 사용자 좋아요 여부 조회
    user_id = request.session.get('user_id')
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM like_country WHERE country_id = %s", [country_id])
        like_count = cursor.fetchone()[0]

        if user_id:
            cursor.execute("SELECT COUNT(*) FROM like_country WHERE user_id = %s AND country_id = %s", [user_id, country_id])
            user_liked = cursor.fetchone()[0] > 0
        else:
            user_liked = False

    # 16) 템플릿 전달용 context 정의
    context = {
        'country': country,                          # 1) 국가 객체 정보
        'publication_count': publication_count,      # 2) 국가 소속 논문 수
        'total_citations': total_citations,          # 3) 총 인용 수
        'avg_citations': avg_citations,              # 4) 평균 인용 수
        'keywords': keywords,                        # 5) 상위 키워드 3개
        'main_part': main_part,                      # 6) 주요 연구 분야

        'like_count': like_count,                    # 7) 국가 좋아요 수
        'user_liked': user_liked,                    # 8) 현재 사용자의 좋아요 여부

        'top_authors': top_authors,                  # 9) 대표 저자 상위 5명
        'all_authors': all_authors,                  # 10) 전체 저자 목록

        'main_affiliation': main_affiliation,        # 11) 주요 기관 1개
        'all_affiliations': all_affiliations,        # 12) 전체 기관 목록
        'total_affiliations': total_affiliations,    # 13) 기관 총 개수
        'total_authors': total_authors,              # 14) 저자 총 수

        'page_obj': page_obj,                        # 15) 페이지네이션 객체

        "content_type": "country",                   # 16) PDF 다운로드용 구분값
        "object_id": country_id,                     # 17) PDF 저장용 객체 ID
        "page_title": country.name,                  # 18) 페이지 타이틀용 국가 이름
    }

    return render(request, 'country/country_page.html', context)


def country_analysis_api(request, country_id):
    """
    국가의 정량적 분석 데이터를 JSON 형식으로 반환
    - 연도별 논문 수, 파트별 논문 수, 키워드 빈도, 공동 연구 국가 등 포함
    """
    # 1) 국가 객체 조회
    country = get_object_or_404(Country, id=country_id)

    # 2) 국가 소속 기관 목록 (country_id 값이 있는 경우만)
    affiliations = Affiliation.objects.filter(country_id=country).exclude(country_id=None)

    # 3) 해당 국가의 논문 ID 목록 (중복 제거)
    paper_ids = list(Paper_affiliation.objects.filter(affiliation_id__in=affiliations)
                     .values_list('paper_id', flat=True).distinct())

    # 4) 전체 논문 수 계산
    total_papers = len(paper_ids)

    # 5) 연도별 논문 수 집계
    year_chart_data = (
        Paper.objects.filter(id__in=paper_ids)
        .values('year')
        .annotate(count=Count('id', distinct=True))
        .order_by('year')
    )
    year_chart_dict = {item['year']: item['count'] for item in year_chart_data}

    # 6) 파트별 논문 수 집계
    part_chart_data = (
        Paper_part.objects.filter(paper_id__in=paper_ids)
        .values('part_id__name')
        .annotate(count=Count('paper_id', distinct=True))
        .order_by('-count')
    )
    part_chart_dict = {item['part_id__name']: item['count'] for item in part_chart_data}

    # 7) 키워드 빈도 상위 10개 추출
    keyword_counts = (
        Paper_keyword.objects.filter(paper_id__in=paper_ids)
        .values('keyword_id__keyword_name')
        .annotate(count=Count('keyword_id', distinct=True))
        .order_by('-count')[:20]
    )
    keyword_dict = {item['keyword_id__keyword_name']: item['count'] for item in keyword_counts}

    # 8) 총 기관 수 계산
    total_affiliations = affiliations.count()

    # 9) 공동 연구 국가 추출 (기관 → 국가 ID 추적)
    related_affiliations = Paper_affiliation.objects.filter(paper_id__in=paper_ids).values_list('affiliation_id', flat=True).distinct()
    related_countries = Affiliation.objects.filter(id__in=related_affiliations)\
        .exclude(country_id=country).exclude(country_id=None)\
        .values('country_id').annotate(count=Count('id'))

    # 10) 공동 연구 국가 정보 정제
    network_data = []
    for item in related_countries:
        if Country.objects.filter(id=item["country_id"]).exists():
            related_country = Country.objects.get(id=item["country_id"])
            network_data.append({
                "id": related_country.id,
                "name": related_country.name,
                "count": item["count"]
            })

    # 11) JSON 데이터 응답 생성
    response_data = {
        "main_country": {
            "id": country.id,
            "name": country.name,
        },
        "year_chart_data": year_chart_dict,
        "part_chart_data": part_chart_dict,
        "keyword_data": keyword_dict,
        "total_affiliations": total_affiliations,
        "total_papers": total_papers,
        "network_data": network_data,
    }

    return JsonResponse(response_data)

OLLAMA_URL = ""

@login_required
def analyze_country(request, country_id):
    """
    국가의 연구 데이터를 기반으로 Ollama에 정성적 분석 요청
    - 기관 정성적 분석(analyze_affiliation)과 동일한 ana-card 스타일 / 섹션 구조 적용
    """
    country = get_object_or_404(Country, id=country_id)

    # -------- 1) 기본 데이터 수집 --------
    # 해당 국가에 속한 기관들
    affiliations = Affiliation.objects.filter(country_id=country)

    # 해당 국가에서 나온 논문 id
    paper_ids = list(
        Paper_affiliation.objects.filter(affiliation_id__in=affiliations)
        .values_list('paper_id', flat=True)
        .distinct()
    )
    publication_count = len(paper_ids)
    pubs = Paper.objects.filter(id__in=paper_ids)

    # 연도별 출판 수
    year_rows = (
        pubs.values('year')
        .annotate(cnt=Count('id'))
        .order_by('year')
    )
    year_chart = {r['year']: r['cnt'] for r in year_rows if r['year']}

    years = sorted(year_chart.keys())
    first_year = years[0] if years else None
    last_year = years[-1] if years else None
    active_span = (last_year - first_year + 1) if (first_year and last_year) else 0

    # 최근/과거 3년 비교로 추세값 계산
    def last_n_sum(n: int) -> int:
        if not years:
            return 0
        tail = [y for y in years if y >= (last_year - n + 1)]
        return sum(year_chart.get(y, 0) for y in tail)

    def prev_n_sum(n: int) -> int:
        if not years:
            return 0
        prev = [y for y in years if (last_year - 2 * n) < y < (last_year - n + 1)]
        return sum(year_chart.get(y, 0) for y in prev)

    recent3 = last_n_sum(3)
    prev3 = prev_n_sum(3)
    recent_ratio = (recent3 / publication_count) if publication_count else 0
    if recent3 > prev3 * 1.15:
        trend = "상승"
    elif recent3 < prev3 * 0.85:
        trend = "하락"
    else:
        trend = "보합"

    # 인용 지표
    citations = [c or 0 for c in pubs.values_list('citation', flat=True)]
    total_citations = sum(citations)
    avg_citations = (total_citations / publication_count) if publication_count else 0
    max_citation = max(citations) if citations else 0

    top_cited = pubs.filter(citation=max_citation).first() if max_citation > 0 else None
    if top_cited and top_cited.title:
        if len(top_cited.title) > 60:
            top_cited_title = top_cited.title[:60] + "…"
        else:
            top_cited_title = top_cited.title
    else:
        top_cited_title = "정보 없음"
    top_cited_paper = f"{top_cited_title} ({max_citation}회)" if max_citation else "정보 없음"

    # h-index 유사값
    def h_index_like(cites):
        arr = sorted(cites, reverse=True)
        h = 0
        for i, c in enumerate(arr, start=1):
            if c >= i:
                h = i
            else:
                break
        return h

    h_index = h_index_like(citations)

    # 함께 논문을 쓴 저자
    coauthor_qs = (
        Paper_author.objects.filter(paper_id__in=paper_ids)
        .values('author_id__name')
        .annotate(cnt=Count('paper_id', distinct=True))
        .order_by('-cnt')
    )
    coauthor_count = coauthor_qs.count()
    top_authors = [f"{r['author_id__name']}({r['cnt']})" for r in coauthor_qs[:5]]

    # 함께 논문을 쓴 다른 국가들 (Paper_country 기준)
    co_country_qs = (
        Paper_country.objects.filter(paper_id__in=paper_ids)
        .exclude(country_id=country)
        .values('country_id__name')
        .annotate(cnt=Count('paper_id', distinct=True))
        .order_by('-cnt')
    )
    co_country_count = co_country_qs.count()
    top_countries = [f"{r['country_id__name']}({r['cnt']})" for r in co_country_qs[:5]]

    # 파트 / 키워드
    part_rows = (
        Paper_part.objects.filter(paper_id__in=paper_ids)
        .values('part_id__name')
        .annotate(cnt=Count('part_id'))
        .order_by('-cnt')
    )
    main_part = part_rows.first()['part_id__name'] if part_rows.exists() else "정보 없음"

    kw_rows = (
        Paper_keyword.objects.filter(paper_id__in=paper_ids)
        .values('keyword_id__keyword_name')
        .annotate(cnt=Count('keyword_id'))
        .order_by('-cnt')
    )
    top_keywords = [f"{r['keyword_id__keyword_name']}({r['cnt']})" for r in kw_rows[:10]]
    keyword_total_unique = kw_rows.count()

    # 초기 vs 최근 키워드 (3년 구간 기준)
    early_ids = []
    recent_ids = []
    if first_year and last_year and last_year - first_year >= 3:
        early_cut = first_year + 2
        recent_cut = last_year - 2
        early_ids = list(pubs.filter(year__lte=early_cut).values_list('id', flat=True))
        recent_ids = list(pubs.filter(year__gte=recent_cut).values_list('id', flat=True))

    early_kw_qs = (
        Paper_keyword.objects.filter(paper_id__in=early_ids)
        .values('keyword_id__keyword_name')
        .annotate(cnt=Count('keyword_id'))
        .order_by('-cnt')[:5]
    ) if early_ids else []
    recent_kw_qs = (
        Paper_keyword.objects.filter(paper_id__in=recent_ids)
        .values('keyword_id__keyword_name')
        .annotate(cnt=Count('keyword_id'))
        .order_by('-cnt')[:5]
    ) if recent_ids else []

    early_kw = ", ".join([k['keyword_id__keyword_name'] for k in early_kw_qs]) if early_kw_qs else "정보 부족"
    recent_kw = ", ".join([k['keyword_id__keyword_name'] for k in recent_kw_qs]) if recent_kw_qs else "정보 부족"

    # -------- 2) 프롬프트 생성 (기관 버전과 동일 포맷) --------
    prompt = f"""
당신은 국가 연구 전략 컨설턴트입니다. 아래 '정량 지표'를 바탕으로
국가 '{country.name}'의 연구 성과와 전략을 한국어로 분석해 주세요.

[정량 지표]
- 활동기간: {first_year} ~ {last_year} (약 {active_span}년), 최근3년 비중: {recent_ratio:.0%}, 추세: {trend}
- 총 출판수: {publication_count}편, 총 인용수: {total_citations}회, 평균: {avg_citations:.2f}, 최고: {max_citation}, h-index 유사값: {h_index}
- 최고 인용 논문: {top_cited_paper}
- 함께 논문을 쓴 저자 수: {coauthor_count}명, 상위 저자: {', '.join(top_authors)}
- 함께 논문을 쓴 외국/타국 수: {co_country_count}개국, 상위 협력 국가: {', '.join(top_countries)}
- 대표 파트(연구 분야): {main_part}
- 키워드 고유 개수: {keyword_total_unique}
- 상위 키워드 TOP10: {', '.join(top_keywords)}
- 초기 3년 키워드: {early_kw} / 최근 3년 키워드: {recent_kw}
- 연도별 출판 수: {year_chart}

[작성 형식]
1. 핵심 연구 분야 및 트렌드
2. 키워드 연관성 및 연구 방향
3. 협력 국가와의 협력 현황
4. 연구 영향력과 향후 확장 가능성
5. 전략 인사이트 — (a) 단기 6개월, (b) 중기 12개월 실행 항목을 ✔ 체크리스트로
6. 국제 협력/펀딩·데이터 전략 — 타깃 국가, 유망 키워드, 추천 데이터셋·플랫폼
7. 출판/국제 학회 전략 — 적합한 학회/저널과 이유
요약(TL;DR): 핵심 3줄.

반드시 한국어로만, 과장 없이 명료하게, 마크다운 기호 없이 순수 텍스트로 작성하세요.
""".strip()

    # -------- 3) Ollama 호출 --------
    try:
        res = requests.post(
            OLLAMA_URL,
            json={"model": "gemma", "prompt": prompt, "stream": False},
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        j = res.json()
        if "response" not in j:
            return JsonResponse({"error": "Ollama 응답에 'response'가 없습니다."}, status=500)

        raw = j["response"].strip()
        lines = raw.splitlines()
        if lines and lines[0].lstrip().startswith("#"):
            lines = lines[1:]
        raw = "\n".join(lines).lstrip()
        # markdown 굵게 → <strong>
        raw = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', raw)
    except Exception as e:
        return JsonResponse({"error": f"Ollama 호출 실패: {e}"}, status=500)

    # -------- 4) 섹션 나누기 / TL;DR 추출 (기관과 동일) --------
    def build_sections(text: str) -> str:
        sections = []
        # "1. ..." 으로 시작하는 구간 단위로 자르기
        chunks = re.split(r'\n\s*(?=\d+\.\s)', text)
        for c in chunks:
            m = re.match(r'(\d+)\.\s*([^\n]+)\n(.*)', c, flags=re.S)
            if not m:
                # 맨 위에 '## 국가 ~ 분석' 같은 제목이 와도 여기서 걸러져서 버려짐
                continue
            no, title, body = m.groups()
            body_lines = [l.strip() for l in body.split('\n') if l.strip()]

            # 5번(전략 인사이트)은 체크리스트 구조
            if no == '5':
                html_parts, bucket = [], []
                for line in body_lines:
                    # (a), a), (b), b) 같은 소제목이면 새 구간
                    if re.match(r'^\(?[ab]\)', line, flags=re.I):
                        if bucket:
                            html_parts.append(
                                '<ul class="ana-list">' +
                                ''.join(f'<li>✔ {x}</li>' for x in bucket) +
                                '</ul>'
                            )
                            bucket = []
                        html_parts.append(f"<p class='ana-subhead'>{line}</p>")
                    else:
                        bucket.append(line)
                if bucket:
                    html_parts.append(
                        '<ul class="ana-list">' +
                        ''.join(f'<li>✔ {x}</li>' for x in bucket) +
                        '</ul>'
                    )
                body_html = ''.join(html_parts)
            else:
                body_html = ''.join(f"<p>{l}</p>" for l in body_lines)

            sections.append(f"<div class='ana-sec' data-no='{no}'>{body_html}</div>")

        if sections:
            return ''.join(sections)

        # 위 패턴이 안 맞으면 그냥 전체를 하나의 섹션으로
        body_html = ''.join(f"<p>{l.strip()}</p>" for l in text.split('\n') if l.strip())
        return f"<div class='ana-sec'>{body_html}</div>"

    # TL;DR 추출
    tldr_html = ""
    m = re.search(r'(요약|TL;DR)\s*[:：]?\s*(.*)', raw, flags=re.I | re.S)
    if m:
        tldr_text = m.group(2).strip()
        tldr_lines = [l.strip('- •').strip() for l in tldr_text.split('\n') if l.strip()]
        tldr_html = (
            "<div class='ana-tldr'><h5>요약 (TL;DR)</h5>" +
            "".join(f"<p>• {l}</p>" for l in tldr_lines[:3]) +
            "</div>"
        )

    sections_html = build_sections(raw)

    # -------- 5) 헤더 HTML (국가용) --------
    header_html = f"""
    <div class="ana-head">
      <div class="title">{country.name} 국가 정성적 분석</div>
      <div class="ana-badges">
        <span class="badge-chip"><i>🌍</i> 활동 {active_span}년</span>
        <span class="badge-chip"><i>📚</i> {publication_count}편</span>
        <span class="badge-chip"><i>⭐</i> h-index {h_index}</span>
      </div>
    </div>
    """

    # -------- 6) CSS + 전체 카드 HTML --------
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
    .ana-body p{{margin:.35rem 0;line-height:1.85;color:#2d2d2d;font-size:1.05rem}}
    .ana-sec{{position:relative;padding:14px 16px 14px 56px;border-radius:12px;border:none;
      background:#ffffff;margin-bottom:18px;box-shadow:none}}
    .ana-sec::before{{content:none !important}}
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
      display:block;font-size:1.25rem;font-weight:900;color:#111;margin-bottom:6px;margin-top:12px;
    }}
    </style>

    <div class="ana-card">
      {header_html}
      <div class="ana-body">
        {sections_html}
        {tldr_html}
      </div>
    </div>
    """

    return JsonResponse({"analysis": html_output}, json_dumps_params={'ensure_ascii': False})

@login_required
def like_country(request, country_id):
    """국가 좋아요 추가 및 취소 기능"""
    user_id = request.session.get('user_id')  # ✅ 세션에서 user_id 가져오기

    if not user_id:
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)  # 🔥 로그인 필요 시 401 응답

    with connection.cursor() as cursor:
        # ✅ 1. 현재 사용자의 좋아요 여부 확인
        cursor.execute("""
            SELECT count FROM like_country WHERE user_id = %s AND country_id = %s
        """, [user_id, country_id])
        row = cursor.fetchone()  # 결과 가져오기

        if row is None:
            # ✅ 좋아요가 없는 경우 → 새로 추가
            cursor.execute("""
                INSERT INTO like_country (user_id, country_id, count) VALUES (%s, %s, 1)
            """, [user_id, country_id])
            like_count = 1  # 새로 추가된 경우 count = 1
            liked = True  # ✅ 좋아요 상태

        else:
            # ✅ 이미 좋아요를 눌렀다면 → 삭제 (좋아요 취소)
            cursor.execute("""
                DELETE FROM like_country WHERE user_id = %s AND country_id = %s
            """, [user_id, country_id])
            like_count = 0  # 좋아요 삭제 시 count = 0
            liked = False  # ✅ 좋아요 취소 상태

        # ✅ 최종 좋아요 개수 가져오기
        cursor.execute("""
            SELECT COUNT(*) FROM like_country WHERE country_id = %s
        """, [country_id])
        total_likes = cursor.fetchone()[0]  # 해당 국가의 총 좋아요 수 가져오기

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