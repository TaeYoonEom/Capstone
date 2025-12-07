from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.models import AbstractUser
from datetime import timedelta

class User(models.Model): #유저
    id = models.AutoField(primary_key=True) 
    password = models.CharField(max_length=128)
    last_login = models.DateTimeField(blank=True, null=True)
    user_name = models.CharField(unique=True, max_length=150)
    email = models.CharField(max_length=254)
    date_joined = models.DateTimeField()

    class Meta:
        db_table = 'user'


class Paper(models.Model): #논문
    id = models.AutoField(primary_key=True)  
    search_keyword = models.TextField()
    title = models.TextField()
    year = models.IntegerField() 
    citation = models.IntegerField()  
    site = models.TextField()
    paper_url = models.TextField(unique=True)
    published_in = models.CharField(max_length=255)  
    abstract = models.TextField() 
    saved_count = models.IntegerField(default=0)  

    class Meta:
        db_table = 'paper'  
        indexes = [
            models.Index(fields=['year', 'citation'], name='idx_paper_year_cit'),
            models.Index(fields=['published_in'], name='idx_paper_pubin'),
        ]


class Part(models.Model): #파트
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    part_count = models.IntegerField(default=0)  

    class Meta:
        db_table = 'part'

class Country(models.Model): #나라
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    alpha_2 = models.CharField(max_length=2)
    alpha_3 = models.CharField(max_length=3)

    class Meta:
        db_table = 'country'
        

class Affiliation(models.Model): #기관
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    country_id = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, db_column='country_id')

    class Meta:
        db_table = 'affiliation'


class Keyword(models.Model):  # 키워드
    id = models.AutoField(primary_key=True)
    keyword_name = models.TextField(unique=True)  # ✅ 중복 방지 추가

    class Meta:
        db_table = 'keyword'


class Searchkeyword(models.Model):
    id = models.AutoField(primary_key=True)
    keyword = models.TextField()
    count = models.IntegerField(default=0)  

    class Meta:
        db_table = 'searchkeyword'


class Author(models.Model): #저자
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    affiliation = models.TextField()

    class Meta:
        db_table = 'author'



class Paper_part(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='part_papers', db_column='paper_id')  
    part_id = models.ForeignKey(Part, on_delete=models.CASCADE, related_name='part_parts', db_column='part_id')  

    class Meta:
        db_table = 'paper_part'  
        indexes = [
            models.Index(fields=['paper_id', 'part_id'], name='idx_pp_paper_part'),
        ]

class Paper_affiliation(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='affiliation_papers', db_column='paper_id')  
    affiliation_id = models.ForeignKey(Affiliation, on_delete=models.CASCADE, related_name='affiliation_keywords', db_column='affiliation_id')  

    class Meta:
        db_table = 'paper_affiliation'  
        indexes = [
            models.Index(fields=['affiliation_id', 'paper_id'], name='idx_pa_aff_paper'),
            models.Index(fields=['paper_id', 'affiliation_id'], name='idx_pa_paper_aff'),
        ]

class Paper_keyword(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='keyword_papers', db_column='paper_id')  
    keyword_id = models.ForeignKey(Keyword, on_delete=models.CASCADE, related_name='keyword_keywords', db_column='keyword_id')  

    class Meta:
        db_table = 'paper_keyword' 
        indexes = [
            models.Index(fields=['paper_id', 'keyword_id'], name='idx_pk_paper_kw'),
            models.Index(fields=['keyword_id', 'paper_id'], name='idx_pk_kw_paper'),
        ]

class Paper_author(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='author_papers', db_column='paper_id')  
    author_id = models.ForeignKey(Author, on_delete=models.CASCADE, related_name='author_authors', db_column='author_id')  

    class Meta:
        db_table = 'paper_author' 
        indexes = [
            models.Index(fields=['paper_id', 'author_id'], name='idx_pap_paper_author'),
        ]
    
class Paper_country(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, related_name='country_papers', db_column='paper_id')  
    country_id = models.ForeignKey(Country, on_delete=models.CASCADE, related_name='country_countrys', db_column='country_id')  

    class Meta:
        db_table = 'paper_country' 


class SavedPaper(models.Model):
    id = models.AutoField(primary_key=True)
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')  # ✅ User 직접 참조
    paper_id = models.ForeignKey("Paper", on_delete=models.CASCADE, db_column='paper_id')
    part_id = models.ForeignKey("Part", on_delete=models.CASCADE, db_column='part_id')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'savedpaper'

class RecentPaper(models.Model):
    id = models.AutoField(primary_key=True)
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')  # ✅ User 직접 참조
    paper_id = models.ForeignKey("Paper", on_delete=models.CASCADE, db_column='paper_id')
    viewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-viewed_at']
        db_table = 'recentpaper'


class Like_Paper(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    count = models.IntegerField(default=0)  # 기본값 0

    class Meta:
        db_table = 'like_paper'
        unique_together = ('paper_id', 'user_id')

class Like_Author(models.Model):
    id = models.AutoField(primary_key=True)
    author_id = models.ForeignKey(Author, on_delete=models.CASCADE, db_column='author_id')
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    count = models.IntegerField(default=0)

    class Meta:
        db_table = 'like_author'
        unique_together = ('author_id', 'user_id')

class Like_Affiliation(models.Model):
    id = models.AutoField(primary_key=True)
    affiliation_id = models.ForeignKey(Affiliation, on_delete=models.CASCADE, db_column='affiliation_id')
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    count = models.IntegerField(default=0)

    class Meta:
        db_table = 'like_affiliation'
        unique_together = ('affiliation_id', 'user_id')

class Like_Country(models.Model):
    id = models.AutoField(primary_key=True)
    country_id = models.ForeignKey(Country, on_delete=models.CASCADE, db_column='country_id')
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    count = models.IntegerField(default=0)

    class Meta:
        db_table = 'like_country'
        unique_together = ('country_id', 'user_id')

class Like_Keyword(models.Model):
    id = models.AutoField(primary_key=True)
    keyword_id = models.ForeignKey(Keyword, on_delete=models.CASCADE, db_column='keyword_id')
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    count = models.IntegerField(default=0)

    class Meta:
        db_table = 'like_keyword'
        unique_together = ('keyword_id', 'user_id')


class PaperEmbedding(models.Model):
    paper = models.OneToOneField(Paper, on_delete=models.CASCADE, related_name='embedding')
    vector = models.JSONField(null=True, blank=True)          # fp16 리스트
    # 선택: 정규화된 벡터(분모 제거용)
    norm_vector = models.JSONField(null=True, blank=True)     # fp16 리스트
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'paper_embedding'


# 뉴스 캐시 
# ✅ expires_at 기본값을 계산하는 최상위 함수
def default_expires_at():
    return timezone.now() + timedelta(hours=6)

class NewsCache(models.Model):
    PROVIDERS = [
        ("gnews", "GNews"),
        ("guardian", "Guardian"),
        ("gdelt", "GDELT"),
        ("newsapi", "NewsAPI"),
    ]

    paper_id = models.BigIntegerField()  # 필요 시 ForeignKey(Paper)로 교체 가능
    query = models.CharField(max_length=500)
    provider = models.CharField(max_length=20, choices=PROVIDERS)
    results_json = models.JSONField()

    fetched_at = models.DateTimeField(default=timezone.now)  # 생성 시각
    expires_at = models.DateTimeField(default=default_expires_at)  # ✅ 람다 → 함수로 변경

    class Meta:
        db_table = "news_cache"
        indexes = [
            models.Index(fields=["paper_id", "query", "provider"]),
            models.Index(fields=["expires_at"]),
        ]