from django.urls import path
from . import views

urlpatterns = [
    path('<int:country_id>/', views.country_page, name='country_page'),
    path('api/country-analysis/<int:country_id>/', views.country_analysis_api, name='country_analysis_api'),
    path('api/analyze_country/<int:country_id>/', views.analyze_country, name='analyze_country'),
    path('like_country/<int:country_id>/', views.like_country, name='like_country'),
    path('get_saved_papers/', views.get_saved_papers, name='get_saved_papers'),
    path('pdf_upload/', views.pdf_upload_view, name='pdf_upload'),
    path('save_paper/', views.save_paper, name='save_paper'),
    
]
