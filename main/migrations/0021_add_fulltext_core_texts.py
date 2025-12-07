# main/migrations/0021_add_fulltext_core_texts.py
from django.db import migrations

SQLS = [
    "CREATE FULLTEXT INDEX ft_paper_title_abs ON paper (title, abstract);",
    "CREATE FULLTEXT INDEX ft_keyword_name ON keyword (keyword_name);",
    "CREATE FULLTEXT INDEX ft_author_name  ON author (name);",
]
REVERT = [
    "DROP INDEX ft_paper_title_abs ON paper;",
    "DROP INDEX ft_keyword_name ON keyword;",
    "DROP INDEX ft_author_name  ON author;",
]
def forwards(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        with schema_editor.connection.cursor() as cur:
            for s in SQLS: cur.execute(s)
def backwards(apps, schema_editor):
    if schema_editor.connection.vendor == "mysql":
        with schema_editor.connection.cursor() as cur:
            for s in REVERT:
                try: cur.execute(s)
                except Exception: pass
class Migration(migrations.Migration):
    dependencies = [('main', '0020_add_fulltext_affiliation_name')]
    operations = [migrations.RunPython(forwards, backwards)]
