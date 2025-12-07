from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.db.models import Count, Sum
from django.core.paginator import Paginator
from django.db import connection
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.conf import settings
import os, requests, json, re

from main.models import Affiliation, Paper, Paper_affiliation, Paper_keyword, Paper_part, Paper_author, Like_Affiliation


# ✅ 기관 상세 페이지
def affiliation_page(request, affiliation_id):
    affiliation = get_object_or_404(Affiliation, id=affiliation_id)

    unique_paper_ids = set(
        Paper_affiliation.objects.filter(affiliation_id=affiliation)
        .values_list('paper_id', flat=True)
    )
    publication_count = len(unique_paper_ids)
    papers = Paper.objects.filter(id__in=unique_paper_ids).order_by('-year')
    paginator = Paginator(papers, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    total_citations = Paper.objects.filter(id__in=unique_paper_ids).aggregate(Sum('citation'))['citation__sum'] or 0
    avg_citations = total_citations / publication_count if publication_count > 0 else 0

    keyword_counts = (
        Paper_keyword.objects.filter(paper_id__in=unique_paper_ids)
        .values('keyword_id', 'keyword_id__keyword_name')
        .annotate(count=Count('keyword_id'))
        .order_by('-count')[:3]
    )
    keywords = [{'id': k['keyword_id'], 'keyword_name': k['keyword_id__keyword_name']} for k in keyword_counts]

    part_counts = (
        Paper_part.objects.filter(paper_id__in=unique_paper_ids)
        .values('part_id__name')
        .annotate(count=Count('part_id'))
        .order_by('-count')
    )
    main_part = part_counts.first()['part_id__name'] if part_counts.exists() else "정보 없음"

    country = affiliation.country_id.name if affiliation.country_id else "정보 없음"
    country_id = affiliation.country_id.id if affiliation.country_id else None

    user_id = request.session.get('user_id')
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM like_affiliation WHERE affiliation_id = %s", [affiliation_id])
        like_count = cursor.fetchone()[0]

        if user_id:
            cursor.execute("SELECT COUNT(*) FROM like_affiliation WHERE user_id = %s AND affiliation_id = %s", [user_id, affiliation_id])
            user_liked = cursor.fetchone()[0] > 0
        else:
            user_liked = False

    author_count = (
        Paper_author.objects.filter(paper_id__in=unique_paper_ids)
        .values('author_id')
        .distinct()
        .count()
    )

    author_citations = (
        Paper_author.objects.filter(paper_id__in=unique_paper_ids)
        .exclude(author_id=None)
        .values('author_id', 'author_id__name')
        .annotate(total_citations=Sum('paper_id__citation'))
        .order_by('-total_citations')
    )
    top_authors = author_citations[:5]
    all_authors = author_citations

    context = {
        "affiliation": affiliation,
        "publication_count": publication_count,
        "total_citations": total_citations,
        "avg_citations": avg_citations,
        "keywords": keywords,
        "main_part": main_part,
        "country": country,
        "country_id": country_id,
        "author_count": author_count,
        "top_authors": top_authors,
        "all_authors": all_authors,
        "like_count": like_count,
        "user_liked": user_liked,
        "page_obj": page_obj,
        "page_range": range(1, paginator.num_pages + 1),
        "content_type": "affiliation",
        "object_id": affiliation_id,
        "page_title": affiliation.name,
    }
    return render(request, 'affiliation/affiliation_page.html', context)


# ✅ 기관 정량적 분석 API
def affiliation_analysis_api(request, affiliation_id):
    affiliation = get_object_or_404(Affiliation, id=affiliation_id)
    paper_ids = Paper_affiliation.objects.filter(affiliation_id=affiliation).values_list('paper_id', flat=True)

    year_chart_data = (
        Paper.objects.filter(id__in=paper_ids)
        .values('year')
        .annotate(count=Count('id'))
        .order_by('year')
    )
    year_chart_dict = {item['year']: item['count'] for item in year_chart_data}

    part_chart_data = (
        Paper_part.objects.filter(paper_id__in=paper_ids)
        .values('part_id__name')
        .annotate(count=Count('part_id'))
        .order_by('-count')
    )
    part_chart_dict = {item['part_id__name']: item['count'] for item in part_chart_data}

    keyword_counts = (
        Paper_keyword.objects.filter(paper_id__in=paper_ids)
        .values('keyword_id__keyword_name')
        .annotate(count=Count('keyword_id'))
        .order_by('-count')[:20]
    )
    keyword_dict = {item['keyword_id__keyword_name']: item['count'] for item in keyword_counts}

    co_affiliations = (
        Paper_affiliation.objects.filter(paper_id__in=paper_ids)
        .exclude(affiliation_id=affiliation)
        .values('affiliation_id', 'affiliation_id__name')
        .annotate(count=Count('paper_id'))
        .order_by('-count')[:10]
    )
    network_data = [
        {"id": item["affiliation_id"], "name": item["affiliation_id__name"], "count": item["count"]}
        for item in co_affiliations
    ]

    response_data = {
        "year_chart_data": year_chart_dict,
        "part_chart_data": part_chart_dict,
        "keyword_data": keyword_dict,
        "network_data": network_data,
    }
    return JsonResponse(response_data)


# ✅ 좋아요 토글 기능
@login_required
def like_affiliation(request, affiliation_id):
    user_id = request.session.get('user_id')
    if not user_id:
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)

    with connection.cursor() as cursor:
        cursor.execute("SELECT count FROM like_affiliation WHERE user_id = %s AND affiliation_id = %s", [user_id, affiliation_id])
        row = cursor.fetchone()

        if row is None:
            cursor.execute("INSERT INTO like_affiliation (user_id, affiliation_id, count) VALUES (%s, %s, 1)", [user_id, affiliation_id])
            liked = True
        else:
            cursor.execute("DELETE FROM like_affiliation WHERE user_id = %s AND affiliation_id = %s", [user_id, affiliation_id])
            liked = False

        cursor.execute("SELECT COUNT(*) FROM like_affiliation WHERE affiliation_id = %s", [affiliation_id])
        total_likes = cursor.fetchone()[0]

    return JsonResponse({"liked": liked, "count": total_likes})


# ✅ Ollama 주소
OLLAMA_URL = ""


# ✅ 정성적 분석 API (Ollama) — ★ 여기만 기존 코드에서 변경된 부분
@login_required
def analyze_affiliation(request, affiliation_id):
    affiliation = get_object_or_404(Affiliation, id=affiliation_id)

    # -------- 1) 기본 데이터 수집 --------
    paper_ids = list(
        Paper_affiliation.objects.filter(affiliation_id=affiliation)
        .values_list('paper_id', flat=True)
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

    # 최근/과거 3년 비교
    def last_n_sum(n):
        if not years:
            return 0
        tail = [y for y in years if y >= (last_year - n + 1)]
        return sum(year_chart.get(y, 0) for y in tail)

    def prev_n_sum(n):
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

    # 함께 일한 저자
    coauthor_qs = (
        Paper_author.objects.filter(paper_id__in=paper_ids)
        .values('author_id__name')
        .annotate(cnt=Count('paper_id', distinct=True))
        .order_by('-cnt')
    )
    coauthor_count = coauthor_qs.count()
    top_authors = [f"{r['author_id__name']}({r['cnt']})" for r in coauthor_qs[:5]]

    # 함께 일한 기관
    coaff_qs = (
        Paper_affiliation.objects.filter(paper_id__in=paper_ids)
        .exclude(affiliation_id=affiliation)
        .values('affiliation_id__name')
        .annotate(cnt=Count('paper_id', distinct=True))
        .order_by('-cnt')
    )
    coaff_count = coaff_qs.count()
    top_affs = [f"{r['affiliation_id__name']}({r['cnt']})" for r in coaff_qs[:5]]

    # 국가
    country = affiliation.country_id.name if affiliation.country_id else "정보 없음"

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

    # 초기 vs 최근 키워드
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

    # -------- 2) 프롬프트 생성 --------
    prompt = f"""
당신은 연구기관 전략 컨설턴트입니다. 아래 '정량 지표'를 바탕으로
기관 '{affiliation.name}'의 연구 성과와 전략을 한국어로 분석해 주세요.

[정량 지표]
- 국가: {country}
- 활동기간: {first_year} ~ {last_year} (약 {active_span}년), 최근3년 비중: {recent_ratio:.0%}, 추세: {trend}
- 총 출판수: {publication_count}편, 총 인용수: {total_citations}회, 평균: {avg_citations:.2f}, 최고: {max_citation}, h-index 유사값: {h_index}
- 최고 인용 논문: {top_cited_paper}
- 함께 논문을 쓴 저자 수: {coauthor_count}명, 상위 저자: {', '.join(top_authors)}
- 함께 논문을 쓴 외부 기관 수: {coaff_count}곳, 상위 협력기관: {', '.join(top_affs)}
- 대표 파트: {main_part}
- 키워드 고유 개수: {keyword_total_unique}
- 상위 키워드 TOP10: {', '.join(top_keywords)}
- 초기 3년 키워드: {early_kw} / 최근 3년 키워드: {recent_kw}
- 연도별 출판 수: {year_chart}

[작성 형식]
1. 핵심 연구 분야 및 트렌드
2. 키워드 연관성 및 연구 방향
3. 협력 기관과의 협력 현황
4. 연구 영향력과 향후 확장 가능성
5. 전략 인사이트 — (a) 단기 6개월, (b) 중기 12개월 실행 항목을 ✔ 체크리스트로
6. 협력/펀딩·데이터 전략 — 타깃 기관, 유망 키워드, 추천 데이터셋·플랫폼
7. 출판 전략 — 적합한 학회/저널과 이유
요약(TL;DR): 핵심 3줄.

반드시 한국어로만, 과장 없이 명료하게, 마크다운 기호 없이 순수 텍스트로 작성하세요.
""".strip()

    # -------- 3) Ollama 호출 --------
    try:
        res = requests.post(
            OLLAMA_URL,
            json={"model": "gemma", "prompt": prompt, "stream": False},
            headers={"Content-Type": "application/json"},
            timeout=120
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

    # -------- 4) 섹션 나누기 / TL;DR 추출 --------
    def build_sections(text: str) -> str:
        sections = []
        # "1. ..." 으로 시작하는 구간 단위로 자르기
        chunks = re.split(r'\n\s*(?=\d+\.\s)', text)
        for c in chunks:
            m = re.match(r'(\d+)\.\s*([^\n]+)\n(.*)', c, flags=re.S)
            if not m:
                continue
            no, title, body = m.groups()
            body_lines = [l.strip() for l in body.split('\n') if l.strip()]

            # 5번(전략 인사이트)은 체크리스트 구조로
            if no == '5':
                html_parts, bucket = [], []
                for line in body_lines:
                    # (a), a), (b), b) 같은 소제목이면
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
        return f"<div {body_html}</div>"

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

    # 헤더 영역
    header_html = f"""
    <div class="ana-head">
      <div class="title">{affiliation.name} 기관 정성적 분석</div>
      <div class="ana-badges">
        <span class="badge-chip"><i>📍</i> {country}</span>
        <span class="badge-chip"><i>📅</i> 활동 {active_span}년</span>
        <span class="badge-chip"><i>📚</i> {publication_count}편</span>
        <span class="badge-chip"><i>⭐</i> h-index {h_index}</span>
      </div>
    </div>
    """

    # CSS + 본문 HTML
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
