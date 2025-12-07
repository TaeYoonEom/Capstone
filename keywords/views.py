from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
import json
import re
import requests
from django.http import JsonResponse, Http404
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.db import connection, transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from main.models import Keyword
import os  # ✅ PDF 저장 경로 관련
from django.conf import settings  # ✅ settings.BASE_DIR 사용

from .utils import get_keyword_info


def keyword_page(request, keyword_id):
    """키워드 상세 페이지 뷰 함수"""

    # 1) 키워드 ID에 해당하는 이름을 DB에서 가져옴
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, keyword_name FROM keyword WHERE id = %s LIMIT 1", [keyword_id])
        keyword = cursor.fetchone()

    if not keyword:
        return render(request, '404.html', status=404)

    keyword_id_from_db, keyword_name = keyword

    # 2) Wikipedia API를 통해 키워드 정의 및 카테고리 정보 가져오기
    keyword_definition, keyword_categories = get_keyword_info(keyword_name)
    
    # 3) 연도별 키워드 출현 횟수 계산 (2019~2024)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT p.year, COUNT(*) as count
            FROM paper p
            JOIN paper_keyword pk ON p.id = pk.paper_id
            WHERE pk.keyword_id = %s AND p.year BETWEEN 2019 AND 2024
            GROUP BY p.year
            ORDER BY count DESC;
        """, [keyword_id])
        year_data = cursor.fetchall()

    year_counts = {str(year): 0 for year in range(2019, 2025)}
    for row in year_data:
        if row[0] is not None:
            year_counts[str(row[0])] = int(row[1])

    # 4) 출현 빈도가 가장 높은 연도를 선택
    main_year = max(year_counts, key=year_counts.get) if year_data else "N/A"

    # 5) 해당 키워드와 논문에서 함께 등장한 연관 키워드 정보 수집
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT k.id, k.keyword_name, COUNT(pk2.paper_id) AS frequency
            FROM paper_keyword pk1
            JOIN paper_keyword pk2 ON pk1.paper_id = pk2.paper_id
            JOIN keyword k ON pk2.keyword_id = k.id
            WHERE pk1.keyword_id = %s AND pk2.keyword_id != %s
            GROUP BY k.id, k.keyword_name
            ORDER BY frequency DESC
            LIMIT 5;
        """, [keyword_id, keyword_id])
        related_keywords = cursor.fetchall()

    related_keywords_json = [
        {"id": kw[0], "name": kw[1], "frequency": kw[2]} for kw in related_keywords
    ]

    main_related_keyword = related_keywords[0][1] if related_keywords else "N/A"

    # 6) 가장 많이 등장한 논문 파트 정보 추출
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT p.name
            FROM paper_keyword pk
            JOIN paper_part pp ON pk.paper_id = pp.paper_id
            JOIN part p ON pp.part_id = p.id
            WHERE pk.keyword_id = %s
            GROUP BY p.name
            ORDER BY COUNT(pp.part_id) DESC
            LIMIT 1;
        """, [keyword_id])
        main_part = cursor.fetchone()

    main_part = main_part[0] if main_part else "N/A"

    # 7) 키워드가 포함된 논문 목록 조회
    papers_query = """
        SELECT p.id, p.title, p.year, p.published_in
        FROM paper p
        JOIN paper_keyword pk ON p.id = pk.paper_id
        WHERE pk.keyword_id = %s
        ORDER BY p.year DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(papers_query, [keyword_id])
        papers = cursor.fetchall()

    paper_ids = [p[0] for p in papers]

    # 8) 논문에 연결된 저자, 키워드, 파트 정보를 dict 형태로 수집
    authors_dict = {}
    keywords_dict = {}
    parts_dict = {}

    original_keyword_id = keyword_id  # keyword_id 보호

    if paper_ids:
        # 8-1) 저자 정보
        author_query = """
            SELECT pa.paper_id, a.id, a.name
            FROM paper_author pa
            JOIN author a ON pa.author_id = a.id
            WHERE pa.paper_id IN %s
        """
        with connection.cursor() as cursor:
            cursor.execute(author_query, [tuple(paper_ids)])
            authors_data = cursor.fetchall()
            for paper_id, author_id, author_name in authors_data:
                if paper_id not in authors_dict:
                    authors_dict[paper_id] = []
                authors_dict[paper_id].append({"id": author_id, "name": author_name})

        # 8-2) 키워드 정보
        keyword_query = """
            SELECT pk.paper_id, k.id, k.keyword_name
            FROM paper_keyword pk
            JOIN keyword k ON pk.keyword_id = k.id
            WHERE pk.paper_id IN %s
        """
        with connection.cursor() as cursor:
            cursor.execute(keyword_query, [tuple(paper_ids)])
            keywords_data = cursor.fetchall()
            for paper_id, related_keyword_id, related_keyword_name in keywords_data:
                if paper_id not in keywords_dict:
                    keywords_dict[paper_id] = []
                keywords_dict[paper_id].append({"id": related_keyword_id, "name": related_keyword_name})

        # 8-3) 파트 정보
        part_query = """
            SELECT pp.paper_id, p.id, p.name
            FROM paper_part pp
            JOIN part p ON pp.part_id = p.id
            WHERE pp.paper_id IN %s
        """
        with connection.cursor() as cursor:
            cursor.execute(part_query, [tuple(paper_ids)])
            parts_data = cursor.fetchall()
            for paper_id, part_id, part_name in parts_data:
                if paper_id not in parts_dict:
                    parts_dict[paper_id] = []
                parts_dict[paper_id].append({"id": part_id, "name": part_name})

    keyword_id = original_keyword_id  # keyword_id 복원

    # 9) 논문 리스트 생성
    paper_list = [
        {
            "id": p[0],
            "title": p[1],
            "year": p[2],
            "published_in": p[3],
            "authors": authors_dict.get(p[0], []),
            "keywords": keywords_dict.get(p[0], []),
            "parts": parts_dict.get(p[0], [])
        }
        for p in papers
    ]

    # 10) 페이지네이션 처리
    paginator = Paginator(paper_list, 10)
    page_number = request.GET.get('page')

    try:
        page_obj = paginator.page(page_number)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    # 11) 좋아요 수 및 사용자 좋아요 여부 확인
    user_id = request.session.get('user_id')
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM like_keyword WHERE keyword_id = %s", [keyword_id])
        like_count = cursor.fetchone()[0]

        if user_id:
            cursor.execute("SELECT COUNT(*) FROM like_keyword WHERE user_id = %s AND keyword_id = %s", [user_id, keyword_id])
            user_liked = cursor.fetchone()[0] > 0
        else:
            user_liked = False

    # 12) 최종 context: 템플릿에 전달할 데이터 구성
    context = {
        "keyword_id": keyword_id,  # 키워드 고유 ID
        "keyword_name": keyword_name,  # 키워드 이름
        "keyword_definition": keyword_definition,  # Wikipedia 정의
        "keyword_categories": keyword_categories,  # Wikipedia 카테고리
        "year_counts_json": json.dumps(year_counts),  # 연도별 출현 빈도 (차트용)
        "related_keywords_json": json.dumps(related_keywords_json),  # 연관 키워드 정보 (네트워크용)
        "main_part": main_part,  # 가장 자주 등장한 논문 파트
        "main_year": main_year,  # 가장 많이 출현한 연도
        "main_related_keyword": main_related_keyword,  # 주 연관 키워드
        "page_obj": page_obj,  # 페이징된 논문 리스트
        "like_count": like_count,  # 좋아요 수
        "user_liked": user_liked,  # 현재 사용자가 좋아요 눌렀는지 여부
        "content_type": "keyword",  # PDF 저장용 컨텐츠 타입
        "object_id": keyword_id,  # PDF 저장용 키워드 ID
        "page_title": keyword_name,  # 페이지 제목용 키워드명
    }
    
    return render(request, 'keywords/keyword_page.html', context)


@login_required
def like_keyword(request, keyword_id):
    """키워드 좋아요 추가 및 취소 기능"""
    user_id = request.session.get('user_id')  # ✅ 세션에서 user_id 가져오기

    if not user_id:
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)  # 🔥 로그인 필요 시 401 응답

    with connection.cursor() as cursor:
        # ✅ 1. 현재 사용자의 좋아요 여부 확인
        cursor.execute("""
            SELECT count FROM like_keyword WHERE user_id = %s AND keyword_id = %s
        """, [user_id, keyword_id])
        row = cursor.fetchone()  # 결과 가져오기

        if row is None:
            # ✅ 좋아요가 없는 경우 → 새로 추가
            cursor.execute("""
                INSERT INTO like_keyword (user_id, keyword_id, count) VALUES (%s, %s, 1)
            """, [user_id, keyword_id])
            like_count = 1  # 새로 추가된 경우 count = 1
            liked = True  # ✅ 좋아요 상태

        else:
            # ✅ 이미 좋아요를 눌렀다면 → 삭제 (좋아요 취소)
            cursor.execute("""
                DELETE FROM like_keyword WHERE user_id = %s AND keyword_id = %s
            """, [user_id, keyword_id])
            like_count = 0  # 좋아요 삭제 시 count = 0
            liked = False  # ✅ 좋아요 취소 상태

        # ✅ 최종 좋아요 개수 가져오기
        cursor.execute("""
            SELECT COUNT(*) FROM like_keyword WHERE keyword_id = %s
        """, [keyword_id])
        total_likes = cursor.fetchone()[0]  # 해당 키워드의 총 좋아요 수 가져오기

    # ✅ JSON 응답 반환
    return JsonResponse({"liked": liked, "count": total_likes})


# 올라마 정성적 분석을 위한 고귀한 희생
OLLAMA_URL = ""

@login_required
def analyze_keyword(request, keyword_id):
    """키워드 데이터를 기반으로 Ollama에 정성적 분석 요청 (기관/국가와 동일 카드형 디자인)"""

    keyword = get_object_or_404(Keyword, id=keyword_id)

    # 1) 네트워크 차트와 동일한 연관 키워드 조회
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT k.id, k.keyword_name, COUNT(pk2.paper_id) AS frequency
            FROM paper_keyword pk1
            JOIN paper_keyword pk2 ON pk1.paper_id = pk2.paper_id
            JOIN keyword k ON pk2.keyword_id = k.id
            WHERE pk1.keyword_id = %s AND pk2.keyword_id != %s
            GROUP BY k.id, k.keyword_name
            ORDER BY frequency DESC
            LIMIT 5;
        """, [keyword_id, keyword_id])
        related_keywords = cursor.fetchall()

    # 2) 키워드 설명 목록 생성 (프롬프트용)
    keyword_definitions = []
    for kw in related_keywords:
        keyword_definitions.append(
            f"<li><strong>{kw[1]}</strong>: {kw[2]}개의 논문에서 함께 등장한 연관 키워드</li>"
        )

    # 3) Ollama 프롬프트 구성
    prompt = (
        f"'{keyword.keyword_name}' 키워드는 연구 분야에서 중요한 개념입니다. "
        f"이 키워드가 의미하는 바를 분석하고, 연관 키워드들과 어떤 의미적 관계를 가지는지 설명하세요.\n\n"
        f"연관 키워드 및 연구 빈도:\n"
        f"<ul>{''.join(keyword_definitions)}</ul>\n\n"
        f"<h3>분석할 내용:</h3>\n"
        f"- <strong>{keyword.keyword_name}</strong> 키워드의 연구 분야에서의 의미\n"
        f"- 각 연관 키워드들의 일반적인 의미 및 <strong>{keyword.keyword_name}</strong>과의 관계\n"
        f"- <strong>{keyword.keyword_name}</strong> 연구가 발전할 가능성과 향후 연구 방향\n"
        f"객관적이고 논리적으로 분석하여 문단 형식으로 설명하세요."
    )

    ollama_data = {
        "model": "gemma",
        "prompt": prompt,
        "stream": False
    }

    headers = {'Content-Type': 'application/json'}

    try:
        # 4) Ollama API 호출
        response = requests.post(OLLAMA_URL, json=ollama_data, headers=headers)
        response_data = response.json()

        if "response" not in response_data:
            return JsonResponse({"error": "Ollama 응답에 'response' 항목이 없습니다."}, status=500)

        raw = response_data["response"]

        # ===== 마크다운을 HTML로 변환 (기본 포맷) =====
        formatted = raw.replace("**", "<strong>")
        formatted = re.sub(
            r'##\s*(.+)',
            r'<h5 style="font-size:1.05rem; font-weight:700; color:#111827; margin-top:14px; margin-bottom:8px;">\1</h5>',
            formatted
        )
        paragraphs = formatted.split('\n')
        formatted_paragraphs = ''.join(
            f"<p style='margin-bottom:8px; color:#111827;'>{line}</p>" 
            for line in paragraphs if line.strip()
        )

        # ===== 기관/국가 상세페이지와 유사한 카드형 디자인 적용 =====
        total_related = len(related_keywords)
        total_freq = sum(int(kw[2]) for kw in related_keywords) if related_keywords else 0

        html_output = f"""
        <div style="
            border-radius:16px;
            border:1px solid #E5E7EB;
            background:#FFFFFF;
            box-shadow:0 14px 35px rgba(15,23,42,0.10);
            overflow:hidden;
        ">
          <!-- 상단 헤더 바 -->
          <div style="
              background:linear-gradient(135deg,#6900B8,#A855F7);
              color:#ffffff;
              padding:14px 20px;
              display:flex;
              align-items:center;
              justify-content:space-between;
              gap:12px;
              flex-wrap:wrap;
          ">
            <div style="font-weight:800; font-size:1.05rem; letter-spacing:-0.02em;">
              <span style="opacity:0.9;">'{keyword.keyword_name}'</span> 키워드 정성적 분석
            </div>
            <div style="display:flex; gap:8px; flex-wrap:wrap; font-size:0.78rem;">
              <span style="
                  background:rgba(255,255,255,0.18);
                  padding:4px 10px;
                  border-radius:999px;
                  font-weight:600;
              ">
                🔍 연관 키워드 {total_related}개 기준
              </span>
              <span style="
                  background:rgba(255,255,255,0.18);
                  padding:4px 10px;
                  border-radius:999px;
                  font-weight:600;
              ">
                📚 공동 등장 횟수 합계 {total_freq}회
              </span>
            </div>
          </div>

          <!-- 본문 영역 -->
          <div style="
              padding:20px 22px 22px 22px;
              background:#F9FAFB;
          ">
            <div style="
                background:#FFFFFF;
                border-radius:12px;
                border:1px solid #E5E7EB;
                padding:18px 20px;
                font-size:0.95rem;
                line-height:1.7;
                color:#111827;
            ">
              {formatted_paragraphs}
            </div>
          </div>
        </div>
        """

        return JsonResponse(
            {"analysis": html_output},
            status=200,
            json_dumps_params={'ensure_ascii': False}
        )

    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": f"Ollama API 요청 실패: {str(e)}"}, status=500)

    except json.JSONDecodeError as e:
        return JsonResponse({"error": f"Ollama 응답 JSON 변환 실패: {str(e)}"}, status=500)


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
                        continue

                    cursor.execute("SELECT part_id FROM paper_part WHERE paper_id = %s", [paper_id])
                    part_ids = cursor.fetchall()

                    if not part_ids:
                        continue

                    for part_id in part_ids:
                        cursor.execute("""
                            INSERT INTO savedpaper (user_id, paper_id, part_id, saved_at)
                            VALUES (%s, %s, %s, NOW())
                        """, [user_id, paper_id, part_id[0]])

            connection.commit()
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
            saved_paper_ids = [row[0] for row in cursor.fetchall()]

        return JsonResponse({"saved_paper_ids": saved_paper_ids})

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        return JsonResponse({"error": str(e)}, status=500)


def save_recent_paper(request, paper_id):  # 최근 본 논문
    user_id = request.session.get('user_id')

    if not user_id:
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)

    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT id FROM recentpaper WHERE user_id = %s AND paper_id = %s",
                    [user_id, paper_id]
                )
                existing_paper = cursor.fetchone()

                if existing_paper:
                    cursor.execute(
                        "UPDATE recentpaper SET viewed_at = %s WHERE id = %s",
                        [timezone.now(), existing_paper[0]]
                    )
                else:
                    cursor.execute(
                        "INSERT INTO recentpaper (user_id, paper_id, viewed_at) VALUES (%s, %s, %s)",
                        [user_id, paper_id, timezone.now()]
                    )

                cursor.execute(
                    "SELECT id FROM recentpaper WHERE user_id = %s ORDER BY viewed_at DESC",
                    [user_id]
                )
                recent_papers = cursor.fetchall()

                if len(recent_papers) > 10:
                    oldest_paper_id = recent_papers[-1][0]
                    cursor.execute(
                        "DELETE FROM recentpaper WHERE id = %s",
                        [oldest_paper_id]
                    )

        return JsonResponse({"message": "최근 본 논문이 저장되었습니다."}, status=200)

    except Exception as e:
        print(f"❌ [ERROR] {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)
    

@csrf_exempt
def pdf_upload_view(request):
    """📄 JavaScript에서 생성된 PDF를 서버에 저장 (로그인 필요)"""
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "잘못된 요청"}, status=400)

    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "로그인이 필요합니다."}, status=403)

    if "pdf" not in request.FILES:
        return JsonResponse({"success": False, "error": "파일이 없습니다."}, status=400)

    pdf_file = request.FILES["pdf"]
    content_type = request.POST.get("content_type", "unknown")
    object_title = request.POST.get("object_title", "unknown")

    user_id = request.user.id

    base_folder = os.path.join(settings.BASE_DIR, "main", "pdfs", str(user_id))
    category_folder = os.path.join(base_folder, content_type)
    os.makedirs(category_folder, exist_ok=True)

    if content_type == "author" and object_title.lower() == "eom":
        file_name = "author_eom.pdf"
    else:
        file_name = f"{content_type}_{object_title}.pdf"

    file_path = os.path.join(category_folder, file_name)

    with open(file_path, "wb") as f:
        for chunk in pdf_file.chunks():
            f.write(chunk)

    return JsonResponse({"success": True})
