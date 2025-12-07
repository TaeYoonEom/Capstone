from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse
from django.template.loader import render_to_string
from collections import defaultdict
from django.contrib import messages
from django.db import connection, transaction
from collections import Counter
from django.utils import timezone
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.utils.timezone import now
from datetime import datetime
from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_exempt
import json
from django.contrib.auth.hashers import check_password, make_password
from django.db.models import Q
import random
import string
from django.core.mail import send_mail
from django.contrib.auth.decorators import login_required
from django.contrib.auth import get_user_model
import requests
import re
from .models import Part  
from math import ceil
from django.core.cache import cache
from django.views.decorators.cache import cache_page
from email.utils import parsedate_to_datetime
from datetime import datetime
from django.views.decorators.http import require_POST

#메인페이지
#인기 키워드, 인기 논문 5개

def main(request):
    # 인기 논문 5개 가져오기 (SavedPaper 테이블에서 paper_id 기준으로 카운트)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT p.id, p.title, COUNT(sp.paper_id) AS save_count
            FROM savedpaper sp
            JOIN paper p ON sp.paper_id = p.id
            GROUP BY sp.paper_id, p.id, p.title
            ORDER BY save_count DESC, p.id ASC
            LIMIT 5;
        """)
        popular_papers = cursor.fetchall()  # 리스트 형태로 결과 저장

    # 결과를 딕셔너리 리스트로 변환
    papers = [{'id': row[0], 'title': row[1]} for row in popular_papers]

    # 실시간 인기 키워드 10개 가져오기 (keyword_id 포함)
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT id, keyword
            FROM searchkeyword
            ORDER BY count DESC
            LIMIT 10;
        """)
        popular_keywords = [{'id': row[0], 'keyword': row[1]} for row in cursor.fetchall()]

    return render(request, 'main.html', {
        'popular_papers': papers,  # 인기 논문 데이터 (SQL 쿼리 결과)
        'popular_keywords': popular_keywords  # 인기 키워드 데이터 (id 포함)
    })

# 인기 자료 페이지
def popular_papers_page(request):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT p.id, p.title, COUNT(sp.paper_id) AS save_count
            FROM savedpaper sp
            JOIN paper p ON sp.paper_id = p.id
            GROUP BY sp.paper_id, p.id, p.title
            ORDER BY save_count DESC, p.id ASC
            LIMIT 10;
        """)
        popular_papers = cursor.fetchall()

    papers = [{'id': row[0], 'title': row[1], 'save_count': row[2]} for row in popular_papers]
    return render(request, 'popular_papers.html', {'popular_papers': papers})

# 주제별 논문 페이지 목록
def part_paper_page(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, name FROM part ORDER BY name ASC;")
        parts = cursor.fetchall()

    parts_list = [{'id': row[0], 'name': row[1]} for row in parts]
    return render(request, 'part_paper_page.html', {'parts': parts_list})

# ✅ 제목 검색(q) + 페이지네이션
def get_papers_by_part(request, part_id):
    from math import ceil
    q = (request.GET.get('q') or '').strip()
    try:
        page = max(int(request.GET.get('page', 1)), 1)
    except ValueError:
        page = 1
    try:
        page_size = int(request.GET.get('page_size', 20))
    except ValueError:
        page_size = 20
    page_size = max(min(page_size, 200), 1)
    offset = (page - 1) * page_size

    # 검색 조건
    where_q = ""
    params = [part_id]
    if q:
        where_q = " AND LOWER(p.title) LIKE LOWER(%s) "
        params.append(f"%{q}%")

    # 총 개수
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT COUNT(*)
            FROM paper_part pp
            JOIN paper p ON pp.paper_id = p.id
            WHERE pp.part_id = %s {where_q}
        """, params)
        total_count = cursor.fetchone()[0]

    # 해당 페이지 데이터
    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT p.id, p.title
            FROM paper_part pp
            JOIN paper p ON pp.paper_id = p.id
            WHERE pp.part_id = %s {where_q}
            ORDER BY p.title ASC
            LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        rows = cursor.fetchall()

    papers = [{'id': r[0], 'title': r[1]} for r in rows]
    total_pages = ceil(total_count / page_size) if page_size else 1

    return JsonResponse({
        'papers': papers,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'total_count': total_count,
        'has_prev': page > 1,
        'has_next': page < total_pages,
        'q': q,
    })


#기업소개페이지
def introduction(request):
    return render(request, 'introduction.html')

# 분석 페이지 (HTML 렌더링) 연도 지정 
def analysis(request):
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT DISTINCT year
            FROM paper
            WHERE year IS NOT NULL
            ORDER BY year
        """)
        year_rows = cursor.fetchall()
        years = [row[0] for row in year_rows]  # 튜플을 리스트로 변환

    main_parts = Part.objects.all().order_by('name')  # 주제 목록 가져오기
    return render(request, 'analysis.html', {'years': years, 'main_parts': main_parts})

# 분석페이지
# 연도별 파트 및 키워드 순위 가져오기 (AJAX)
def get_rankings(request, year):
    with connection.cursor() as cursor:
        # ✅ 파트: id, name, count
        cursor.execute("""
            SELECT part.id, part.name, COUNT(*) AS part_count
            FROM paper_part
            JOIN part ON paper_part.part_id = part.id
            JOIN paper ON paper_part.paper_id = paper.id
            WHERE paper.year = %s
            GROUP BY part.id, part.name
            ORDER BY part_count DESC
            LIMIT 10
        """, [year])
        part_rankings = cursor.fetchall()  # [(id, name, count), ...]

        # ✅ 키워드: id, name, count
        cursor.execute("""
            SELECT keyword.id, keyword.keyword_name, COUNT(*) AS keyword_count
            FROM paper_keyword
            JOIN keyword ON paper_keyword.keyword_id = keyword.id
            JOIN paper ON paper_keyword.paper_id = paper.id
            WHERE paper.year = %s
            GROUP BY keyword.id, keyword.keyword_name
            ORDER BY keyword_count DESC
            LIMIT 10
        """, [year])
        keyword_rankings = cursor.fetchall()

    # 보기 좋은 JSON 형태로 반환
    return JsonResponse({
        "part_rankings": [
            {"id": r[0], "name": r[1], "count": r[2]} for r in part_rankings
        ],
        "keyword_rankings": [
            {"id": r[0], "name": r[1], "count": r[2]} for r in keyword_rankings
        ]
    })


def get_wordcloud_data(request): # 분석페이지 워드클라우드
    year = request.GET.get('year')
    part_id = request.GET.get('part_id')

    query_params = []
    where_clause = ""

    if year:
        where_clause += " AND paper.year = %s"
        query_params.append(year)

    if part_id:
        where_clause += " AND part.id = %s"
        query_params.append(part_id)

    with connection.cursor() as cursor:
        cursor.execute(f"""
            SELECT keyword.keyword_name, COUNT(*) AS count
            FROM paper_keyword
            JOIN keyword ON paper_keyword.keyword_id = keyword.id
            JOIN paper ON paper_keyword.paper_id = paper.id
            JOIN paper_part ON paper.id = paper_part.paper_id
            JOIN part ON paper_part.part_id = part.id
            WHERE 1=1 {where_clause}
            GROUP BY keyword.keyword_name
            ORDER BY count DESC
            LIMIT 50  -- 상위 50개 키워드
        """, query_params)
        keyword_data = cursor.fetchall()

    return JsonResponse({"keywords": [{"text": row[0], "size": row[1] * 10} for row in keyword_data]})

def get_keyword_id(request): #분석 페이지 워드 클라우드
    keyword_name = request.GET.get('name')

    if not keyword_name:
        return JsonResponse({"error": "키워드가 제공되지 않았습니다."}, status=400)

    with connection.cursor() as cursor:
        cursor.execute("SELECT id FROM keyword WHERE keyword_name = %s", [keyword_name])
        keyword_data = cursor.fetchone()

    if keyword_data:
        return JsonResponse({"keyword_id": keyword_data[0]})
    else:
        return JsonResponse({"error": "해당 키워드가 없습니다."}, status=404)


################### PDF 저장 ##############################################################
import os
from django.http import JsonResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import re


############################## 시각화 #############################################

def part_pie_chart_view(request):
    # SQL 쿼리로 part 데이터 가져오기
    with connection.cursor() as cursor:
        cursor.execute("SELECT name, part_count FROM part ORDER BY part_count DESC")
        pie_data = cursor.fetchall()

    # 데이터 구성
    data = [{'name': item[0], 'value': item[1]} for item in pie_data]
    return JsonResponse(data, safe=False)


def keyword_cloud_data(request):
    # SQL 쿼리로 searchkeyword 테이블에서 keyword와 count 가져오기
    with connection.cursor() as cursor:
        cursor.execute("SELECT keyword, count FROM searchkeyword ORDER BY count DESC")
        keyword_data = cursor.fetchall()

    # 워드클라우드 데이터 구성 - 크기 스케일링
    max_count = max([row[1] for row in keyword_data]) if keyword_data else 1
    wordcloud_data = [{'text': row[0], 'size': int((row[1] / max_count) * 100) + 20} for row in keyword_data]

    return JsonResponse(wordcloud_data, safe=False)

def get_affiliation_count(request):
    # SQL 쿼리로 affiliation 테이블의 학회 수 가져오기
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM affiliation")
        affiliation_count = cursor.fetchone()[0]

    # JSON 응답 반환
    return JsonResponse({'affiliation_count': affiliation_count})

def get_paper_count(request):
    # SQL 쿼리로 paper 테이블의 논문 수 가져오기
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM paper")
        paper_count = cursor.fetchone()[0]

    # JSON 응답 반환
    return JsonResponse({'paper_count': paper_count})

def get_user_count(request):
    # SQL 쿼리로 user 테이블의 이용자 수 가져오기
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM user")
        user_count = cursor.fetchone()[0]

    # JSON 응답 반환
    return JsonResponse({'user_count': user_count})


def get_top_saved_parts(request):
    # SQL 쿼리로 가장 많이 저장된 TOP 10 파트 가져오기
    query = """
        SELECT p.name, COUNT(sp.part_id) AS save_count
        FROM savedpaper sp
        JOIN part p ON sp.part_id = p.id
        WHERE sp.part_id IS NOT NULL  -- ✅ NULL 값 방지
        GROUP BY p.name
        ORDER BY save_count DESC
        LIMIT 5
    """
    with connection.cursor() as cursor:
        cursor.execute(query)
        top_parts = cursor.fetchall()

    # JSON 데이터 구성
    part_data = [{'name': row[0], 'count': row[1]} for row in top_parts]
    return JsonResponse(part_data, safe=False)

#########################로그인/ 회원가입 / 마이페이지 ###########################

def register_page(request):
    """register.html 페이지를 반환하는 뷰"""
    return render(request, 'register.html')

@csrf_exempt
def register_user(request):
    """회원가입 기능"""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            username = data.get('user_name')
            email = data.get('email')
            password = data.get('password')
            confirm_password = data.get('confirm_password')

            if password != confirm_password:
                return JsonResponse({"error": "Passwords do not match"}, status=400)

            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM user WHERE user_name = %s", [username])
                if cursor.fetchone()[0] > 0:
                    return JsonResponse({"error": "Username already exists"}, status=400)

                hashed_password = make_password(password)

                cursor.execute("""
                    INSERT INTO user (user_name, email, password, date_joined, last_login)
                    VALUES (%s, %s, %s, %s, %s)
                """, [username, email, hashed_password, now(), None])

            # ✅ 회원가입 성공 → 로그인 페이지로 이동 (회원가입 플래그 추가)
            return JsonResponse({
                "message": "회원가입 성공",
                "redirect_url": "/login/?from_register=1"
            }, status=201)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)

def check_username(request):
    """사용자 ID 중복 확인"""
    if request.method == "GET":
        user_name = request.GET.get('user_name')

        if not user_name:
            return JsonResponse({"error": "사용자 ID를 입력해주세요."}, status=400)

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM user WHERE user_name = %s", [user_name])
                if cursor.fetchone()[0] > 0:
                    return JsonResponse({"error": "이미 존재하는 사용자 ID입니다."}, status=400)

            return JsonResponse({"message": "사용 가능한 ID입니다."}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "잘못된 요청입니다."}, status=405)

def login_page(request):
    """login.html 반환 + 이전 페이지 경로 전달"""
    next_url = request.GET.get('next')  # 이전 페이지 정보
    from_register = request.GET.get('from_register')
    context = {
        "next": next_url or "",
        "from_register": from_register or "0"
    }
    return render(request, 'login.html', context)

@csrf_exempt
def login_user(request):
    """로그인 기능"""
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_name = data.get('user_name')
            password = data.get('password')
            next_url = data.get('next')
            from_register = data.get('from_register')

            with connection.cursor() as cursor:
                cursor.execute("SELECT id, password FROM user WHERE user_name = %s", [user_name])
                result = cursor.fetchone()

            if result:
                user_id, db_password = result
                valid = check_password(password, db_password) or password == db_password

                if valid:
                    with connection.cursor() as cursor:
                        cursor.execute("UPDATE user SET last_login = %s WHERE user_name = %s", [now(), user_name])

                    # Django User 객체 처리
                    try:
                        user = User.objects.get(id=user_id)
                    except User.DoesNotExist:
                        user = User(id=user_id, username=user_name)
                        user.set_unusable_password()
                        user.save()

                    user.backend = 'django.contrib.auth.backends.ModelBackend'
                    login(request, user)

                    request.session['user_id'] = user_id
                    request.session['user_name'] = user_name

                    # ✅ 리다이렉트 URL 처리
                    if from_register == "1":
                        redirect_url = "http://calfadventure.com:8000/"
                    elif next_url:
                        redirect_url = next_url
                    else:
                        redirect_url = "/"

                    return JsonResponse({
                        "message": "로그인 성공",
                        "status": "success",
                        "redirect_url": redirect_url
                    }, status=200)

                return JsonResponse({"error": "비밀번호가 틀렸습니다."}, status=400)
            else:
                return JsonResponse({"error": "존재하지 않는 사용자입니다."}, status=400)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request method"}, status=405)


def find_user_id(request):
    """이메일을 통해 사용자 ID 찾기"""
    if request.method == "GET":
        email = request.GET.get('email')

        with connection.cursor() as cursor:
            cursor.execute("SELECT user_name FROM user WHERE email = %s", [email])
            result = cursor.fetchone()

        if result:
            return JsonResponse({"user_name": result[0]}, status=200)
        else:
            return JsonResponse({"error": "해당 이메일로 등록된 ID가 없습니다."}, status=404)

    return JsonResponse({"error": "잘못된 요청 방식입니다."}, status=405)

@csrf_exempt
def reset_password(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            user_name = data.get('user_name')
            email = data.get('email')

            with connection.cursor() as cursor:
                cursor.execute("SELECT id FROM user WHERE user_name = %s AND email = %s", [user_name, email])
                result = cursor.fetchone()

            if not result:
                return JsonResponse({"error": "입력한 정보와 일치하는 사용자가 없습니다."}, status=400)

            # 임시 비밀번호 생성
            new_password = ''.join(random.choices(string.ascii_letters + string.digits, k=8))

            # 🔒 비밀번호 암호화
            hashed_password = make_password(new_password)

            # DB 업데이트
            with connection.cursor() as cursor:
                cursor.execute("UPDATE user SET password = %s WHERE user_name = %s", [hashed_password, user_name])

            # 이메일 전송
            send_mail(
                "ITRT 비밀번호 재설정",
                f"안녕하세요, {user_name}님.\n\n새로운 임시 비밀번호: {new_password}\n로그인 후 반드시 변경해주세요.",
                "ITRT@itrt.com",
                [email],
                fail_silently=False,
            )

            return JsonResponse({"message": "임시 비밀번호가 이메일로 전송되었습니다."}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "잘못된 요청 방식입니다."}, status=405)


@csrf_exempt
def logout_user(request):
    if request.method == "POST":
        # 세션 초기화
        request.session.flush()
        return JsonResponse({"message": "로그아웃 성공"}, status=200)
    return JsonResponse({"error": "Invalid request method"}, status=405)


###################### 마이페이지 #######################
def mypage_view(request):  
    if not request.session.get('user_id'):
        messages.error(request, "로그인을 하셔야 합니다!")  
        return redirect('/login')

    user_id = request.session.get('user_id')

    with connection.cursor() as cursor:
        # ✅ 사용자 정보 조회
        cursor.execute("""
            SELECT user_name, email FROM user WHERE id = %s
        """, [user_id])
        user_info = cursor.fetchone()
        if not user_info:
            messages.error(request, "사용자 정보를 찾을 수 없습니다.")
            return redirect('/login')

        # ✅ 저장된 논문 조회
        cursor.execute("""
            SELECT p.id, p.title, p.abstract, p.year, p.published_in, p.citation, sp.saved_at
            FROM paper p
            JOIN savedpaper sp ON p.id = sp.paper_id
            WHERE sp.user_id = %s
            ORDER BY sp.saved_at DESC
        """, [user_id])
        saved_papers = cursor.fetchall()

        # ✅ 최근 본 논문 조회 (최근 10개 유지 + 좋아요 수/상태 포함)
        cursor.execute("""
            SELECT 
                p.id,
                p.title,
                rp.viewed_at,
                COALESCE(lp_counts.cnt, 0) AS like_count,
                CASE 
                    WHEN EXISTS (
                        SELECT 1 
                        FROM like_paper lp2 
                        WHERE lp2.paper_id = p.id AND lp2.user_id = %s
                    ) THEN 1 ELSE 0 
                END AS is_liked
            FROM paper p
            JOIN recentpaper rp ON p.id = rp.paper_id
            LEFT JOIN (
                SELECT paper_id, COUNT(*) AS cnt
                FROM like_paper
                GROUP BY paper_id
            ) lp_counts ON lp_counts.paper_id = p.id
            WHERE rp.user_id = %s
            ORDER BY rp.viewed_at DESC
            LIMIT 10
        """, [user_id, user_id])
        recent_papers = cursor.fetchall()

        # ✅ 데이터 검증
        recent_papers = [
            (paper_id, title, viewed_at, like_count, is_liked)
            for paper_id, title, viewed_at, like_count, is_liked in recent_papers
            if paper_id is not None
        ]


        # ✅ 논문별 저자 리스트 가져오기 (최대 5명까지 표시)
        cursor.execute("""
            SELECT pa.paper_id, GROUP_CONCAT(a.name ORDER BY a.name SEPARATOR ', ') 
            FROM paper_author pa
            JOIN author a ON pa.author_id = a.id
            WHERE pa.paper_id IN (
                SELECT paper_id FROM savedpaper WHERE user_id = %s
            )
            GROUP BY pa.paper_id
        """, [user_id])
        authors = {}
        for paper_id, author_list in cursor.fetchall():
            author_names = author_list.split(", ")  # 리스트 변환
            if len(author_names) > 5:
                authors[paper_id] = f"{', '.join(author_names[:5])} 외 {len(author_names) - 5}인"
            else:
                authors[paper_id] = author_list  # 5명 이하이면 그대로 출력

        # ✅ 논문별 국가 리스트 가져오기
        cursor.execute("""
            SELECT pc.paper_id, GROUP_CONCAT(c.name SEPARATOR ', ') 
            FROM paper_country pc
            JOIN country c ON pc.country_id = c.id
            WHERE pc.paper_id IN (
                SELECT paper_id FROM savedpaper WHERE user_id = %s
            )
            GROUP BY pc.paper_id
        """, [user_id])
        countries = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        # ✅ 논문별 기관(Affiliation) 리스트 가져오기
        cursor.execute("""
            SELECT pa.paper_id, GROUP_CONCAT(af.name SEPARATOR ', ') 
            FROM paper_affiliation pa
            JOIN affiliation af ON pa.affiliation_id = af.id
            WHERE pa.paper_id IN (
                SELECT paper_id FROM savedpaper WHERE user_id = %s
            )
            GROUP BY pa.paper_id
        """, [user_id])
        affiliations = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        # ✅ 논문별 파트(Part) 리스트 가져오기
        cursor.execute("""
            SELECT pp.paper_id, GROUP_CONCAT(pt.name SEPARATOR ', ') 
            FROM paper_part pp
            JOIN part pt ON pp.part_id = pt.id
            WHERE pp.paper_id IN (
                SELECT paper_id FROM savedpaper WHERE user_id = %s
            )
            GROUP BY pp.paper_id
        """, [user_id])
        parts = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        # ✅ 논문별 키워드 리스트 가져오기
        cursor.execute("""
            SELECT pk.paper_id, GROUP_CONCAT(k.keyword_name SEPARATOR ', ') 
            FROM paper_keyword pk
            JOIN keyword k ON pk.keyword_id = k.id
            WHERE pk.paper_id IN (
                SELECT paper_id FROM savedpaper WHERE user_id = %s
            )
            GROUP BY pk.paper_id
        """, [user_id])
        keywords = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        # ✅ 논문별 좋아요 수 가져오기
        cursor.execute("""
            SELECT paper_id, COUNT(*) FROM like_paper
            GROUP BY paper_id
        """)
        likes = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        # ✅ 사용자가 좋아요를 누른 논문 목록 가져오기
        cursor.execute("""
            SELECT paper_id FROM like_paper WHERE user_id = %s
        """, [user_id])
        liked_papers = {row[0]: True for row in cursor.fetchall()} if cursor.rowcount > 0 else {}

        # ✅ 발행 연도 목록 가져오기
        cursor.execute("""
            SELECT DISTINCT p.year
            FROM paper p
            JOIN savedpaper sp ON p.id = sp.paper_id
            WHERE sp.user_id = %s
            ORDER BY p.year DESC
        """, [user_id])
        years = [row[0] for row in cursor.fetchall()]

        # ✅ 연구 분야 목록 가져오기
        cursor.execute("""
            SELECT DISTINCT pt.name
            FROM paper_part pp
            JOIN part pt ON pp.part_id = pt.id
            WHERE pp.paper_id IN (
                SELECT paper_id FROM savedpaper WHERE user_id = %s
            )
            ORDER BY pt.name
        """, [user_id])
        research_parts = [row[0] for row in cursor.fetchall()]

        # ✅ 발행처 목록 가져오기
        cursor.execute("""
            SELECT DISTINCT p.published_in
            FROM paper p
            JOIN savedpaper sp ON p.id = sp.paper_id
            WHERE sp.user_id = %s
            ORDER BY p.published_in
        """, [user_id])
        published_in_list = [row[0] for row in cursor.fetchall()]

        # ✅ 저자 목록 가져오기
        cursor.execute("""
            SELECT DISTINCT a.name
            FROM author a
            JOIN paper_author pa ON a.id = pa.author_id
            WHERE pa.paper_id IN (
                SELECT paper_id FROM savedpaper WHERE user_id = %s
            )
            ORDER BY a.name
        """, [user_id])
        authors_list = [row[0] for row in cursor.fetchall()]

        # ✅ 기관 목록 가져오기
        cursor.execute("""
            SELECT DISTINCT af.name
            FROM affiliation af
            JOIN paper_affiliation pa ON af.id = pa.affiliation_id
            WHERE pa.paper_id IN (
                SELECT paper_id FROM savedpaper WHERE user_id = %s
            )
            ORDER BY af.name
        """, [user_id])
        affiliations_list = [row[0] for row in cursor.fetchall()]

        # ✅ 국가 목록 가져오기
        cursor.execute("""
            SELECT DISTINCT c.name
            FROM country c
            JOIN affiliation af ON c.id = af.country_id
            JOIN paper_affiliation pa ON af.id = pa.affiliation_id
            WHERE pa.paper_id IN (
                SELECT paper_id FROM savedpaper WHERE user_id = %s
            )
            ORDER BY c.name
        """, [user_id])
        countries_list = [row[0] for row in cursor.fetchall()]

        # ✅ 좋아요한 저자 목록
        cursor.execute("""
            SELECT a.name
            FROM author a
            JOIN like_author la ON a.id = la.author_id
            WHERE la.user_id = %s
        """, [user_id])
        liked_authors_list = [row[0] for row in cursor.fetchall()]

        # ✅ 좋아요한 기관 목록
        cursor.execute("""
            SELECT af.name
            FROM affiliation af
            JOIN like_affiliation la ON af.id = la.affiliation_id
            WHERE la.user_id = %s
        """, [user_id])
        liked_affiliations_list = [row[0] for row in cursor.fetchall()]

        # ✅ 좋아요한 나라 목록
        cursor.execute("""
            SELECT c.name
            FROM country c
            JOIN like_country lc ON c.id = lc.country_id
            WHERE lc.user_id = %s
        """, [user_id])
        liked_countries_list = [row[0] for row in cursor.fetchall()]

        # ✅ 좋아요한 논문 연도 가져오기
        cursor.execute("""
            SELECT DISTINCT p.year
            FROM paper p
            JOIN like_paper lp ON p.id = lp.paper_id
            WHERE lp.user_id = %s
            ORDER BY p.year DESC
        """, [user_id])
        liked_paper_years = [row[0] for row in cursor.fetchall()]

        # ✅ 좋아요한 논문 연구 분야 가져오기
        cursor.execute("""
            SELECT DISTINCT pa.name
            FROM part pa
            JOIN paper_part pp ON pa.id = pp.part_id
            WHERE pp.paper_id IN (
                SELECT paper_id FROM like_paper WHERE user_id = %s
            )
            ORDER BY pa.name
        """, [user_id])
        liked_paper_parts = [row[0] for row in cursor.fetchall()]

        # ✅ 좋아요한 논문 발행처 가져오기
        cursor.execute("""
            SELECT DISTINCT p.published_in
            FROM paper p
            JOIN like_paper lp ON p.id = lp.paper_id
            WHERE lp.user_id = %s
            ORDER BY p.published_in
        """, [user_id])
        liked_paper_publishers = [row[0] for row in cursor.fetchall()]

        # ✅ 좋아요한 논문 저자 가져오기
        cursor.execute("""
            SELECT DISTINCT a.name
            FROM author a
            JOIN paper_author pa ON a.id = pa.author_id
            WHERE pa.paper_id IN (
                SELECT paper_id FROM like_paper WHERE user_id = %s
            )
            ORDER BY a.name
        """, [user_id])
        liked_paper_authors = [row[0] for row in cursor.fetchall()]

        # ✅ 논문 정보 구성
        updated_papers = []
        for paper in saved_papers:
            paper_id = paper[0]
            updated_papers.append((  
                paper_id, paper[1], paper[2],  # 논문 ID, 제목, 초록
                paper[3], paper[4], paper[5],  # 연도, 발행처, 인용수
                paper[6],  # 저장일
                authors.get(paper_id, "정보 없음"),       # ✅ 수정된 저자 (최대 5명 + "외 %인")
                countries.get(paper_id, "정보 없음"),     # 국가
                affiliations.get(paper_id, "정보 없음"),  # 기관
                parts.get(paper_id, "정보 없음"),         # 연구 분야 (파트)
                keywords.get(paper_id, "정보 없음"),      # 키워드
                likes.get(paper_id, 0),  # ❤️ 좋아요 수
                paper_id in liked_papers  # ✅ 사용자가 좋아요를 눌렀는지 여부 (True/False)
            ))
    main_parts = Part.objects.all().order_by('name')

        # ✅ 필터 데이터 가져오기
    filter_data = get_liked_filter_data(user_id)

    context = {
        "user": {"user_name": user_info[0], "email": user_info[1]},
        "saved_papers": updated_papers,
        "recent_papers": recent_papers,  # ✅ 최근 본 논문 추가
        "years": years,
        "research_parts": research_parts,  # ✅ 유지 (마이페이지 필터용)
        "parts": main_parts,               # ✅ 추가 (base.html 드롭다운용)
        "published_in_list": published_in_list,
        "authors_list": authors_list,
        "affiliations_list": affiliations_list,
        "countries_list": countries_list,
        "liked_authors_list": liked_authors_list,
        "liked_affiliations_list": liked_affiliations_list,
        "liked_countries_list": liked_countries_list,
        "liked_paper_years": liked_paper_years,
        "liked_paper_parts": liked_paper_parts,
        "liked_paper_publishers": liked_paper_publishers,
        "liked_paper_authors": liked_paper_authors,
    }

    # ✅ 필터 데이터 추가
    context.update(filter_data)

    return render(request, 'mypage.html', context)


def get_liked_filter_data(user_id):
    """📌 마이페이지 필터용 데이터 제공 함수"""
    with connection.cursor() as cursor:
        # ✅ 좋아요한 저자 → 키워드 목록
        cursor.execute("""
            SELECT a.id, a.name
            FROM author a
            JOIN like_author la ON a.id = la.author_id
            WHERE la.user_id = %s
        """, [user_id])
        liked_authors = cursor.fetchall()

        # ✅ 중복 없는 키워드 set 생성
        liked_author_keywords_set = set()

        for author_id, author_name in liked_authors:
            cursor.execute("""
                SELECT k.keyword_name
                FROM paper_keyword pk
                JOIN keyword k ON pk.keyword_id = k.id
                JOIN paper_author pa ON pk.paper_id = pa.paper_id
                WHERE pa.author_id = %s
                GROUP BY k.keyword_name
                ORDER BY COUNT(*) DESC
                LIMIT 8
            """, [author_id])
            keywords = [row[0] for row in cursor.fetchall()]
            liked_author_keywords_set.update(keywords)

        # ✅ set → list 변환
        liked_author_keywords = list(liked_author_keywords_set)

        # ✅ 좋아요한 저자 → 소속 기관
        cursor.execute("""
            SELECT DISTINCT a.affiliation
            FROM author a
            JOIN like_author la ON a.id = la.author_id
            WHERE la.user_id = %s AND a.affiliation IS NOT NULL
        """, [user_id])
        liked_author_affiliations = [row[0] for row in cursor.fetchall()]

        # ✅ 좋아요한 기관 → 국가
        cursor.execute("""
            SELECT DISTINCT c.name
            FROM country c
            JOIN affiliation af ON c.id = af.country_id
            JOIN like_affiliation la ON af.id = la.affiliation_id
            WHERE la.user_id = %s
        """, [user_id])
        liked_affiliation_countries = [row[0] for row in cursor.fetchall()]

        # ✅ 좋아요한 기관 목록 조회
        cursor.execute("""
            SELECT af.id, af.name
            FROM affiliation af
            JOIN like_affiliation la ON af.id = la.affiliation_id
            WHERE la.user_id = %s
        """, [user_id])
        liked_affiliations = cursor.fetchall()

        # ✅ 주요 저자 set 생성
        liked_affiliation_authors_set = set()

        for affiliation_id, affiliation_name in liked_affiliations:
            cursor.execute("""
                SELECT a.name
                FROM author a
                JOIN paper_author pa ON a.id = pa.author_id
                JOIN paper_affiliation paf ON pa.paper_id = paf.paper_id
                WHERE paf.affiliation_id = %s
                GROUP BY a.name
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, [affiliation_id])
            authors = [row[0] for row in cursor.fetchall()]
            liked_affiliation_authors_set.update(authors)

        # ✅ set → list 변환
        liked_affiliation_authors = list(liked_affiliation_authors_set)

        # ✅ 좋아요한 기관 → 키워드
        # ✅ 주요 키워드 set 생성
        liked_affiliation_keywords_set = set()

        for affiliation_id, affiliation_name in liked_affiliations:
            cursor.execute("""
                SELECT k.keyword_name
                FROM keyword k
                JOIN paper_keyword pk ON k.id = pk.keyword_id
                JOIN paper_affiliation paf ON pk.paper_id = paf.paper_id
                WHERE paf.affiliation_id = %s
                GROUP BY k.keyword_name
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, [affiliation_id])
            keywords = [row[0] for row in cursor.fetchall()]
            liked_affiliation_keywords_set.update(keywords)

        # ✅ set → list 변환
        liked_affiliation_keywords = list(liked_affiliation_keywords_set)


        # ✅ 좋아요한 나라 → 주요 키워드
        # ✅ 좋아요한 나라 목록 조회
        cursor.execute("""
            SELECT c.id, c.name
            FROM country c
            JOIN like_country lc ON c.id = lc.country_id
            WHERE lc.user_id = %s
        """, [user_id])
        liked_countries = cursor.fetchall()

        # ✅ 주요 키워드 set 생성 (중복 제거용)
        liked_country_keywords_set = set()

        for country_id, country_name in liked_countries:
            # ✅ 해당 나라 주요 키워드 5개 가져오기
            cursor.execute("""
                SELECT k.keyword_name
                FROM paper_keyword pk
                JOIN keyword k ON pk.keyword_id = k.id
                JOIN paper_country pc ON pk.paper_id = pc.paper_id
                WHERE pc.country_id = %s
                GROUP BY k.keyword_name
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, [country_id])
            keywords = [row[0] for row in cursor.fetchall()]
            liked_country_keywords_set.update(keywords)

        # ✅ set → list 변환
        liked_country_keywords = list(liked_country_keywords_set)


        # ✅ 좋아요한 나라 → 주요 기관
        # ✅ 주요 기관 set 생성
        liked_country_affiliations_set = set()

        for country_id, country_name in liked_countries:
            cursor.execute("""
                SELECT af.name
                FROM affiliation af
                WHERE af.country_id = %s
                GROUP BY af.name
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, [country_id])
            affiliations = [row[0] for row in cursor.fetchall()]
            liked_country_affiliations_set.update(affiliations)

        # ✅ set → list 변환
        liked_country_affiliations = list(liked_country_affiliations_set)


    return {
        "liked_author_keywords": liked_author_keywords,
        "liked_author_affiliations": liked_author_affiliations,
        "liked_affiliation_authors": liked_affiliation_authors,
        "liked_affiliation_countries": liked_affiliation_countries,
        "liked_affiliation_keywords": liked_affiliation_keywords,
        "liked_country_keywords": liked_country_keywords,
        "liked_country_affiliations": liked_country_affiliations,
    }


# 마이페이지 좋아요한 논문/저자
def liked_items_view(request):
    """
    사용자가 좋아요한 논문, 저자, 기관, 나라, 키워드를 가져오는 API
    """
    if not request.session.get('user_id'):
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)

    user_id = request.session.get('user_id')

    with connection.cursor() as cursor:
        # ✅ 좋아요한 논문 조회
        cursor.execute("""
            SELECT p.id, p.title, p.abstract, p.year, p.published_in, p.citation
            FROM paper p
            JOIN like_paper lp ON p.id = lp.paper_id
            WHERE lp.user_id = %s
        """, [user_id])
        liked_papers_raw = cursor.fetchall()

        # ✅ 논문별 추가 정보 가져오기 (재사용 가능한 함수)
        def get_paper_metadata(query):
            cursor.execute(query, [user_id])
            return dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        authors = get_paper_metadata("""
            SELECT pa.paper_id, GROUP_CONCAT(a.name ORDER BY a.name SEPARATOR ', ') 
            FROM paper_author pa
            JOIN author a ON pa.author_id = a.id
            WHERE pa.paper_id IN (SELECT paper_id FROM like_paper WHERE user_id = %s)
            GROUP BY pa.paper_id
        """)

        keywords = get_paper_metadata("""
            SELECT pk.paper_id, GROUP_CONCAT(k.keyword_name SEPARATOR ', ') 
            FROM paper_keyword pk
            JOIN keyword k ON pk.keyword_id = k.id
            WHERE pk.paper_id IN (SELECT paper_id FROM like_paper WHERE user_id = %s)
            GROUP BY pk.paper_id
        """)

        affiliations = get_paper_metadata("""
            SELECT pa.paper_id, GROUP_CONCAT(af.name SEPARATOR ', ') 
            FROM paper_affiliation pa
            JOIN affiliation af ON pa.affiliation_id = af.id
            WHERE pa.paper_id IN (SELECT paper_id FROM like_paper WHERE user_id = %s)
            GROUP BY pa.paper_id
        """)

        countries = get_paper_metadata("""
            SELECT pc.paper_id, GROUP_CONCAT(c.name SEPARATOR ', ') 
            FROM paper_country pc
            JOIN country c ON pc.country_id = c.id
            WHERE pc.paper_id IN (SELECT paper_id FROM like_paper WHERE user_id = %s)
            GROUP BY pc.paper_id
        """)

        parts = get_paper_metadata("""
            SELECT pp.paper_id, GROUP_CONCAT(pt.name SEPARATOR ', ') 
            FROM paper_part pp
            JOIN part pt ON pp.part_id = pt.id
            WHERE pp.paper_id IN (SELECT paper_id FROM like_paper WHERE user_id = %s)
            GROUP BY pp.paper_id
        """)

        # ✅ 논문별 좋아요 수 가져오기
        cursor.execute("""
            SELECT paper_id, COUNT(*) FROM like_paper
            GROUP BY paper_id
        """)
        likes = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        # ✅ 좋아요한 논문 데이터 가공 (like_count 포함)
        liked_papers = [{
            "id": paper[0],
            "title": paper[1],
            "abstract": paper[2],
            "year": paper[3],
            "published_in": paper[4],
            "citation": paper[5],
            "authors": authors.get(paper[0], "정보 없음"),
            "keywords": keywords.get(paper[0], "정보 없음"),
            "affiliations": affiliations.get(paper[0], "정보 없음"),
            "countries": countries.get(paper[0], "정보 없음"),
            "parts": parts.get(paper[0], "정보 없음"),
            "like_count": likes.get(paper[0], 0),
        } for paper in liked_papers_raw]

        # ✅ 좋아요한 저자 조회
        cursor.execute("""
            SELECT a.id, a.name, a.affiliation
            FROM author a
            JOIN like_author la ON a.id = la.author_id
            WHERE la.user_id = %s
        """, [user_id])
        liked_authors_raw = cursor.fetchall()

        # ✅ 저자별 좋아요 수 가져오기
        cursor.execute("""
            SELECT la.author_id, COUNT(*) 
            FROM like_author la 
            GROUP BY la.author_id
        """)
        author_likes = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        liked_authors = []
        for author in liked_authors_raw:
            author_id, name, affiliation = author

            # ✅ 저자가 작성한 논문 개수
            cursor.execute("""
                SELECT COUNT(*) FROM paper_author WHERE author_id = %s
            """, [author_id])
            paper_count = cursor.fetchone()[0]

            # ✅ 저자가 작성한 논문의 총 인용수
            cursor.execute("""
                SELECT SUM(p.citation)
                FROM paper p
                JOIN paper_author pa ON p.id = pa.paper_id
                WHERE pa.author_id = %s
            """, [author_id])
            citation_count = cursor.fetchone()[0] or 0  # NULL 방지

            # ✅ 저자가 포함된 논문의 키워드 가져오기 (빈도수 계산 후 5~8개 추출)
            cursor.execute("""
                SELECT k.keyword_name
                FROM paper_keyword pk
                JOIN keyword k ON pk.keyword_id = k.id
                JOIN paper_author pa ON pk.paper_id = pa.paper_id
                WHERE pa.author_id = %s
            """, [author_id])
            all_keywords = [row[0] for row in cursor.fetchall()]

            # 키워드 빈도 계산 후, 가장 많이 등장한 키워드 5~8개 선택
            keyword_counts = Counter(all_keywords)
            sorted_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)
            top_keywords = [kw[0] for kw in sorted_keywords[:8]]  # 최대 8개 선택

            # ✅ 저자가 작성한 논문의 연구 분야(파트) 가져오기
            cursor.execute("""
                SELECT GROUP_CONCAT(DISTINCT pt.name ORDER BY pt.name SEPARATOR ', ')
                FROM paper_part pp
                JOIN part pt ON pp.part_id = pt.id
                JOIN paper_author pa ON pp.paper_id = pa.paper_id
                WHERE pa.author_id = %s
            """, [author_id])
            parts = cursor.fetchone()[0] or "정보 없음"

            # ✅ 저자가 소속된 국가 가져오기
            cursor.execute("""
                SELECT GROUP_CONCAT(DISTINCT c.name ORDER BY c.name SEPARATOR ', ')
                FROM country c
                JOIN affiliation af ON c.id = af.country_id
                JOIN paper_affiliation pa ON af.id = pa.affiliation_id
                JOIN paper_author p_auth ON pa.paper_id = p_auth.paper_id
                WHERE p_auth.author_id = %s
            """, [author_id])
            country = cursor.fetchone()[0] or "정보 없음"

            liked_authors.append({
                "id": author_id,
                "name": name,
                "keywords": ", ".join(top_keywords) if top_keywords else "정보 없음",
                "parts": parts,
                "country": country,
                "paper_count": paper_count,
                "citation_count": citation_count,
                "affiliation": affiliation if affiliation else "정보 없음",
                "like_count": author_likes.get(author_id, 0),
            })

        # ✅ 좋아요한 기관(Affiliation) 조회
        cursor.execute("""
            SELECT af.id, af.name, c.name as country
            FROM affiliation af
            JOIN like_affiliation la ON af.id = la.affiliation_id
            LEFT JOIN country c ON af.country_id = c.id
            WHERE la.user_id = %s
        """, [user_id])
        liked_affiliations_raw = cursor.fetchall()  # ✅ 데이터를 변수에 저장!

        # ✅ 기관별 좋아요 수 가져오기
        cursor.execute("""
            SELECT affiliation_id, COUNT(*) FROM like_affiliation
            GROUP BY affiliation_id
        """)
        affiliation_likes = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        liked_affiliations = []
        for affiliation in liked_affiliations_raw:  # ✅ 여기서 저장한 데이터를 사용!
            affiliation_id, name, country = affiliation

            # ✅ 주요 키워드 5개 가져오기
            cursor.execute("""
                SELECT k.keyword_name
                FROM paper_keyword pk
                JOIN keyword k ON pk.keyword_id = k.id
                JOIN paper_affiliation pa ON pk.paper_id = pa.paper_id
                WHERE pa.affiliation_id = %s
                GROUP BY k.keyword_name
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, [affiliation_id])
            keywords = [row[0] for row in cursor.fetchall()]

            # ✅ 주요 저자 5명 가져오기
            cursor.execute("""
                SELECT a.name
                FROM paper_author pa
                JOIN author a ON pa.author_id = a.id
                JOIN paper_affiliation paf ON pa.paper_id = paf.paper_id
                WHERE paf.affiliation_id = %s
                GROUP BY a.name
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, [affiliation_id])
            authors = [row[0] for row in cursor.fetchall()]

            liked_affiliations.append({
                "id": affiliation_id,
                "name": name,
                "country": country if country else "정보 없음",
                "keywords": ", ".join(keywords) if keywords else "정보 없음",
                "authors": ", ".join(authors) if authors else "정보 없음",
                "like_count": affiliation_likes.get(affiliation_id, 0)  # ✅ 좋아요 수 추가
            })

        # ✅ 좋아요한 나라(Country) 조회
        cursor.execute("""
            SELECT c.id, c.name
            FROM country c
            JOIN like_country lc ON c.id = lc.country_id
            WHERE lc.user_id = %s
        """, [user_id])
        liked_countries_raw = cursor.fetchall()  # ✅ 데이터를 변수에 저장!

        # ✅ 나라별 좋아요 수 가져오기
        cursor.execute("""
            SELECT country_id, COUNT(*) FROM like_country
            GROUP BY country_id
        """)
        country_likes = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        liked_countries = []
        for country in liked_countries_raw:  # ✅ 여기서 저장한 데이터를 사용!
            country_id, country_name = country

            # ✅ 주요 키워드 5개 가져오기
            cursor.execute("""
                SELECT k.keyword_name
                FROM paper_keyword pk
                JOIN keyword k ON pk.keyword_id = k.id
                JOIN paper_country pc ON pk.paper_id = pc.paper_id
                WHERE pc.country_id = %s
                GROUP BY k.keyword_name
                ORDER BY COUNT(*) DESC
                LIMIT 5
            """, [country_id])
            keywords = [row[0] for row in cursor.fetchall()]

            # ✅ 주요 기관 5개 가져오기
            cursor.execute("""
                SELECT af.name
                FROM affiliation af
                WHERE af.country_id = %s
                LIMIT 5
            """, [country_id])
            institutions = [row[0] for row in cursor.fetchall()]

            liked_countries.append({
                "id": country_id,
                "name": country_name,
                "keywords": ", ".join(keywords) if keywords else "정보 없음",
                "institutions": ", ".join(institutions) if institutions else "정보 없음",
                "like_count": country_likes.get(country_id, 0)  # ✅ 좋아요 수 추가
            })

        # ✅ 좋아요한 키워드(Keyword) 조회
        cursor.execute("""
            SELECT k.id, k.keyword_name
            FROM keyword k
            JOIN like_keyword lk ON k.id = lk.keyword_id
            WHERE lk.user_id = %s
        """, [user_id])
        liked_keywords_raw = cursor.fetchall()  # ✅ 데이터를 변수에 저장!

        # ✅ 키워드별 좋아요 수 가져오기
        cursor.execute("""
            SELECT keyword_id, COUNT(*) FROM like_keyword
            GROUP BY keyword_id
        """)
        keyword_likes = dict(cursor.fetchall()) if cursor.rowcount > 0 else {}


        liked_keywords = []
        for keyword in liked_keywords_raw:  # ✅ 여기서 저장한 데이터를 사용!
            keyword_id, keyword_name = keyword

            # ✅ 키워드 정의 (초록 기반 2줄 요약)
            cursor.execute("""
                SELECT p.abstract
                FROM paper_keyword pk
                JOIN paper p ON pk.paper_id = p.id
                WHERE pk.keyword_id = %s
                LIMIT 1
            """, [keyword_id])
            abstract = cursor.fetchone()
            definition = " ".join(abstract[0].split()[:40]) + "..." if abstract else "정보 없음"

            liked_keywords.append({
                "id": keyword_id,
                "keyword_name": keyword_name,
                "definition": definition,
                "like_count": keyword_likes.get(keyword_id, 0)  # ✅ 좋아요 수 추가
            })

    return JsonResponse({
        "liked_papers": liked_papers,
        "liked_authors": liked_authors,
        "liked_affiliations": liked_affiliations,
        "liked_countries": liked_countries,
        "liked_keywords": liked_keywords,
    }, safe=False)

@csrf_exempt
def user_saved_pdfs(request):
    """📄 사용자가 저장한 PDF 목록 반환"""
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "로그인이 필요합니다."}, status=403)

    user_id = request.user.id  
    user_pdf_folder = os.path.join(settings.BASE_DIR, "main", "pdfs", str(user_id))

    if not os.path.exists(user_pdf_folder):
        return JsonResponse({"success": True, "pdfs": {}})  # PDF 폴더가 없으면 빈 리스트 반환

    pdf_list = {category: [] for category in ["paper", "author", "affiliation", "country", "keyword"]}

    for category in pdf_list.keys():
        category_path = os.path.join(user_pdf_folder, category)
        if os.path.isdir(category_path):
            for file in os.listdir(category_path):
                if file.endswith(".pdf"):
                    # ✅ PDF 다운로드 경로 수정 (MEDIA_URL을 사용하여 접근 가능하도록 변경)
                    pdf_list[category].append({
                        "name": file,
                        "path": f"{settings.MEDIA_URL}{user_id}/{category}/{file}"
                    })

    return JsonResponse({"success": True, "pdfs": pdf_list})


@csrf_exempt
def delete_saved_pdf(request):
    """🗑️ 사용자가 저장한 PDF 파일 삭제"""
    if not request.user.is_authenticated:
        return JsonResponse({"success": False, "error": "로그인이 필요합니다."}, status=403)

    file_path = request.POST.get("file_path")
    if not file_path:
        return JsonResponse({"success": False, "error": "파일 경로가 제공되지 않았습니다."}, status=400)

    # ✅ `file_path`에서 user_id와 category 추출
    user_id = request.user.id
    relative_path = file_path.replace(settings.MEDIA_URL, "")  # `/media/` 제거
    absolute_path = os.path.join(settings.BASE_DIR, "main", "pdfs", relative_path)

    # ✅ 파일 존재 여부 확인 후 삭제
    if os.path.exists(absolute_path):
        os.remove(absolute_path)
        return JsonResponse({"success": True})
    else:
        return JsonResponse({"success": False, "error": "파일을 찾을 수 없습니다."}, status=404)


# 추천 논문
def recommended_papers_view(request):
    """
    사용자의 관심 키워드 및 저장한 파트를 기반으로 추천 논문을 반환하는 API
    """
    if not request.session.get('user_id'):
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)

    user_id = request.session.get('user_id')

    with connection.cursor() as cursor:
        # ✅ 사용자가 좋아요/저장/최근본 논문: 추천 제외 대상
        cursor.execute("""
            SELECT paper_id FROM like_paper WHERE user_id = %s
            UNION
            SELECT paper_id FROM savedpaper WHERE user_id = %s
            UNION
            SELECT paper_id FROM recentpaper WHERE user_id = %s
        """, [user_id, user_id, user_id])
        excluded_papers = {row[0] for row in cursor.fetchall()}

        # ✅ 사용자가 저장한 논문의 키워드 상위 5개
        cursor.execute("""
            SELECT k.keyword_name, pk.keyword_id, COUNT(*) as count
            FROM paper_keyword pk
            JOIN savedpaper sp ON pk.paper_id = sp.paper_id
            JOIN keyword k ON pk.keyword_id = k.id
            WHERE sp.user_id = %s
            GROUP BY pk.keyword_id, k.keyword_name
            ORDER BY count DESC
            LIMIT 5
        """, [user_id])
        top_keywords_raw = cursor.fetchall()
        top_keywords   = [row[1] for row in top_keywords_raw]  # id
        keyword_names  = [row[0] for row in top_keywords_raw]  # name

        if not top_keywords:
            return JsonResponse({"recommended_papers": []}, safe=False)

        # ✅ 키워드 기반 후보(제외 목록 빼고)에서 인기순 정렬
        #    (IN () 방지 위해 or (0,) 사용)
        cursor.execute("""
            SELECT DISTINCT p.id, p.title, p.abstract, p.year, p.published_in, p.citation
            FROM paper p
            JOIN paper_keyword pk ON p.id = pk.paper_id
            WHERE pk.keyword_id IN %s
              AND p.id NOT IN %s
            ORDER BY 
                (SELECT COUNT(*) FROM like_paper  lp WHERE lp.paper_id = p.id) DESC,
                (SELECT COUNT(*) FROM savedpaper sp WHERE sp.paper_id = p.id) DESC
            LIMIT 7
        """, [tuple(top_keywords), tuple(excluded_papers) or (0,)])
        recommended_papers_raw = cursor.fetchall()

        # ✅ 추천된 paper_id 목록만 추려서 이후 모든 집계를 "정확히" 이 id들만 대상으로
        paper_ids = [row[0] for row in recommended_papers_raw]
        if not paper_ids:
            return JsonResponse({"recommended_papers": []}, safe=False)
        paper_ids_tuple = tuple(paper_ids)

        # ===== 집계 유틸 =====
        def fetch_map(query, params):
            cursor.execute(query, params)
            return dict(cursor.fetchall()) if cursor.rowcount > 0 else {}

        # ✅ 저자 (최대 5명 + "외 #명")
        cursor.execute("""
            SELECT pa.paper_id, GROUP_CONCAT(a.name ORDER BY a.name SEPARATOR ', ')
            FROM paper_author pa
            JOIN author a ON pa.author_id = a.id
            WHERE pa.paper_id IN %s
            GROUP BY pa.paper_id
        """, [paper_ids_tuple])
        authors = {}
        for pid, author_list in cursor.fetchall():
            names = author_list.split(", ")
            authors[pid] = f"{', '.join(names[:5])} 외 {len(names)-5}명" if len(names) > 5 else author_list

        # ✅ 파트 / 키워드 / 좋아요수 / 저장수 — 전부 추천된 id로만 집계
        parts = fetch_map("""
            SELECT pp.paper_id, GROUP_CONCAT(pt.name SEPARATOR ', ')
            FROM paper_part pp
            JOIN part pt ON pp.part_id = pt.id
            WHERE pp.paper_id IN %s
            GROUP BY pp.paper_id
        """, [paper_ids_tuple])

        keywords = fetch_map("""
            SELECT pk.paper_id, GROUP_CONCAT(k.keyword_name SEPARATOR ', ')
            FROM paper_keyword pk
            JOIN keyword k ON pk.keyword_id = k.id
            WHERE pk.paper_id IN %s
            GROUP BY pk.paper_id
        """, [paper_ids_tuple])

        likes = fetch_map("""
            SELECT paper_id, COUNT(*)
            FROM like_paper
            WHERE paper_id IN %s
            GROUP BY paper_id
        """, [paper_ids_tuple])

        saved_counts = fetch_map("""
            SELECT paper_id, COUNT(*)
            FROM savedpaper
            WHERE paper_id IN %s
            GROUP BY paper_id
        """, [paper_ids_tuple])

        # ✅ 현재 사용자가 '좋아요'한 논문 set (버튼 상태 표시용)
        cursor.execute("""
            SELECT paper_id
            FROM like_paper
            WHERE user_id = %s AND paper_id IN %s
        """, [user_id, paper_ids_tuple])
        user_liked_ids = {row[0] for row in cursor.fetchall()}

        # ✅ 추천 이유(사용자 상위 키워드와 교집합)
        def build_reason(paper_keywords_str):
            if not paper_keywords_str:
                return "사용자의 관심 키워드와 관련된 논문입니다."
            paper_kw = [kw.strip() for kw in paper_keywords_str.split(",")]
            common = [kw for kw in paper_kw if kw in keyword_names]
            if common:
                return f"회원님이 저장한 논문의 핵심 키워드 중 '{', '.join(common[:2])}'와 관련된 논문입니다."
            return "저장한 논문과 유사한 주제의 논문입니다."

        # ✅ 최종 JSON
        recommended_papers = [{
            "id":           p[0],
            "title":        p[1],
            "abstract":     p[2],
            "year":         p[3],
            "published_in": p[4],
            "citation":     p[5],
            "authors":      authors.get(p[0], "정보 없음"),
            "parts":        parts.get(p[0], "정보 없음"),
            "keywords":     keywords.get(p[0], "정보 없음"),
            "like_count":   likes.get(p[0], 0),               # 👍 정확한 좋아요 수
            "saved_count":  saved_counts.get(p[0], 0),        # 📌 저장 수
            "is_liked":     (p[0] in user_liked_ids),         # ❤️ 버튼 상태
            "reason":       build_reason(keywords.get(p[0])),
        } for p in recommended_papers_raw]

    return JsonResponse({"recommended_papers": recommended_papers}, safe=False)



@csrf_exempt  # CSRF 방지 (Ajax 요청)
def remove_saved_paper(request):
    if request.method == "POST":
        user_id = request.session.get("user_id")  # 로그인한 사용자
        if not user_id:
            return JsonResponse({"error": "로그인이 필요합니다."}, status=401)

        try:
            data = json.loads(request.body)
            paper_id = data.get("paper_id")

            if not paper_id:
                return JsonResponse({"error": "논문 ID가 필요합니다."}, status=400)

            # savedpaper 테이블에서 논문 삭제
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM savedpaper WHERE user_id = %s AND paper_id = %s",
                    [user_id, paper_id]
                )

            return JsonResponse({"success": True, "message": "논문이 저장 목록에서 삭제되었습니다."})

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "잘못된 요청입니다."}, status=400)


@csrf_exempt
def change_password(request):
    """비밀번호 변경 뷰"""
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user_id = request.session.get('user_id')
            current_password = data.get('currentPassword')
            new_password = data.get('newPassword')

            if not user_id:
                return JsonResponse({"error": "로그인이 필요합니다."}, status=401)

            # 현재 비밀번호 확인
            with connection.cursor() as cursor:
                cursor.execute("SELECT password FROM user WHERE id = %s", [user_id])
                result = cursor.fetchone()
            
            if not result:
                return JsonResponse({"error": "사용자를 찾을 수 없습니다."}, status=404)

            db_password = result[0]

            # 기존 비밀번호 검증 (해시 검증 제거)
            password_correct = (current_password == db_password)

            if not password_correct:
                return JsonResponse({"error": "현재 비밀번호가 일치하지 않습니다."}, status=400)

            # 새 비밀번호를 평문으로 저장 (보안에 취약함)
            with connection.cursor() as cursor:
                cursor.execute("UPDATE user SET password = %s WHERE id = %s", [new_password, user_id])

            return JsonResponse({"message": "비밀번호가 성공적으로 변경되었습니다."}, status=200)

        except Exception as e:
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "잘못된 요청입니다."}, status=405)

User = get_user_model()

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


## 좋아요한 저자, 기관, 나라, 키워드 
def _must_login_json(request):
    if not request.session.get('user_id'):
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)
    return None


def _toggle_like(request, table, col, obj_id):
    """공통 좋아요 토글 로직 (count=1 자동 삽입 포함)"""
    user_id = request.session.get('user_id')

    with connection.cursor() as cursor:
        # ✅ 현재 좋아요 여부 확인
        cursor.execute(f"SELECT 1 FROM {table} WHERE user_id=%s AND {col}=%s LIMIT 1",
                       [user_id, obj_id])
        exists = cursor.fetchone() is not None

        if exists:
            # ✅ 이미 좋아요면 → 취소 (삭제)
            cursor.execute(f"DELETE FROM {table} WHERE user_id=%s AND {col}=%s",
                           [user_id, obj_id])
            liked = False
        else:
            # ✅ 좋아요 추가 (count=1 필드 포함)
            try:
                cursor.execute(
                    f"INSERT INTO {table} (user_id, {col}, count, created_at) VALUES (%s, %s, 1, %s)",
                    [user_id, obj_id, timezone.now()]
                )
            except Exception:
                try:
                    cursor.execute(
                        f"INSERT INTO {table} (user_id, {col}, count) VALUES (%s, %s, 1)",
                        [user_id, obj_id]
                    )
                except Exception:
                    cursor.execute(
                        f"INSERT INTO {table} (user_id, {col}) VALUES (%s, %s)",
                        [user_id, obj_id]
                    )
            liked = True

        # ✅ 해당 항목의 전체 좋아요 수 계산
        cursor.execute(f"SELECT COUNT(*) FROM {table} WHERE {col}=%s", [obj_id])
        count = cursor.fetchone()[0]

    return JsonResponse({"liked": liked, "count": count})


# ✅ 각 항목별로 재사용
@csrf_exempt
@require_POST
def toggle_like_author(request, author_id):
    must = _must_login_json(request)
    if must: return must
    return _toggle_like(request, "like_author", "author_id", author_id)


@csrf_exempt
@require_POST
def toggle_like_affiliation(request, affiliation_id):
    must = _must_login_json(request)
    if must: return must
    return _toggle_like(request, "like_affiliation", "affiliation_id", affiliation_id)


@csrf_exempt
@require_POST
def toggle_like_country(request, country_id):
    must = _must_login_json(request)
    if must: return must
    return _toggle_like(request, "like_country", "country_id", country_id)


@csrf_exempt
@require_POST
def toggle_like_keyword(request, keyword_id):
    must = _must_login_json(request)
    if must: return must
    return _toggle_like(request, "like_keyword", "keyword_id", keyword_id)


# 올라마 정성적 분석을 위한 고귀한 희생
OLLAMA_URL = ""

def analyze_wordcloud(request):
    year = request.GET.get('year')
    part_id = request.GET.get('part_id')

    if not year or not part_id:
        return JsonResponse({"error": "연도와 파트를 선택해야 합니다."}, status=400)

    query_params = [year, part_id]

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT keyword.keyword_name, COUNT(*) AS count
            FROM paper_keyword
            JOIN keyword ON paper_keyword.keyword_id = keyword.id
            JOIN paper ON paper_keyword.paper_id = paper.id
            JOIN paper_part ON paper.id = paper_part.paper_id
            JOIN part ON paper_part.part_id = part.id
            WHERE paper.year = %s AND part.id = %s
            GROUP BY keyword.keyword_name
            ORDER BY count DESC
            LIMIT 30
        """, query_params)
        keyword_data = cursor.fetchall()

    if not keyword_data:
        return JsonResponse({"error": "해당 조건에 맞는 키워드 데이터가 없습니다."}, status=400)

    keyword_text = ", ".join([f"{row[0]}({row[1]})" for row in keyword_data])

    prompt = (
        "다음은 선택한 연구 연도와 특정 연구 분야에서 사용된 키워드와 출현 빈도를 나타냅니다. "
        "이를 바탕으로 주요 연구 주제, 연구 경향 및 관련성 분석을 수행하세요.\n\n"
        f"키워드 데이터: {keyword_text}\n\n"
        "분석할 내용:\n"
        "- 주요 연구 주제 (가장 빈번하게 사용된 키워드와 그 의미)\n"
        "- 관련 키워드 간의 연관성과 연구 방향\n"
        "- 해당 연구 분야의 발전 가능성과 향후 연구 트렌드\n"
        "결과를 논리적이고 객관적인 분석으로 작성해 주세요."
    )

    ollama_data = {
        "model": "gemma",
        "prompt": prompt,
        "stream": False
    }

    headers = {'Content-Type': 'application/json'}

    try:
        response = requests.post(OLLAMA_URL, json=ollama_data, headers=headers)
        response_data = response.json()

        if "response" not in response_data:
            return JsonResponse({"error": "Ollama 응답에 'response' 항목이 없습니다."}, status=500)

        raw = response_data["response"]

        # ✅ HTML 포맷 처리
        formatted = raw.replace("**", "<strong>")  # 굵은 글씨
        formatted = re.sub(r'##\s*(.+)', r'<h5 style="font-size:1.1rem; font-weight:bold; color:#333;">\1</h5>', formatted)  # 제목

        paragraphs = formatted.split('\n')
        formatted_paragraphs = ''.join(
            f"<p style='margin-bottom:10px;'>{line.strip()}</p>" for line in paragraphs if line.strip()
        )

        html_output = f"""
        <div class='analysis-result-box' style='font-size: 0.95rem; line-height: 1.7; background: #fdfdfd; padding: 20px; border-radius: 8px; border: 1px solid #ddd;'>
            {formatted_paragraphs}
        </div>
        """

        return JsonResponse({"analysis": html_output}, json_dumps_params={'ensure_ascii': False})

    except requests.exceptions.RequestException as e:
        return JsonResponse({"error": f"Ollama API 요청 실패: {str(e)}"}, status=500)

##### 인기자료 페이지 뉴스 #####
from .services.news_clients import gnews_search, guardian_search, gdelt_search, naver_search

# ─────────────────────────────────────────────────────────────
# 🔹 제목/키워드 → 뉴스 검색어 정제 & 다중 쿼리 생성
# ─────────────────────────────────────────────────────────────
def _clean_query(text: str, max_tokens=6) -> str:
    """괄호/연도/특수문자 제거 + 앞 n단어만 남기기 (Guardian 400, GNews 403 회피용)"""
    s = re.sub(r"\(.*?\)|\[[^\]]*\]|\b(19|20)\d{2}\b", "", text)  # 괄호/연도 제거
    s = re.sub(r"[^\w\s\-:]", " ", s)                             # 특수문자 제거
    tokens = s.split()
    core = " ".join(tokens[:max_tokens]) if len(tokens) > max_tokens else " ".join(tokens)
    return re.sub(r"\s{2,}", " ", core).strip()


def _make_variants(title: str, keywords: list[str]) -> list[str]:
    t_full = _clean_query(title)                  # 전체 제목 (따옴표 X)
    short = " ".join(t_full.split()[:3])          # 핵심 3단어
    kws = [_clean_query(k, max_tokens=3) for k in keywords if k]
    kws = [k for k in kws if k]

    variants = [
        t_full,                 # ① 전체제목 (느슨)
        f'"{short}"',           # ② 핵심구절 고정 (타이트)
    ]
    if kws:
        variants.append(f'"{short}" {kws[0]}')    # ③ 핵심구절 + 키워드 1개
    return variants

# 불용어(매칭 잡음 줄이기)
STOP = {"the","a","an","of","to","in","for","and","on","with","is","are","from"}

def _tokens_from(title: str, kws: list[str]) -> list[str]:
    """논문 제목+키워드에서 매칭용 토큰 최대 10개 추출"""
    s = _clean_query(title, max_tokens=12)
    base = [w.lower() for w in re.split(r"\W+", s) if w and w.lower() not in STOP]
    extra = []
    for k in kws:
        extra += [w.lower() for w in re.split(r"\W+", k) if w and w.lower() not in STOP]
    # 중복 제거 & 상위 10개만
    seen = []
    for w in base + extra:
        if w not in seen:
            seen.append(w)
    return seen[:10]

def _match_terms(text: str, tokens: list[str]) -> list[str]:
    """기사 제목에 실제로 포함된 토큰만 반환"""
    t = (text or "").lower()
    return [w for w in tokens if w and w in t]

# ─────────────────────────────────────────────────────────────
# 🔹 Paper ↔ Keyword 상위 N개 조회 (스키마: paper_keyword, keyword)
# ─────────────────────────────────────────────────────────────
def _get_top_keywords(paper_id, limit=3):
    """
    가중치 컬럼이 없으므로 '짧은 키워드 우선'으로 정렬(매칭률 개선 목적).
    DB 테이블명/컬럼명은 질문에 주신 스키마와 동일하게 사용.
    """
    SQL = """
    SELECT k.keyword_name
    FROM paper_keyword pk
    JOIN keyword k ON k.id = pk.keyword_id
    WHERE pk.paper_id = %s
    ORDER BY CHAR_LENGTH(k.keyword_name) ASC, k.id ASC
    LIMIT %s
    """
    try:
        with connection.cursor() as c:
            c.execute(SQL, [paper_id, limit])
            return [row[0] for row in c.fetchall()]
    except Exception:
        return []


# ─────────────────────────────────────────────────────────────
# 🔹 캐시 헬퍼 (news_cache 테이블)
# ─────────────────────────────────────────────────────────────
def _get_cached_news(paper_id, query, provider):
    with connection.cursor() as c:
        c.execute("""
          SELECT results_json, expires_at FROM news_cache
          WHERE paper_id=%s AND query=%s AND provider=%s
          ORDER BY id DESC LIMIT 1
        """, [paper_id, query, provider])
        row = c.fetchone()
    if not row:
        return None
    results_json, expires_at = row
    return None if timezone.now() > expires_at else json.loads(results_json)


def _set_cached_news(paper_id, query, provider, results, ttl_hours=6):
    # 빈 결과는 캐시에 저장하지 않음(레이트리밋/일시적 실패 시 재시도 유도)
    if not results:
        return
    with connection.cursor() as c:
        c.execute("""
         INSERT INTO news_cache (paper_id, query, provider, results_json, fetched_at, expires_at)
         VALUES (%s, %s, %s, %s, NOW(), DATE_ADD(NOW(), INTERVAL %s HOUR))
        """, [paper_id, query, provider, json.dumps(results, ensure_ascii=False), ttl_hours])


# ─────────────────────────────────────────────────────────────
# 🔹 뉴스 피드(표 아래 전용 리스트): Top10 논문을 기준으로 모아 반환
# ─────────────────────────────────────────────────────────────
def _as_ts(s: str) -> float:
    """pubDate 문자열을 정렬 가능한 timestamp로 변환 (Naver RFC822, ISO 혼용 대응)"""
    if not s:
        return 0.0
    try:
        return parsedate_to_datetime(s).timestamp()  # RFC822 (Naver)
    except Exception:
        try:
            return datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()  # ISO8601
        except Exception:
            return 0.0

def _build_news_feed(rows, per_paper=2, max_feed=10,
                     foreign_ratio=0.18, foreign_min=1, foreign_max=2):
    """
    네이버 위주(약 80~90%) + 해외(Guardian/GNews) 최소 1~2개 보장.
    - 먼저 전체 Top10을 훑으며 NAVER/FOREIGN 풀에 후보를 충분히 모음
    - 그 다음 비율/최소치 기준으로 합성
    """
    pool_naver, pool_foreign = [], []
    seen = set()
    call_budget = 24  # 호출 상한 살짝 상향

    for (pid, title, _) in rows:
        top_kws  = _get_top_keywords(pid, limit=3)
        variants = _make_variants(title, top_kws)
        tokens   = _tokens_from(title, top_kws)

        for q in variants:
            for provider, fn in [
                ("naver", naver_search),        # 네이버 우선 수집
                ("guardian", guardian_search),  # 해외
                ("gnews", gnews_search),        # 해외
            ]:
                if call_budget <= 0:
                    break

                cached = _get_cached_news(pid, q, provider)
                items = []

                if cached is None:
                    try:
                        ask_n = 6  # 후보 넉넉히
                        if provider == "guardian":
                            items = fn(q, n=ask_n)
                        else:
                            items = fn(q, n=ask_n)
                    finally:
                        call_budget -= 1
                else:
                    items = cached

                if cached is None and items:
                    _set_cached_news(pid, q, provider, items, ttl_hours=6)

                for it in (items or []):
                    key = (it.get("link") or "") or it.get("title")
                    if not key or key in seen:
                        continue

                    # 매칭 기준: NAVER는 한글 제목이 많으므로 0개 허용, 해외는 ≥1
                    matched = _match_terms((it.get("title") or ""), tokens)
                    min_needed = 0 if provider == "naver" else 1
                    if len(matched) < min_needed:
                        continue

                    seen.add(key)
                    entry = {
                        "title": it.get("title"),
                        "link": it.get("link"),
                        "pubDate": it.get("pubDate"),
                        "source": it.get("source"),
                        "provider": provider,
                        "paper_title": title,
                        "paper_id": pid,
                        "matched": matched if provider != "naver" else [],
                        "match_mode": "strict" if provider != "naver" and matched else "loose",
                        "ts": _as_ts(it.get("pubDate")),
                    }
                    if provider == "naver":
                        pool_naver.append(entry)
                    else:
                        pool_foreign.append(entry)

            # 풀 크기가 충분해지면 다음 논문으로 (불필요한 호출 방지)
            if len(pool_naver) + len(pool_foreign) >= max_feed * 3 or call_budget <= 0:
                break

        if len(pool_naver) + len(pool_foreign) >= max_feed * 3 or call_budget <= 0:
            break

    # 1) 각 풀을 최신순 정렬
    pool_naver.sort(key=lambda x: x["ts"], reverse=True)
    pool_foreign.sort(key=lambda x: x["ts"], reverse=True)

    # 2) 비율/최소치 계산 (해외 최소 1~2개, 목표 18% 정도)
    target_foreign = max(foreign_min, min(foreign_max, int(round(max_feed * foreign_ratio)) or 1))

    # 3) 패턴 혼합: 대체로 네이버 4~5개당 해외 1개 섞기
    out, i_n, i_f = [], 0, 0
    naver_since_foreign = 0
    while len(out) < max_feed and (i_n < len(pool_naver) or i_f < len(pool_foreign)):
        # 해외 최소 달성 전이면 가능한 한 해외를 우선 섞기
        foreign_so_far = sum(1 for x in out if x["provider"] != "naver")
        need_foreign = foreign_so_far < target_foreign

        if need_foreign and i_f < len(pool_foreign):
            out.append(pool_foreign[i_f]); i_f += 1
            naver_since_foreign = 0
            continue

        # 기본은 네이버 채우기
        if i_n < len(pool_naver):
            out.append(pool_naver[i_n]); i_n += 1
            naver_since_foreign += 1
            # 네이버를 연속으로 4~5개 뽑았고 해외가 남아 있으면 하나 섞기
            if naver_since_foreign >= 5 and i_f < len(pool_foreign) and len(out) < max_feed:
                out.append(pool_foreign[i_f]); i_f += 1
                naver_since_foreign = 0
            continue

        # 네이버가 부족하면 해외로 채움
        if i_f < len(pool_foreign):
            out.append(pool_foreign[i_f]); i_f += 1

    # 4) 출력 정리
    for x in out:
        x.pop("ts", None)
    return out[:max_feed]



# ─────────────────────────────────────────────────────────────
# 🔹 인기 자료 페이지
# ─────────────────────────────────────────────────────────────
@cache_page(60 * 5)
def popular_papers_page(request):
    with connection.cursor() as cursor:
        cursor.execute("""
          SELECT p.id, p.title, COUNT(sp.paper_id) AS save_count
          FROM savedpaper sp
          JOIN paper p ON sp.paper_id = p.id
          GROUP BY sp.paper_id, p.id, p.title
          ORDER BY save_count DESC, p.id ASC
          LIMIT 10
        """)
        rows = cursor.fetchall()

    papers = [{'id': r[0], 'title': r[1], 'save_count': r[2]} for r in rows]


    return render(request, 'popular_papers.html', {
        'popular_papers': papers,
    })

def popular_news_feed_api(request):
    cache_key = "popular_news_feed_v1"
    if request.GET.get("refresh") == "1":
        cache.delete(cache_key)

    data = cache.get(cache_key)
    if data is None:
        with connection.cursor() as cursor:
            cursor.execute("""
              SELECT p.id, p.title, COUNT(sp.paper_id) AS save_count
              FROM savedpaper sp
              JOIN paper p ON sp.paper_id = p.id
              GROUP BY sp.paper_id, p.id, p.title
              ORDER BY save_count DESC, p.id ASC
              LIMIT 10
            """)
            rows = cursor.fetchall()
        data = _build_news_feed(rows, per_paper=2, max_feed=10)
        cache.set(cache_key, data, 60 if not data else 60*30)  # 빈 결과 60초, 정상 30분
    return JsonResponse(data, safe=False)