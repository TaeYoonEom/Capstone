from django.db import models

# ✅ 나라
class Country(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    alpha_2 = models.CharField(max_length=2)
    alpha_3 = models.CharField(max_length=3)

    class Meta:
        managed = False
        db_table = 'country'


# ✅ 기관
class Affiliation(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    country_id = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, db_column='country_id')

    class Meta:
        managed = False
        db_table = 'affiliation'


# ✅ 논문
class Paper(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.TextField()
    year = models.IntegerField()
    citation = models.IntegerField()
    site = models.TextField()
    published_in = models.CharField(max_length=255)
    abstract = models.TextField()

    class Meta:
        managed = False
        db_table = 'paper'


# ✅ 키워드
class Keyword(models.Model):
    id = models.AutoField(primary_key=True)
    keyword_name = models.TextField()

    class Meta:
        managed = False
        db_table = 'keyword'


# ✅ 파트
class Part(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()

    class Meta:
        managed = False
        db_table = 'part'


# ✅ 저자
class Author(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()

    class Meta:
        managed = False
        db_table = 'author'


# ✅ 논문-기관 관계
class Paper_affiliation(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    affiliation_id = models.ForeignKey(Affiliation, on_delete=models.CASCADE, db_column='affiliation_id')

    class Meta:
        managed = False
        db_table = 'paper_affiliation'


# ✅ 논문-키워드 관계
class Paper_keyword(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    keyword_id = models.ForeignKey(Keyword, on_delete=models.CASCADE, db_column='keyword_id')

    class Meta:
        managed = False
        db_table = 'paper_keyword'


# ✅ 논문-파트 관계
class Paper_part(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    part_id = models.ForeignKey(Part, on_delete=models.CASCADE, db_column='part_id')

    class Meta:
        managed = False
        db_table = 'paper_part'


# ✅ 논문-저자 관계
class Paper_author(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    author_id = models.ForeignKey(Author, on_delete=models.CASCADE, db_column='author_id')

    class Meta:
        managed = False
        db_table = 'paper_author'


# ✅ 기관 좋아요
class Like_Affiliation(models.Model):
    id = models.AutoField(primary_key=True)
    affiliation_id = models.ForeignKey(Affiliation, on_delete=models.CASCADE, db_column='affiliation_id')
    user_id = models.IntegerField()
    count = models.IntegerField(default=0)

    class Meta:
        managed = False
        db_table = 'like_affiliation'
        unique_together = ('affiliation_id', 'user_id')
