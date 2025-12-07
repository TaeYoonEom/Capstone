from django.urls import path
from . import views

urlpatterns = [
    path('', views.search, name='search'),

    path('like_paper/<int:item_id>/',       views.like_paper,       name='like_paper'),
    path('like_author/<int:item_id>/',      views.like_author,      name='like_author'),
    path('like_keyword/<int:item_id>/',     views.like_keyword,     name='like_keyword'),
    path('like_country/<int:item_id>/',     views.like_country,     name='like_country'),
    path('like_affiliation/<int:item_id>/', views.like_affiliation, name='like_affiliation'),

]