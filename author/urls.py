# author/urls.py
from django.urls import path
from . import views

urlpatterns = [
    path('<int:author_id>/', views.author_page, name='author_page'),
    path('api/<int:author_id>/', views.author_analysis_api, name='author_analysis_api'),
    path('like_author/<int:author_id>/', views.like_author, name='like_author'),
    path('api/analyze_author/<int:author_id>/', views.analyze_author, name='analyze_author'),  # ✅ 이 라인!
    path('save_paper/', views.save_paper, name='save_paper'),
    path('get_saved_papers/', views.get_saved_papers, name='get_saved_papers'),
    path('pdf_upload/', views.pdf_upload_view, name='pdf_upload'),
]
