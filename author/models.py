from django.db import models

class Author(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    affiliation = models.TextField()

    class Meta:
        db_table = 'author'
        managed = False


class Paper(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.TextField()
    year = models.IntegerField()
    citation = models.IntegerField(null=True)
    abstract = models.TextField()
    published_in = models.CharField(max_length=255)
    
    class Meta:
        db_table = 'paper'
        managed = False


class Paper_author(models.Model):
    id = models.AutoField(primary_key=True)
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    author = models.ForeignKey(Author, on_delete=models.CASCADE, db_column='author_id')

    class Meta:
        db_table = 'paper_author'
        managed = False


class Paper_part(models.Model):
    id = models.AutoField(primary_key=True)
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    part_id = models.ForeignKey('Part', on_delete=models.CASCADE, db_column='part_id')

    class Meta:
        db_table = 'paper_part'
        managed = False


class Part(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()

    class Meta:
        db_table = 'part'
        managed = False


class Paper_keyword(models.Model):
    id = models.AutoField(primary_key=True)
    paper = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    keyword_id = models.ForeignKey('Keyword', on_delete=models.CASCADE, db_column='keyword_id')

    class Meta:
        db_table = 'paper_keyword'
        managed = False


class Keyword(models.Model):
    id = models.AutoField(primary_key=True)
    keyword_name = models.TextField()

    class Meta:
        db_table = 'keyword'
        managed = False


class Affiliation(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    country = models.ForeignKey('Country', on_delete=models.SET_NULL, null=True, db_column='country_id')

    class Meta:
        db_table = 'affiliation'
        managed = False


class Country(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()

    class Meta:
        db_table = 'country'
        managed = False


class Like_Author(models.Model):
    id = models.AutoField(primary_key=True)
    author = models.ForeignKey(Author, on_delete=models.CASCADE, db_column='author_id')
    user_id = models.IntegerField()  # ForeignKey 안 써도 무방 (user 테이블 직접 참조 안 할 경우)
    count = models.IntegerField(default=0)

    class Meta:
        db_table = 'like_author'
        managed = False
        unique_together = ('author', 'user_id')
