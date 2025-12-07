# paper/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('<int:paper_id>/', views.paper_page, name='paper_page'),
    path('save_recent_paper/<int:paper_id>/', views.save_recent_paper, name='save_recent_paper'),
    path('like_paper/<int:paper_id>/', views.like_paper, name='like_paper'),
    path('get_saved_papers/', views.get_saved_papers, name='get_saved_papers'),
    path('save_paper/', views.save_paper, name='save_paper'),
    path('pdf_upload/', views.pdf_upload_view, name='pdf_upload'),
]
