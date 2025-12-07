from django.db import models
from django.utils import timezone


class User(models.Model):
    id = models.AutoField(primary_key=True)
    user_name = models.CharField(max_length=150)
    email = models.CharField(max_length=254)

    class Meta:
        managed = False
        db_table = 'user'


class Country(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    alpha_2 = models.CharField(max_length=2)
    alpha_3 = models.CharField(max_length=3)

    class Meta:
        managed = False
        db_table = 'country'


class Affiliation(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    country_id = models.ForeignKey(Country, on_delete=models.SET_NULL, null=True, db_column='country_id')

    class Meta:
        managed = False
        db_table = 'affiliation'


class Author(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()
    affiliation = models.TextField()

    class Meta:
        managed = False
        db_table = 'author'


class Paper(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.TextField()
    abstract = models.TextField()
    citation = models.IntegerField()
    year = models.IntegerField()
    published_in = models.CharField(max_length=255)
    site = models.TextField()

    class Meta:
        managed = False
        db_table = 'paper'


class Paper_affiliation(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    affiliation_id = models.ForeignKey(Affiliation, on_delete=models.CASCADE, db_column='affiliation_id')

    class Meta:
        managed = False
        db_table = 'paper_affiliation'


class Keyword(models.Model):
    id = models.AutoField(primary_key=True)
    keyword_name = models.TextField()

    class Meta:
        managed = False
        db_table = 'keyword'


class Paper_keyword(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id', related_name='keyword_papers')
    keyword_id = models.ForeignKey(Keyword, on_delete=models.CASCADE, db_column='keyword_id')

    class Meta:
        managed = False
        db_table = 'paper_keyword'


class Part(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.TextField()

    class Meta:
        managed = False
        db_table = 'part'


class Paper_part(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id', related_name='part_papers')
    part_id = models.ForeignKey(Part, on_delete=models.CASCADE, db_column='part_id')

    class Meta:
        managed = False
        db_table = 'paper_part'


class Paper_country(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    country_id = models.ForeignKey(Country, on_delete=models.CASCADE, db_column='country_id')

    class Meta:
        managed = False
        db_table = 'paper_country'


class SavedPaper(models.Model):
    id = models.AutoField(primary_key=True)
    user_id = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    part_id = models.ForeignKey(Part, on_delete=models.CASCADE, db_column='part_id')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = 'savedpaper'

class Paper_author(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id', related_name='author_papers')
    author_id = models.ForeignKey(Author, on_delete=models.CASCADE, db_column='author_id')

    class Meta:
        managed = False
        db_table = 'paper_author'
