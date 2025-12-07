# main/migrations/00xx_add_covering_indexes.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('main', '0018_paperembedding_norm_vector_paperembedding_updated_at'),
    ]
    operations = [
        migrations.AddIndex(
            model_name='paper_affiliation',
            index=models.Index(
                fields=['affiliation_id', 'paper_id'],
                name='idx_pa_aff_paper',
            ),
        ),
        migrations.AddIndex(
            model_name='paper_affiliation',
            index=models.Index(
                fields=['paper_id', 'affiliation_id'],
                name='idx_pa_paper_aff',
            ),
        ),
        migrations.AddIndex(
            model_name='paper_author',
            index=models.Index(
                fields=['paper_id', 'author_id'],
                name='idx_pap_paper_author',
            ),
        ),
        migrations.AddIndex(
            model_name='paper_part',
            index=models.Index(
                fields=['paper_id', 'part_id'],
                name='idx_pp_paper_part',
            ),
        ),
        migrations.AddIndex(
            model_name='paper_keyword',
            index=models.Index(
                fields=['paper_id', 'keyword_id'],
                name='idx_pk_paper_kw',
            ),
        ),
        migrations.AddIndex(
            model_name='paper',
            index=models.Index(
                fields=['year', 'citation'],
                name='idx_paper_year_cit',
            ),
        ),
        migrations.AddIndex(
            model_name='paper',
            index=models.Index(
                fields=['published_in'],
                name='idx_paper_pubin',
            ),
        ),
    ]
