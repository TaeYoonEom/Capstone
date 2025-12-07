from django.shortcuts import render
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection, transaction
from django.utils import timezone
from django.core.paginator import Paginator
from django.contrib.auth import get_user_model
import json
import os
from django.contrib.auth.decorators import login_required
from django.conf import settings
from main.models import (
    Paper, Paper_part, Paper_keyword, Paper_author,
    SavedPaper, RecentPaper, Like_Paper
)
from main.models import Part, Keyword, Author, Affiliation

# 논문 상세 페이지
def paper_page(request, paper_id):
    # 1) 특정 논문 객체를 가져옴 (존재하지 않으면 404 에러)
    paper = get_object_or_404(Paper, id=paper_id)
    user_id = request.session.get('user_id')  # 현재 로그인한 사용자 ID

    # 2) 로그인한 사용자의 경우 최근 본 논문 리스트에 현재 논문 저장
    if user_id:
        try:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    # 기존에 본 논문인지 확인
                    cursor.execute(
                        "SELECT id FROM recentpaper WHERE user_id = %s AND paper_id = %s",
                        [user_id, paper_id]
                    )
                    existing = cursor.fetchone()

                    if existing:
                        # 이미 본 논문이면 시간만 업데이트
                        cursor.execute(
                            "UPDATE recentpaper SET viewed_at = %s WHERE id = %s",
                            [timezone.now(), existing[0]]
                        )
                    else:
                        # 처음 본 논문이면 새로 삽입
                        cursor.execute(
                            "INSERT INTO recentpaper (user_id, paper_id, viewed_at) VALUES (%s, %s, %s)",
                            [user_id, paper_id, timezone.now()]
                        )

                    # 최근 본 논문이 10개를 넘으면 가장 오래된 항목 삭제
                    cursor.execute(
                        "SELECT id FROM recentpaper WHERE user_id = %s ORDER BY viewed_at DESC",
                        [user_id]
                    )
                    recent_papers = cursor.fetchall()
                    if len(recent_papers) > 10:
                        oldest_id = recent_papers[-1][0]
                        cursor.execute("DELETE FROM recentpaper WHERE id = %s", [oldest_id])
        except Exception as e:
            print(f"❌ 최근 본 논문 저장 실패: {e}")

    # 3) 논문에 연결된 파트와 키워드 ID 목록을 가져옴
    part_ids = Paper_part.objects.filter(paper_id=paper).values_list('part_id', flat=True)
    keyword_ids = Paper_keyword.objects.filter(paper_id=paper).values_list('keyword_id', flat=True)

    # 4) 해당 파트 이름과 최대 5개의 키워드 객체를 조회
    parts = Part.objects.filter(id__in=part_ids).values_list('name', flat=True)
    keywords = Keyword.objects.filter(id__in=keyword_ids)[:5]

    # 5) 논문 저자 정보(ID, 이름, 소속)를 가져옴
    author_ids = Paper_author.objects.filter(paper_id=paper_id).values_list('author_id', flat=True)
    authors = Author.objects.filter(id__in=author_ids).only('id', 'name', 'affiliation')

    # 6) 각 저자의 소속 기관을 통해 국가 정보를 가져오고, 중복 제거
    author_countries = set()
    for author in authors:
        affiliation = Affiliation.objects.filter(name=author.affiliation).first()
        author.country = affiliation.country_id.name if affiliation and affiliation.country_id else "정보 없음"
        if author.country != "정보 없음":
            author_countries.add(author.country)

    # 7) 해당 논문이 포함된 국가 리스트로 변환
    country = list(author_countries)

    # 8) 좋아요 수 및 로그인 사용자의 좋아요 여부 확인
    with connection.cursor() as cursor:
        cursor.execute("SELECT COUNT(*) FROM like_paper WHERE paper_id = %s", [paper_id])
        like_count = cursor.fetchone()[0]

        if user_id:
            cursor.execute("SELECT COUNT(*) FROM like_paper WHERE user_id = %s AND paper_id = %s", [user_id, paper_id])
            user_liked = cursor.fetchone()[0] > 0
        else:
            user_liked = False

    # 9) 연관 논문 검색: 동일한 키워드와 파트를 모두 포함하는 논문만 가져옴
    related_paper_ids = Paper_keyword.objects.filter(
        keyword_id__in=keyword_ids
    ).values_list('paper_id', flat=True)

    related_paper_ids = Paper_part.objects.filter(
        paper_id__in=related_paper_ids, part_id__in=part_ids
    ).exclude(paper_id=paper.id).values_list('paper_id', flat=True)

    papers_list = Paper.objects.filter(id__in=related_paper_ids).order_by('-year')

    # 10) 연관 논문 리스트에 대한 페이지네이션 처리
    items_per_page = request.GET.get('items_per_page', 10)
    paginator = Paginator(papers_list, items_per_page)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    page_range = list(paginator.get_elided_page_range(number=page_obj.number, on_each_side=2, on_ends=1))

    # 11) 최종적으로 템플릿에 전달할 데이터를 context에 담아서 렌더링
    return render(request, 'paper/paper_page.html', {
        'paper': paper,                     # 논문 객체
        'parts': parts,                     # 논문 파트명 리스트
        'keywords': keywords,               # 키워드 리스트 (최대 5개)
        'authors': authors,                 # 저자 객체 리스트
        'country': country,                 # 논문과 관련된 국가 리스트 (중복 제거)
        'like_count': like_count,           # 좋아요 수
        'user_liked': user_liked,           # 사용자의 좋아요 여부
        'page_obj': page_obj,               # 페이지네이션 객체
        'page_range': page_range,           # 페이지 번호 범위
        'items_per_page': items_per_page,   # 한 페이지당 논문 수
        'content_type': 'paper',            # PDF 저장을 위한 content type
        'object_id': paper.id,              # PDF 저장용 객체 ID
        'page_title': paper.title[:30],     # 페이지 제목 (최대 30자)
    })

# 최근 본 논문 저장
def save_recent_paper(request, paper_id):  # 최근 본 논문
    user_id = request.session.get('user_id')

    if not user_id:
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)

    try:
        with transaction.atomic():  # 🔹 트랜잭션 적용
            with connection.cursor() as cursor:
                # 1. 이미 저장된 동일 논문 조회 여부 확인
                cursor.execute(
                    "SELECT id FROM recentpaper WHERE user_id = %s AND paper_id = %s",
                    [user_id, paper_id]
                )
                existing_paper = cursor.fetchone()

                if existing_paper:
                    # 2. 동일 논문이 있을 경우, viewed_at만 업데이트
                    cursor.execute(
                        "UPDATE recentpaper SET viewed_at = %s WHERE id = %s",
                        [timezone.now(), existing_paper[0]]
                    )
                    print("♻️ 기존 논문 조회 기록 업데이트")
                else:
                    # 3. 새로운 논문 조회 기록 추가
                    cursor.execute(
                        "INSERT INTO recentpaper (user_id, paper_id, viewed_at) VALUES (%s, %s, %s)",
                        [user_id, paper_id, timezone.now()]
                    )
                    print("✅ 새로운 조회 기록 추가")

                # 4. 사용자의 최근 논문 개수 확인 (최신순 정렬)
                cursor.execute(
                    "SELECT id FROM recentpaper WHERE user_id = %s ORDER BY viewed_at DESC",
                    [user_id]
                )
                recent_papers = cursor.fetchall()

                # 5. 11개 초과 시 가장 오래된 논문 삭제
                if len(recent_papers) > 10:
                    oldest_paper_id = recent_papers[-1][0]  # 🔹 가장 오래된 논문 ID
                    cursor.execute(
                        "DELETE FROM recentpaper WHERE id = %s",  # ✅ id 기준으로 삭제
                        [oldest_paper_id]
                    )
                    print("🗑️ 오래된 논문 삭제")

        return JsonResponse({"message": "최근 본 논문이 저장되었습니다."}, status=200)

    except Exception as e:
        print(f"❌ [ERROR] {str(e)}")  # ✅ 오류 로그 추가
        return JsonResponse({"error": str(e)}, status=500)
    
# 좋아요

User = get_user_model()

def like_paper(request, paper_id):
    """좋아요 추가 및 취소 기능"""
    user_id = request.session.get('user_id')  # ✅ 세션에서 user_id 가져오기

    if not user_id:
        return JsonResponse({"error": "로그인이 필요합니다."}, status=401)  # 🔥 로그인 필요 시 401 응답

    with connection.cursor() as cursor:
        # ✅ 1. 현재 사용자의 좋아요 여부 확인
        cursor.execute("""
            SELECT count FROM like_paper WHERE user_id = %s AND paper_id = %s
        """, [user_id, paper_id])
        row = cursor.fetchone()  # 결과 가져오기

        if row is None:
            # ✅ 좋아요가 없는 경우 → 새로 추가
            cursor.execute("""
                INSERT INTO like_paper (user_id, paper_id, count) VALUES (%s, %s, 1)
            """, [user_id, paper_id])
            like_count = 1  # 새로 추가된 경우 count = 1
            liked = True  # ✅ 좋아요 상태

        else:
            # ✅ 이미 좋아요를 눌렀다면 → 삭제 (좋아요 취소)
            cursor.execute("""
                DELETE FROM like_paper WHERE user_id = %s AND paper_id = %s
            """, [user_id, paper_id])
            like_count = 0  # 좋아요 삭제 시 count = 0
            liked = False  # ✅ 좋아요 취소 상태

        # ✅ 최종 좋아요 개수 가져오기
        cursor.execute("""
            SELECT COUNT(*) FROM like_paper WHERE paper_id = %s
        """, [paper_id])
        total_likes = cursor.fetchone()[0]  # 해당 논문의 총 좋아요 수 가져오기

    # ✅ JSON 응답 반환
    return JsonResponse({"liked": liked, "count": total_likes})

#논문 저장 목록 조회
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

# 논문 저장

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