from django.urls import path
from . import views

urlpatterns = [
    path('<int:keyword_id>/', views.keyword_page, name='keyword_page'),
    path('get_saved_papers/', views.get_saved_papers, name='get_saved_papers'),
    path('save_paper/', views.save_paper, name='save_paper'),
    path('like_keyword/<int:keyword_id>/', views.like_keyword, name='like_keyword'),
    path('pdf_upload/', views.pdf_upload_view, name='pdf_upload_view'),
    path('api/analyze_keyword/<int:keyword_id>/', views.analyze_keyword, name='analyze_keyword'),
]
