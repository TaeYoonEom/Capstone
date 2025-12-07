"""
URL configuration for capstone project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path('', include('main.urls')),
    path('paper/', include('paper.urls')), # paper 앱으로 
    path('author/', include('author.urls')), # author 앱으로로
    path('affiliation/', include('affiliation.urls')),# affiliation 앱으로
    path('country/', include('country.urls')),# country 앱으로
    path('keyword/', include('keywords.urls')),#keywords 앱으로로
]
