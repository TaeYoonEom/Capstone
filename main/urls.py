from django.urls import path, include
from . import views
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', views.main, name='main'),  # 루트 URL
    path('introduction/', views.introduction, name='introduction'),  # 기업 소개개 페이지
    path('analysis/', views.analysis, name='analysis'),  # 분석 페이지
    path('get_wordcloud_data/', views.get_wordcloud_data, name='get_wordcloud_data'), # 분석 페이지 워드 클라우드
    path('get_keyword_id/', views.get_keyword_id, name='get_keyword_id'), #분석 페이지 워드 클라우드
    path('get_rankings/<int:year>/', views.get_rankings, name='get_rankings'),  # 연도별 파트 & 키워드 순위 데이터
    path('part_paper/', views.part_paper_page, name='part_paper_page'), #주제별 논문 페이지
    path('get_papers_by_part/<int:part_id>/', views.get_papers_by_part, name='get_papers_by_part'),
    path('popular_papers/', views.popular_papers_page, name='popular_papers_page'), # ✅ 인기 자료 페이지
    path('popular_papers/news_feed/', views.popular_news_feed_api, name='popular_news_feed_api'),  # ✅ 인기 자료 뉴스 
    path('search/', include('search.urls')),
    path("", include("paper.urls")),
    

    # 메인페이지 시각화
    path('part_pie_chart/', views.part_pie_chart_view, name='part_pie_chart'), #메인 페이지 실시간 파트 수 
    path('keyword_cloud_data/', views.keyword_cloud_data, name='keyword_cloud_data'), # 메인 페이지 등록 논문 키워드
    path('get_affiliation_count/', views.get_affiliation_count, name='get_affiliation_count'), #메인 페이지 학회 수
    path('get_paper_count/', views.get_paper_count, name='get_paper_count'), # 메인페이지 학술 논문 수
    path('get_user_count/', views.get_user_count, name='get_user_count'), #메인페이지 사용자 수
    path('get_top_saved_parts/', views.get_top_saved_parts, name='get_top_saved_parts'), #실시간 파트 수
    path('register/', views.register_page, name='register_page'),  # 페이지 로딩용 뷰
    path('register_user/', views.register_user, name='register_user'),  # 회원가입 처리용 뷰
    path('check_username/', views.check_username, name='check_username'),
    path('login/', views.login_page, name='login_page'),
    path('login_user/', views.login_user, name='login_user'),
    path('find_user_id/', views.find_user_id, name='find_user_id'),
    path('reset_password/', views.reset_password, name='reset_password'),
    path('logout/', views.logout_user, name='logout_user'),


    # 마이페이지
    path('mypage/', views.mypage_view, name='mypage'), #마이페이지
    path('liked-items/', views.liked_items_view, name='liked_items'), #좋아요한 논문/저자
    path('recommended_papers/', views.recommended_papers_view, name='recommended_papers'),  # ✅ 추천 논문 조회
    path('user_saved_pdfs/', views.user_saved_pdfs, name='user_saved_pdfs'), # ✅ 사용자가 저장한 PDF 목록 조회
    path('delete_saved_pdf/', views.delete_saved_pdf, name='delete_saved_pdf'),  # ✅ 저장된 PDF 삭제
    path("remove_saved_paper/", views.remove_saved_paper, name="remove_saved_paper"),
    path('change_password/', views.change_password, name='change_password'),
    path('api/analyze_wordcloud/', views.analyze_wordcloud, name='analyze_wordcloud'), #분석 페이지 정성적 분석

    # 좋아요 토글 (POST)
    path('like_author/<int:author_id>/', views.toggle_like_author, name='like_author'),
    path('like_affiliation/<int:affiliation_id>/', views.toggle_like_affiliation, name='like_affiliation'),
    path('like_country/<int:country_id>/', views.toggle_like_country, name='like_country'),
    path('like_keyword/<int:keyword_id>/', views.toggle_like_keyword, name='like_keyword'),


]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)  
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    