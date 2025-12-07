from django.db import models
from django.utils import timezone

class Paper(models.Model):
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
        managed = False


class Paper_part(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    part_id = models.ForeignKey('main.Part', on_delete=models.CASCADE, db_column='part_id', related_name='saved_parts_in_paper_app')

    class Meta:
        db_table = 'paper_part'
        managed = False


class Paper_keyword(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    keyword_id = models.ForeignKey('main.Keyword', on_delete=models.CASCADE, db_column='keyword_id')

    class Meta:
        db_table = 'paper_keyword'
        managed = False


class Paper_author(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    author_id = models.ForeignKey('main.Author', on_delete=models.CASCADE, db_column='author_id')

    class Meta:
        db_table = 'paper_author'
        managed = False


class SavedPaper(models.Model):
    id = models.AutoField(primary_key=True)
    user_id = models.ForeignKey('main.User', on_delete=models.CASCADE, db_column='user_id', related_name='saved_papers_in_paper_app')
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    part_id = models.ForeignKey('main.Part', on_delete=models.CASCADE, db_column='part_id', related_name='saved_papers_in_paper_app')
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'savedpaper'
        managed = False


class RecentPaper(models.Model):
    id = models.AutoField(primary_key=True)
    user_id = models.ForeignKey('main.User', on_delete=models.CASCADE, db_column='user_id', related_name='recent_papers_in_paper_app')
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    viewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'recentpaper'
        ordering = ['-viewed_at']
        managed = False


class Like_Paper(models.Model):
    id = models.AutoField(primary_key=True)
    paper_id = models.ForeignKey(Paper, on_delete=models.CASCADE, db_column='paper_id')
    user_id = models.ForeignKey('main.User', on_delete=models.CASCADE, db_column='user_id', related_name='liked_papers_in_paper_app')
    count = models.IntegerField(default=0)

    class Meta:
        db_table = 'like_paper'
        unique_together = ('paper_id', 'user_id')
        managed = False
