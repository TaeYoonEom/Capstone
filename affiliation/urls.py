# affiliation/urls.py

from django.urls import path
from . import views

urlpatterns = [
    path('<int:affiliation_id>/', views.affiliation_page, name='affiliation_page'),
    path('like_affiliation/<int:affiliation_id>/', views.like_affiliation, name='like_affiliation'),
    path('save_paper/', views.save_paper, name='save_paper'),
    path('get_saved_papers/', views.get_saved_papers, name='get_saved_papers'),
    path('pdf_upload/', views.pdf_upload_view, name='pdf_upload'),
    path('api/affiliation-analysis/<int:affiliation_id>/', views.affiliation_analysis_api, name='affiliation_analysis_api'),
    path('api/analyze_affiliation/<int:affiliation_id>/', views.analyze_affiliation, name='analyze_affiliation'),

]
